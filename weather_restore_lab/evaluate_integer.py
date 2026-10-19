"""Full-image integer candidate quality; floating point only for metrics/reference."""
import argparse
import csv
from pathlib import Path
import numpy as np
import torch
from data import audit_manifest,PairedImages
from integer import IntegerRestore,tiled_integer
from metrics import quality
from run import load_model,array,write_json,average_metrics,sha


def main():
    import json
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True);p.add_argument('--checkpoint',required=True)
    p.add_argument('--integer-dir',required=True);p.add_argument('--output',required=True)
    p.add_argument('--tile',type=int,default=128);p.add_argument('--limit',type=int,default=0)
    p.add_argument('--split',choices=['val','test'],default='test')
    args=p.parse_args()
    audit=audit_manifest(args.manifest)
    folder=Path(args.integer_dir)
    spec=json.loads((folder/'integer_spec.json').read_text())
    if spec['checkpoint_sha256']!=sha(args.checkpoint):raise ValueError('Integer package/checkpoint identity differs')
    if spec['task']!=audit['task'] or spec['manifest_sha256']!=audit['manifest_sha256']:
        raise ValueError('Integer package/dataset identity differs')
    with np.load(folder/'integer_weights.npz',allow_pickle=False) as data:
        integer=IntegerRestore(spec,{k:data[k].copy() for k in data.files})
    model,checkpoint=load_model(args.checkpoint,'cpu')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    rows=[];diagnostics=[]
    dataset=PairedImages(args.manifest,args.split)
    for i,(a,b,identity) in enumerate(dataset):
        if args.limit and i>=args.limit:break
        x=np.rint(a[None].numpy()*16384).astype(np.int16)
        q=tiled_integer(integer,x,args.tile)
        restored=q[0].astype(np.float32).transpose(1,2,0)/16384
        with torch.inference_mode():fp=model(a[None]).clamp(0,1)
        error=np.abs(restored-array(fp[0]))
        row={'id':identity,'height':a.shape[1],'width':a.shape[2],
             'fp32_integer_mae':float(error.mean()),'fp32_integer_max_abs':float(error.max()),
             'saturations_including_overlap':sum(integer.saturations.values())}
        for prefix,prediction in (('input_',array(a)),('float_',array(fp[0])),('integer_',restored)):
            row.update({prefix+k:v for k,v in quality(prediction,array(b)).items()})
        rows.append(row)
        diagnostics.append({'id':identity,'saturations_including_overlap':dict(integer.saturations),
                            'int32_conservative_checks':'PASS','accumulator_peaks':dict(integer.accumulator_peaks)})
        if (i+1)%10==0:print(f'full-image integer {i+1}/{len(dataset)}',flush=True)
    with (output/'per_image.csv').open('w',newline='',encoding='utf-8') as handle:
        w=csv.DictWriter(handle,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_json(output/'diagnostics.json',diagnostics)
    summary={'task':audit['task'],'data_kind':audit['kind'],'images':len(rows),
             'split':args.split,'available_split_images':len(dataset),'full_split':len(rows)==len(dataset),
             'checkpoint_step':checkpoint['step'],'identity_control':checkpoint['step']==0,
             'input':average_metrics(rows,'input_'),'float':average_metrics(rows,'float_'),
             'integer':average_metrics(rows,'integer_'),
             'max_fp32_integer_abs_error':max(r['fp32_integer_max_abs'] for r in rows),
             'saturations_including_overlap':sum(r['saturations_including_overlap'] for r in rows),
             'hardware_deployable':'NOT_VERIFIED'}
    write_json(output/'summary.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
