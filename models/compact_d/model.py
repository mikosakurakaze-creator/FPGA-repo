"""Frozen D FP32 architecture. Quantization and FPGA implementation are separate."""
from pathlib import Path
import hashlib
import torch
from torch import nn
import torch.nn.functional as F

CHECKPOINT_SHA256='0d2678ba533a83c797d5b7a2a922461440fa47f93043525a9165f0a1f9fc28fc'
TEACHER_SHA256='80a8f3aad5fd0ed744f39bd60bda802087fbb48b2fa2ce86261ac443a4dba396'
CONFIG={'channels':8,'blocks':3}

class CompactResidual(nn.Module):
    def __init__(self,channels=8,blocks=3):
        super().__init__()
        self.stem=nn.Conv2d(3,channels,3,padding=1)
        self.blocks=nn.ModuleList(nn.Sequential(nn.Conv2d(channels,channels,3,padding=1),nn.ReLU(),
            nn.Conv2d(channels,channels,3,padding=1)) for _ in range(blocks))
        self.head=nn.Conv2d(channels,3,3,padding=1)
        nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)

    def forward(self,x):
        y=F.relu(self.stem(x))
        for block in self.blocks:y=F.relu(y+block(y))
        return F.relu((x+1)*.5+self.head(y))

def load_model(checkpoint=None,device='cpu'):
    path=Path(checkpoint) if checkpoint else Path(__file__).parent/'weights/d_best_fp32.pth'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=CHECKPOINT_SHA256:
        raise ValueError('D frozen checkpoint SHA256 differs')
    state=torch.load(path,map_location='cpu',weights_only=True)
    if state['variant']!='compact_residual_trial' or state['config']!=CONFIG or state['teacher_sha256']!=TEACHER_SHA256:
        raise ValueError('D checkpoint identity differs')
    if state['step']!=600:raise ValueError('Expected selected step 600')
    model=CompactResidual(**CONFIG)
    model.load_state_dict(state['state_dict'],strict=True)
    return model.to(device).eval()

def trace(model,x):
    """Ordered FP32 semantic boundaries; NOT an integer Golden or hardware ABI."""
    nodes={'input':x}
    y=model.stem(x);nodes['stem.conv']=y
    y=F.relu(y);nodes['stem.relu']=y
    for i,block in enumerate(model.blocks):
        residual=y
        y=block[0](y);nodes[f'block{i}.conv0']=y
        y=F.relu(y);nodes[f'block{i}.relu0']=y
        y=block[2](y);nodes[f'block{i}.conv1']=y
        y=residual+y;nodes[f'block{i}.add']=y
        y=F.relu(y);nodes[f'block{i}.relu1']=y
    correction=model.head(y);nodes['head.conv']=correction
    base=(x+1)*.5;nodes['input.affine']=base
    y=base+correction;nodes['output.add']=y
    nodes['output.relu']=F.relu(y)
    return nodes
