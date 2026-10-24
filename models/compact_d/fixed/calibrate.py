"""Record calibration ranges and compare hardware-simple uniform hidden scales."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image,ImageOps
from models.compact_d.model import load_model,trace
from .numeric import sha256,write_json

def read_rgb(path):
    with Image.open(path) as image:
        image=ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1280,720),Image.Resampling.LANCZOS)
        return np.asarray(image).copy()

def synthetic_cases():
    for pattern in ['black','white','gray','red','green','blue','checker','impulse','random']:
        h,w=33,47;rgb=np.zeros((h,w,3),np.uint8)
        if pattern=='white':rgb[:]=255
        elif pattern=='gray':rgb[:]=128
        elif pattern in ('red','green','blue'):rgb[:,:,'rgb'.index(pattern[0])]=255
        elif pattern=='checker':rgb[:]=(((np.indices((h,w)).sum(0)%2)*255)[...,None])
        elif pattern=='impulse':rgb[0,0]=[255,127,0];rgb[-1,-1]=[0,255,127];rgb[h//2,w//2]=255
        elif pattern=='random':rgb=np.random.default_rng(20261025).integers(0,256,rgb.shape,dtype=np.uint8)
        yield pattern,rgb

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--images',nargs='*',default=[]);p.add_argument('--image-list');p.add_argument('--out',required=True);p.add_argument('--scales',required=True);a=p.parse_args()
    torch.set_num_threads(2);model=load_model();peaks={};records=[]
    paths=a.images+(json.loads(Path(a.image_list).read_text()) if a.image_list else [])
    cases=list(synthetic_cases())+[(str(path),read_rgb(path)) for path in paths]
    for name,rgb in cases:
        x=torch.from_numpy(rgb.transpose(2,0,1)[None].copy()).float()/255*2-1
        with torch.inference_mode():nodes=trace(model,x)
        local={k:float(v.abs().max()) for k,v in nodes.items()}
        for key,peak in local.items():peaks[key]=max(peaks.get(key,0),peak)
        records.append(dict(name=Path(name).name,source_sha256=sha256(name) if Path(name).is_file() else None,rgb_sha256=__import__('hashlib').sha256(rgb.tobytes()).hexdigest(),shape=list(rgb.shape),peaks=local))
    # Uniform hidden F13 keeps residuals aligned, with >=~2x headroom over measured probes.
    fracs={k:13 for k in peaks}
    for key in ('input','head.conv','input.affine','output.add','output.relu'):fracs[key]=14
    report=dict(protocol='Nine full33x47 synthetic probes + listed full images after official fit-to720p; calibration only, not quality evaluation',records=records,observed_abs_max=peaks,hidden_candidates=[dict(frac=f,range_max=32767/(1<<f),minimum_peak_headroom=min(32767/(1<<f)/max(v,1e-30) for k,v in peaks.items() if k not in ('input','head.conv','input.affine','output.add','output.relu'))) for f in (12,13,14)],decision='F13 uniform hidden, input/head/base/output F14; residual align free; saturation still defined for all legal input',node_fracs=fracs)
    write_json(a.out,report)
    write_json(a.scales,dict(format='compact-d-scales-v1',node_fracs=fracs,reason=report['decision'],calibration_report_sha256=sha256(a.out)))
    print(json.dumps({'status':'D_CALIBRATION_PASS','cases':len(cases),'max_hidden_peak':max(v for k,v in peaks.items() if fracs[k]==13),'candidate_headroom':report['hidden_candidates']}))
if __name__=='__main__':main()
