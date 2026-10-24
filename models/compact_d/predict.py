"""python predict.py --input photo.jpg --output result.png [--device cpu|cuda]"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
import torch
from model import load_model

def preprocess(path):
    with Image.open(path) as im:image=ImageOps.exif_transpose(im).convert('RGB')
    image.thumbnail((1280,720),Image.Resampling.LANCZOS)
    a=np.asarray(image).astype(np.float32)/255
    return torch.from_numpy(a.transpose(2,0,1).copy())[None]*2-1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    p.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    a=p.parse_args();model=load_model(device=a.device)
    x=preprocess(a.input).to(a.device)
    with torch.inference_mode():y=model(x).clamp(0,1)[0].cpu().numpy().transpose(1,2,0)
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(np.rint(y*255).astype(np.uint8)).save(path)
    print(json.dumps({'output':str(path),'shape':list(x.shape),'device':a.device,'scope':'FP32 software; NOT FPGA'},ensure_ascii=False))

if __name__=='__main__':main()
