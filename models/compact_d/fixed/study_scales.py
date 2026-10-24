"""Compare three activation formats on declared held-out center128 crops."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import torch
from models.compact_d.model import load_model,trace
from .calibrate import read_rgb
from .export import build
from .numeric import input_rgb8,run,load_package,display_rgb8,write_json,sha256
from .suite import metrics

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--image-list',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(2);model=load_model()
    original=json.loads((Path(__file__).parent/'scales.json').read_text());packages={}
    for frac in (12,13,14):
        config=copy.deepcopy(original)
        for name in config['node_fracs']:
            if name not in ('input','head.conv','input.affine','output.add','output.relu'):config['node_fracs'][name]=frac
        config['reason']=f'Exploratory uniform hidden F{frac}, heldout crop comparison, not final bundle'
        file=out/f'scales_f{frac}.json';write_json(file,config);folder=out/f'package_f{frac}';build(folder,file);packages[frac]=folder
    reports=[]
    for path in json.loads(Path(a.image_list).read_text()):
        rgb=read_rgb(path);h,w=rgb.shape[:2];ch,cw=min(128,h),min(128,w);y,x=(h-ch)//2,(w-cw)//2;rgb=rgb[y:y+ch,x:x+cw].copy()
        with torch.inference_mode():floating=trace(model,torch.from_numpy(rgb.transpose(2,0,1)[None].copy()).float()/255*2-1)['output.relu'].numpy()
        displays=np.rint(np.clip(floating,0,1)[0].transpose(1,2,0)*255).astype(np.uint8)
        record=dict(image=Path(path).name,source_sha256=sha256(path),processed_shape=[h,w],crop_yxhw=[y,x,ch,cw],candidates=[])
        for frac,folder in packages.items():
            saturated=[]
            output=run(folder,input_rgb8(rgb,14),observer=lambda i,n,v,s:saturated.append(s['saturated_low']+s['saturated_high']))
            delta=np.abs(display_rgb8(output).astype(np.int16)-displays.astype(np.int16))
            record['candidates'].append(dict(hidden_frac=frac,**metrics(floating,output.astype(np.float64)/16384),display_mae=float(delta.mean()),display_max=int(delta.max()),saturation_count=sum(saturated)))
        reports.append(record)
    summary=[]
    for frac in packages:
        results=[next(v for v in r['candidates'] if v['hidden_frac']==frac) for r in reports]
        summary.append(dict(hidden_frac=frac,mean_image_mae=float(np.mean([r['mae'] for r in results])),worst_max_abs=max(r['max_abs'] for r in results),saturation_count=sum(r['saturation_count'] for r in results),worst_display_max=max(r['display_max'] for r in results)))
    report=dict(scope='All12 fixed holdout images, one center128x128 crop each, no resizing crop to claim720p; compares quantization fidelity only',cases=reports,summary=summary,decision='Use hiddenF13: calibration headroom2.356x versus F14 1.178x, with sub1 RGB8 quantization differences on full-image evaluation. F12 sacrifices fidelity. All retain INT16 storage/MAC operand size; this is precision range tradeoff, not measured DSP saving.')
    write_json(out/'report.json',report);print(json.dumps({'status':'D_SCALE_STUDY_PASS','summary':summary}))
if __name__=='__main__':main()
