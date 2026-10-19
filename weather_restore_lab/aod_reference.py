"""Run publisher AOD-Net Caffe weights through OpenCV CPU, RGB [0,1].

Network layers are taken from the publisher's saved prototxt. Only the label
input and EuclideanLoss are omitted for deployment. No downloaded Python runs.
"""
import argparse
import csv
import json
import re
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
from metrics import quality
from public_data import digest


def predict(folder,path):
    with Image.open(path) as image:
        rgb=image.convert('RGB')
        rgb.thumbnail((800,800),Image.Resampling.LANCZOS)
        x=np.asarray(rgb,dtype=np.float32)/255
    h,w=x.shape[:2]
    template=(folder/'test_template.prototxt').read_text()
    rendered=template.format(height=h,width=w)
    layers=rendered[rendered.index('layer {'):]
    layers=re.sub(r'layer\s*\{\s*name:\s*"loss"[\s\S]*$','',layers)
    header=f'name: "AODDeploy"\ninput: "data"\ninput_dim: 1\ninput_dim: 3\ninput_dim: {h}\ninput_dim: {w}\n'
    deploy=folder/'deploy_generated.prototxt'
    deploy.write_text(header+layers)
    net=cv2.dnn.readNetFromCaffe(str(deploy),str(folder/'AOD_Net.caffemodel'))
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    net.setInput(np.ascontiguousarray(x.transpose(2,0,1)[None]))
    start=time.perf_counter()
    y=net.forward('clip')[0].transpose(1,2,0)
    seconds=time.perf_counter()-start
    if not np.isfinite(y).all():raise ValueError('Nonfinite AOD result')
    return x,np.clip(y,0,1),seconds


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets',default='data/aod_reference');p.add_argument('--input')
    p.add_argument('--manifest');p.add_argument('--split',choices=['val','test'],default='test')
    p.add_argument('--output',required=True)
    args=p.parse_args()
    folder=Path(args.assets);output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    references={}
    if bool(args.input)==bool(args.manifest):raise ValueError('Choose exactly one of --input or --manifest')
    if args.manifest:
        from data import audit_manifest,read_manifest,read_rgb
        audit=audit_manifest(args.manifest)
        if audit['task']!='dehaze':raise ValueError('AOD reference requires dehaze manifest')
        _,pairs=read_manifest(args.manifest)
        pairs=[r for r in pairs if r['split']==args.split]
        paths=[r['input'] for r in pairs];references={r['input']:r['target'] for r in pairs}
    else:paths=sorted(Path(args.input).glob('*.jpg'))
    if not paths:raise ValueError('No input images')
    rows=[]
    for path in paths:
        x,y,seconds=predict(folder,path)
        h,w=x.shape[:2]
        canvas=Image.new('RGB',(w*2,h+24),'white');draw=ImageDraw.Draw(canvas)
        for col,(image,label) in enumerate(((x,'INPUT'),(y,'AOD-NET REFERENCE'))):
            canvas.paste(Image.fromarray(np.uint8(np.rint(image*255))),(col*w,24))
            draw.text((col*w+4,4),label,fill='black')
        canvas.save(output/(path.stem+'_comparison.png'))
        row={'input':str(path.resolve()),'sha256':digest(path),'shape':list(x.shape),
             'cpu_forward_seconds':seconds,'ground_truth':bool(references)}
        if references:
            reference=read_rgb(references[path])
            if reference.shape!=y.shape:raise ValueError('Reference shape differs after AOD resize')
            row.update({'input_'+k:v for k,v in quality(x,reference).items()})
            row.update({'restored_'+k:v for k,v in quality(y,reference).items()})
        rows.append(row)
    summary={'model':'publisher AOD-Net Caffe',
        'weights_sha256':digest(folder/'AOD_Net.caffemodel'),'opencv':cv2.__version__,
        'scope':'paired local evaluation' if references else 'unpaired sample demonstration',
        'hardware_deployable':'NOT_VERIFIED',
        'preprocessing':'PIL RGB [0,1], aspect preserving resize <=800',
        'results':rows}
    if references:
        from run import average_metrics
        summary.update({'images':len(rows),'split':args.split,'dataset_audit':audit,
            'input':average_metrics(rows,'input_'),'restored':average_metrics(rows,'restored_')})
    (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
