"""CLI for audited paired restoration experiments. Run --help for commands."""
import argparse
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import csv
import hashlib
import json
import random
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader
from data import PairedImages, audit_manifest
from metrics import quality
from model import TinyRestore, tiled_forward, engineering_profile


def write_json(path, value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_model(path, device):
    checkpoint = torch.load(path,map_location='cpu',weights_only=True)
    model = TinyRestore(**checkpoint['config']).to(device)
    model.load_state_dict(checkpoint['state_dict'],strict=True)
    model.eval()
    return model,checkpoint


def array(t):
    return t.detach().cpu().numpy().transpose(1,2,0)


def average_metrics(rows, prefix):
    result = {}
    for metric in ('psnr_db','ssim','mae'):
        values = [r[prefix+metric] for r in rows if r[prefix+metric] is not None]
        result[metric] = float(np.mean(values)) if values else None
    result['infinite_psnr_count'] = sum(r[prefix+'psnr_db'] is None for r in rows)
    return result


@torch.inference_mode()
def validate(model, dataset, device):
    model.eval()
    errors = []
    for a,b,_ in dataset:
        pred = model(a.unsqueeze(0).to(device)).clamp(0,1).cpu()[0]
        errors.append(float(torch.mean((pred-b)**2)))
    return float(np.mean(errors))


def train(args):
    audit = audit_manifest(args.manifest)
    if args.steps <= 0 or args.batch <= 0 or args.crop < 8 or args.validate_every <= 0:
        raise ValueError('Invalid training settings')
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable; no silent CPU fallback')
    output = Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark=False
    torch.backends.cudnn.deterministic=True
    torch.backends.cudnn.allow_tf32=False
    torch.backends.cuda.matmul.allow_tf32=False
    model = TinyRestore(args.channels,args.blocks).to(args.device)
    optimizer = torch.optim.Adam(model.parameters(),lr=args.lr)
    trainset = PairedImages(args.manifest,'train',args.crop,cache=args.cache_data)
    valset = PairedImages(args.manifest,'val',cache=args.cache_data)
    loader = DataLoader(trainset,batch_size=args.batch,shuffle=True,num_workers=0)
    initial_val = validate(model,valset,args.device)
    best = initial_val
    metadata = {'task':audit['task'], 'data_kind':audit['kind'], 'config':model.config(),
                'manifest_sha256':audit['manifest_sha256'], 'seed':args.seed,
                'torch_version':str(torch.__version__), 'device':args.device,
                'gpu':torch.cuda.get_device_name(0) if args.device=='cuda' else None,
                'initial_validation_mse':initial_val,
                'training_args':{k:v for k,v in vars(args).items() if k!='func'},
                'status':'EXPERIMENTAL_NOT_HARDWARE_VALIDATED'}
    write_json(output/'experiment.json',metadata)
    def checkpoint(step,value):
        return {**metadata,'step':step,'validation_mse':value,
                'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()}}
    # Keep identity baseline if training never improves; never disguise it as learned success.
    torch.save(checkpoint(0,best),output/'best.pth')
    iterator = iter(loader)
    start = time.perf_counter()
    with (output/'training.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=['step','train_loss','loss_kind','val_mse','elapsed_seconds'])
        writer.writeheader()
        for step in range(1,args.steps+1):
            try:
                a,b,_ = next(iterator)
            except StopIteration:
                iterator=iter(loader)
                a,b,_ = next(iterator)
            model.train()
            a,b = a.to(args.device),b.to(args.device)
            optimizer.zero_grad(set_to_none=True)
            prediction=model(a)
            loss=(torch.nn.functional.l1_loss(prediction,b) if args.loss=='l1'
                  else torch.nn.functional.mse_loss(prediction,b))
            if not torch.isfinite(loss):
                raise RuntimeError('Nonfinite loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0,error_if_nonfinite=True)
            optimizer.step()
            val=None
            if step % args.validate_every == 0 or step==args.steps:
                val=validate(model,valset,args.device)
                if val < best:
                    best=val
                    torch.save(checkpoint(step,val),output/'best.pth')
                print(f'step={step}/{args.steps} train_{args.loss}={loss.item():.6f} val_MSE={val:.6f}',flush=True)
            writer.writerow({'step':step,'train_loss':float(loss.detach()),'loss_kind':args.loss,'val_mse':val,
                             'elapsed_seconds':time.perf_counter()-start})
            handle.flush()
    torch.save(checkpoint(args.steps,val),output/'last.pth')
    write_json(output/'training_summary.json',{'steps':args.steps,'seconds':time.perf_counter()-start,
               'initial_validation_mse':initial_val,'best_validation_mse':best,
               'improved_validation':best<initial_val,'best_checkpoint_sha256':sha(output/'best.pth')})


def evaluate(args):
    audit = audit_manifest(args.manifest)
    model,checkpoint=load_model(args.checkpoint,args.device)
    if checkpoint['task'] != audit['task']:
        raise ValueError('Checkpoint task and dataset task differ')
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    dataset=PairedImages(args.manifest,args.split)
    with torch.inference_mode():
        for index,(a,b,identity) in enumerate(dataset):
            source=b if args.clean_input else a
            x=source.unsqueeze(0).to(args.device)
            if args.device=='cuda': torch.cuda.synchronize()
            start=time.perf_counter()
            pred=tiled_forward(model,x,args.tile) if args.tile else model(x)
            if args.device=='cuda': torch.cuda.synchronize()
            elapsed=time.perf_counter()-start
            pred=array(pred[0].clamp(0,1))
            raw,reference=array(source),array(b)
            row={'id':identity,'height':a.shape[1],'width':a.shape[2],
                 'pc_inference_seconds':elapsed}
            row.update({'input_'+k:v for k,v in quality(raw,reference).items()})
            row.update({'restored_'+k:v for k,v in quality(pred,reference).items()})
            rows.append(row)
            if index < args.previews:
                pictures=[np.uint8(np.rint(np.clip(t,0,1)*255)) for t in (raw,pred,reference)]
                h,w=pictures[0].shape[:2]
                canvas=Image.new('RGB',(w*3,h+24),'white')
                draw=ImageDraw.Draw(canvas)
                for col,(picture,label) in enumerate(zip(pictures,['INPUT','RESTORED','REFERENCE'])):
                    canvas.paste(Image.fromarray(picture),(col*w,24))
                    draw.text((col*w+4,4),label,fill='black')
                canvas.save(output/f'{index:03d}_comparison.png')
    with (output/'per_image.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'task':audit['task'],'data_kind':audit['kind'],'split':args.split,'images':len(rows),
             'input_type':'clean_target_identity_protection' if args.clean_input else 'degraded_input',
             'checkpoint_sha256':sha(args.checkpoint),'checkpoint_step':checkpoint['step'],
             'identity_control':checkpoint['step']==0,
             'dataset_audit':audit,'input':average_metrics(rows,'input_'),
             'restored':average_metrics(rows,'restored_'),
             'metrics_protocol':'RGB [0,1], output clip, full image, no border crop, skimage SSIM default',
             'device':args.device,'timing_scope':'PC inference only; no decode/encode; NOT FPGA FPS',
             'hardware_deployable':'NOT_VERIFIED'}
    write_json(output/'summary.json',summary)
    print(json.dumps(summary,indent=2))


def profile(args):
    profiles=[engineering_profile(TinyRestore(c,args.blocks),args.height,args.width,args.tile,args.fps)
              for c in (8,16)]
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    write_json(args.output,profiles)
    print(json.dumps(profiles,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    audit=sub.add_parser('audit');audit.add_argument('--manifest',required=True)
    audit.set_defaults(func=lambda a:print(json.dumps(audit_manifest(a.manifest),indent=2)))
    t=sub.add_parser('train')
    t.add_argument('--manifest',required=True);t.add_argument('--output',required=True)
    t.add_argument('--channels',type=int,choices=[8,16],default=8)
    t.add_argument('--blocks',type=int,default=5);t.add_argument('--steps',type=int,default=1000)
    t.add_argument('--crop',type=int,default=96);t.add_argument('--batch',type=int,default=8)
    t.add_argument('--lr',type=float,default=1e-3);t.add_argument('--seed',type=int,default=42)
    t.add_argument('--cache-data',action='store_true',help='Keep decoded train/val pairs in host RAM')
    t.add_argument('--loss',choices=['l1','mse'],default='l1')
    t.add_argument('--validate-every',type=int,default=100)
    t.add_argument('--device',choices=['cpu','cuda'],default='cuda');t.set_defaults(func=train)
    e=sub.add_parser('evaluate')
    e.add_argument('--manifest',required=True);e.add_argument('--checkpoint',required=True)
    e.add_argument('--output',required=True);e.add_argument('--split',choices=['val','test'],default='test')
    e.add_argument('--tile',type=int,default=128);e.add_argument('--previews',type=int,default=6)
    e.add_argument('--clean-input',action='store_true')
    e.add_argument('--device',choices=['cpu','cuda'],default='cuda');e.set_defaults(func=evaluate)
    r=sub.add_parser('profile')
    r.add_argument('--height',type=int,default=720);r.add_argument('--width',type=int,default=1272)
    r.add_argument('--tile',type=int,default=128);r.add_argument('--blocks',type=int,default=5)
    r.add_argument('--fps',type=float,default=30);r.add_argument('--output',required=True)
    r.set_defaults(func=profile)
    args=p.parse_args();args.func(args)


if __name__=='__main__':
    main()
