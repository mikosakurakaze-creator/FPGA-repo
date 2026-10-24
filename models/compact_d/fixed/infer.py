"""Torch-free image -> D integer output; no hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from .numeric import load_package,input_rgb8,run,display_rgb8,sha256,write_json

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--package',required=True);p.add_argument('--input',required=True);p.add_argument('--out',required=True);p.add_argument('--dump-all',action='store_true');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    with Image.open(a.input) as image:
        image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1280,720),Image.Resampling.LANCZOS);rgb=np.asarray(image).copy()
    qinput=input_rgb8(rgb,14);(out/'input.i16').write_bytes(qinput.tobytes());Image.fromarray(rgb).save(out/'input.png');nodes=[]
    def observer(index,node,value,stats):
        raw=value.astype('<i2').tobytes();filename=f'{index:02d}_{node["id"]}.i16'
        if a.dump_all or node['id']=='output.relu':(out/filename).write_bytes(raw)
        nodes.append(dict(index=index,id=node['id'],shape=list(value.shape),dtype='int16-le',layout='NCHW',activation_frac=node['activation_frac'],sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),file=filename if a.dump_all or node['id']=='output.relu' else None,**stats))
    manifest,graph,_=load_package(a.package);output=run(a.package,qinput,observer=observer)
    Image.fromarray(display_rgb8(output,graph[-1]['activation_frac'])).save(out/'int16.png')
    report=dict(case=Path(a.input).stem,scope='Host integer reference, no FPGA execution',bundle_id=manifest['bundle_id'],input_source_sha256=sha256(a.input),input_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),input_i16_sha256=sha256(out/'input.i16'),shape=list(qinput.shape),nodes=nodes)
    write_json(out/'report.json',report);print(json.dumps({'status':'D_INTEGER_INFER_PASS','shape':report['shape'],'bundle_id':manifest['bundle_id']}))
if __name__=='__main__':main()
