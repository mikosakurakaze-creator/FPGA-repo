"""Image/video software inference; performance is PC processing, never FPGA FPS."""
import argparse
import csv
import json
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from data import tensor
from model import tiled_forward
from run import load_model,sha,write_json


@torch.inference_mode()
def restore(model,rgb,device,core):
    x=tensor(rgb.astype(np.float32)/255)[None].to(device)
    y=tiled_forward(model,x,core).clamp(0,1)
    return np.uint8(np.rint(y[0].cpu().numpy().transpose(1,2,0)*255))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True);p.add_argument('--input',required=True)
    p.add_argument('--output',required=True);p.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    p.add_argument('--tile',type=int,default=128);p.add_argument('--video',action='store_true')
    args=p.parse_args()
    output=Path(args.output)
    if output.exists():raise FileExistsError(output)
    if output.resolve()==Path(args.input).resolve():raise ValueError('Input equals output')
    output.parent.mkdir(parents=True,exist_ok=True)
    model,checkpoint=load_model(args.checkpoint,args.device)
    metadata={'task':checkpoint['task'],'checkpoint_sha256':sha(args.checkpoint),
              'checkpoint_step':checkpoint['step'],'identity_control':checkpoint['step']==0,
              'device':args.device,'scope':'software inference only; no FPGA acceptance'}
    if not args.video:
        with Image.open(args.input) as image:rgb=np.array(image.convert('RGB'))
        start=time.perf_counter();result=restore(model,rgb,args.device,args.tile)
        metadata['inference_and_transfer_seconds']=time.perf_counter()-start
        Image.fromarray(result).save(output)
    else:
        import cv2
        capture=cv2.VideoCapture(args.input)
        writer=None;rows=[]
        try:
            if not capture.isOpened():raise ValueError('Cannot decode input video')
            fps=capture.get(cv2.CAP_PROP_FPS)
            if not np.isfinite(fps) or fps<=0:raise ValueError('Input video requires known positive FPS')
            start=time.perf_counter()
            while True:
                frame_start=time.perf_counter()
                ok,bgr=capture.read()
                if not ok:break
                if writer is None:
                    h,w=bgr.shape[:2]
                    if h%2 or w%2:raise ValueError('mp4v video requires even dimensions; no silent crop')
                    writer=cv2.VideoWriter(str(output),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
                    if not writer.isOpened():raise ValueError('Cannot open video encoder')
                rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                restored=restore(model,rgb,args.device,args.tile)
                writer.write(cv2.cvtColor(restored,cv2.COLOR_RGB2BGR))
                rows.append({'frame_id':len(rows),'source_timestamp_ms':capture.get(cv2.CAP_PROP_POS_MSEC),
                             'decode_restore_encode_seconds':time.perf_counter()-frame_start})
        finally:
            capture.release()
            if writer is not None:writer.release()
        elapsed=time.perf_counter()-start
        if not rows:raise ValueError('No video frames processed')
        # Decode the delivered file to catch encoder failures, truncation or dropped frames.
        verification=cv2.VideoCapture(str(output));delivered=0
        try:
            while verification.read()[0]:delivered+=1
        finally:verification.release()
        if delivered!=len(rows):raise RuntimeError('Encoded output frame count differs from processed frames')
        with output.with_suffix('.frames.csv').open('w',newline='',encoding='utf-8') as handle:
            w=csv.DictWriter(handle,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        metadata.update({'frames':len(rows),'verified_encoded_frames':delivered,'input_fps':fps,
            'output_playback_fps':fps,'wall_seconds':elapsed,'pc_processing_fps':len(rows)/elapsed,
            'latency_p95_seconds':float(np.percentile([r['decode_restore_encode_seconds'] for r in rows],95)),
            'limitations':'No audio; constant-FPS file output; no live-camera latency or frame-drop claim'})
    write_json(output.with_suffix(output.suffix+'.json'),metadata)
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()
