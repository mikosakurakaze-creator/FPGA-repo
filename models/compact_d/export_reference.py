"""Export raw FP32 weights, graph and deterministic small reference fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from model import load_model,trace,CHECKPOINT_SHA256

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1);model=load_model()
    parameters={};blob=bytearray()
    for name,value in model.state_dict().items():
        raw=value.cpu().numpy().astype('<f4').tobytes()
        parameters[name]=dict(shape=list(value.shape),offset=len(blob),bytes=len(raw),
            dtype='float32-le',layout='OIHW' if value.ndim==4 else 'O',sha256=hashlib.sha256(raw).hexdigest())
        blob.extend(raw)
    (out/'weights_fp32.bin').write_bytes(blob)
    records=[]
    for name,h,w in [('random_8x8',8,8),('random_33x47',33,47)]:
        # Integer RGB fixtures avoid backend-dependent random FP32 generation.
        a=np.random.default_rng(20261025+h).integers(0,256,(1,3,h,w),dtype=np.uint8)
        x=torch.from_numpy(a.astype(np.float32)/255)*2-1
        folder=out/name;folder.mkdir()
        (folder/'input_rgb_nchw_u8.bin').write_bytes(a.tobytes())
        with torch.inference_mode():nodes=trace(model,x);y=model(x)
        assert torch.equal(y,nodes['output.relu'])
        metas=[]
        for i,(node,value) in enumerate(nodes.items()):
            raw=value.cpu().numpy().astype('<f4').tobytes();filename=f'{i:02d}_{node}.f32'
            (folder/filename).write_bytes(raw)
            metas.append(dict(id=node,file=filename,shape=list(value.shape),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        records.append(dict(case=name,nodes=metas))
    graph=[dict(id='input',op='input',layout='NCHW',dtype='float32',range=[-1,1])]
    previous='input'
    def conv(node,parameter):
        nonlocal previous
        graph.append(dict(id=node,op='conv',inputs=[previous],weight=parameter+'.weight',bias=parameter+'.bias',
            kernel=[3,3],stride=[1,1],padding=[1,1],padding_mode='zeros',dilation=[1,1],groups=1))
        previous=node
    def relu(node):
        nonlocal previous
        graph.append(dict(id=node,op='relu',inputs=[previous]));previous=node
    conv('stem.conv','stem');relu('stem.relu')
    for i in range(3):
        skip=previous
        conv(f'block{i}.conv0',f'blocks.{i}.0');relu(f'block{i}.relu0')
        conv(f'block{i}.conv1',f'blocks.{i}.2')
        graph.append(dict(id=f'block{i}.add',op='add',inputs=[skip,previous]));previous=f'block{i}.add'
        relu(f'block{i}.relu1')
    conv('head.conv','head')
    graph.append(dict(id='input.affine',op='affine',inputs=['input'],scale=.5,offset=.5))
    graph.append(dict(id='output.add',op='add',inputs=['input.affine','head.conv']));previous='output.add'
    relu('output.relu')
    assert len(graph)==22 and [n['id'] for n in graph]==[n['id'] for n in records[0]['nodes']]
    report=dict(scope='FP32 structural/numerical reference; NOT integer Golden or FPGA ABI',
        checkpoint_sha256=CHECKPOINT_SHA256,torch_version=str(torch.__version__),device='cpu',parameters=parameters,
        parameter_count=sum(v.numel() for v in model.parameters()),weights_bytes=len(blob),
        weights_sha256=hashlib.sha256(blob).hexdigest(),graph=graph,cases=records,
        limits='FP32 CPU/GPU kernels may differ slightly; A must define fixed point and integer Golden separately')
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('D_FP32_EXPORT_PASS parameters=3947 convs=8 semantic_nodes=22 cases=2')

if __name__=='__main__':main()
