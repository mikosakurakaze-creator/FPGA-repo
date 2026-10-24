"""D Golden generation, exact independent backend checks, and FP32 error evidence."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
import numpy as np
import torch
from PIL import Image,ImageDraw
from models.compact_d.model import load_model,trace
from .calibrate import synthetic_cases,read_rgb
from .numeric import run,load_package,input_rgb8,display_rgb8,sha256,write_json

def metrics(reference,actual):
    delta=actual.astype(np.float64)-reference.astype(np.float64)
    mse=float(np.mean(delta*delta))
    return dict(mae=float(np.mean(np.abs(delta))),max_abs=float(np.max(np.abs(delta))),mean_signed=float(np.mean(delta)),psnr_db=-10*math.log10(mse) if mse else None)

def run_case(model,package,folder,name,rgb,source=None,dump_all=True,dual=False):
    folder.mkdir(parents=True,exist_ok=False)
    manifest,graph,_=load_package(package)
    Image.fromarray(rgb).save(folder/'input.png')
    qinput=input_rgb8(rgb,14)
    (folder/'input.i16').write_bytes(qinput.astype('<i2').tobytes())
    x=torch.from_numpy(rgb.transpose(2,0,1)[None].copy()).float()/255*2-1
    start=time.perf_counter()
    with torch.inference_mode():floating={k:v.cpu().numpy() for k,v in trace(model,x).items()}
    fp_seconds=time.perf_counter()-start
    records=[]
    def observe(index,node,value,statistics):
        raw=value.astype('<i2').tobytes();filename=f'{index:02d}_{node["id"]}.i16'
        if dump_all or node['id']=='output.relu':(folder/filename).write_bytes(raw)
        records.append(dict(index=index,id=node['id'],file=filename if dump_all or node['id']=='output.relu' else None,shape=list(value.shape),dtype='int16-le',layout='NCHW',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),activation_frac=node['activation_frac'],**statistics,fp32_error=metrics(floating[node['id']],value.astype(np.float64)/(1<<node['activation_frac']))))
    start=time.perf_counter();output=run(package,qinput,observer=observe);int_seconds=time.perf_counter()-start
    if dual:
        def compare(index,node,value,stats):
            expected=np.fromfile(folder/f'{index:02d}_{node["id"]}.i16',dtype='<i2').reshape(value.shape)
            if not np.array_equal(expected,value):raise AssertionError('Independent SciPy direct mismatch: '+node['id'])
        run(package,qinput,backend='direct',observer=compare)
    float_image=np.rint(np.clip(floating['output.relu'],0,1)[0].transpose(1,2,0)*255).astype(np.uint8)
    fixed_image=display_rgb8(output,graph[-1]['activation_frac'])
    Image.fromarray(float_image).save(folder/'fp32.png');Image.fromarray(fixed_image).save(folder/'int16.png')
    diff=np.abs(float_image.astype(np.int16)-fixed_image.astype(np.int16))
    Image.fromarray(np.minimum(diff*32,255).astype(np.uint8)).save(folder/'difference_x32.png')
    # Side-by-side visual evidence preserves full-size PNGs separately.
    thumbs=[]
    for image in (rgb,float_image,fixed_image,np.minimum(diff*32,255).astype(np.uint8)):
        thumb=Image.fromarray(image);thumb.thumbnail((480,270));thumbs.append(thumb)
    width=sum(im.width for im in thumbs);height=max(im.height for im in thumbs)
    sheet=Image.new('RGB',(width,height+24),'#ffffff');draw=ImageDraw.Draw(sheet);left=0
    for label,image in zip(('input','D FP32','D INT16','abs diff x32'),thumbs):
        sheet.paste(image,(left,24));draw.text((left+4,4),label,fill='black');left+=image.width
    sheet.save(folder/'comparison.png')
    report=dict(case=name,bundle_id=manifest['bundle_id'],input_source_sha256=sha256(source) if source else None,input_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),input_i16_sha256=sha256(folder/'input.i16'),shape=list(qinput.shape),scope='Actual full processed dimensions; host CPU only, no FPGA timing',all_intermediates_saved=dump_all,nodes=records,final_error=records[-1]['fp32_error'],display_error=dict(mae=float(diff.mean()),max_abs=int(diff.max()),different_channels=int(np.count_nonzero(diff)),different_pixels=int(np.count_nonzero(np.any(diff,axis=2)))),saturation_count=sum(n['saturated_low']+n['saturated_high'] for n in records),host_seconds=dict(fp32=fp_seconds,integer_numpy_including_hash_dump=int_seconds),scipy_direct_all22_exact=dual)
    write_json(folder/'report.json',report)
    print(json.dumps({'case':name,'shape':list(qinput.shape),'mae':report['final_error']['mae'],'display_max':report['display_error']['max_abs'],'saturation':report['saturation_count'],'seconds':round(int_seconds,3)}),flush=True)
    return report

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--package',required=True);p.add_argument('--out',required=True);p.add_argument('--image-list');p.add_argument('--720p',dest='full720',action='store_true');p.add_argument('--real-only',action='store_true');a=p.parse_args()
    out=Path(a.out)
    if out.exists():raise FileExistsError('Preserve previous evidence')
    out.mkdir(parents=True);torch.set_num_threads(2);model=load_model();reports=[]
    if not a.real_only:
        cases=list(synthetic_cases())
        for h,w in [(1,1),(1,7),(7,1),(2,3),(8,8),(33,47)]:
            # Exactly reuses the published 8x8 and33x47 input fixtures.
            fixture=Path(__file__).resolve().parents[1]/'reference_fp32'/f'random_{h}x{w}'/'input_rgb_nchw_u8.bin'
            rgb=np.fromfile(fixture,dtype=np.uint8).reshape(1,3,h,w)[0].transpose(1,2,0).copy() if fixture.is_file() else np.random.default_rng(20261025+h).integers(0,256,(h,w,3),dtype=np.uint8)
            cases.append((f'random_{h}x{w}',rgb))
        for name,rgb in cases:reports.append(run_case(model,a.package,out/name,name,rgb,dual=True))
    if a.full720:
        yy,xx=np.indices((720,1280));rgb=np.stack((xx%256,yy%256,(xx+yy)%256),axis=2).astype(np.uint8)
        reports.append(run_case(model,a.package,out/'pattern_720p','pattern_720p',rgb,dump_all=True))
    paths=json.loads(Path(a.image_list).read_text()) if a.image_list else []
    for path in paths:
        name=Path(path).stem
        reports.append(run_case(model,a.package,out/name,name,read_rgb(path),source=path,dump_all=False))
    summary=dict(format='compact-d-validation-v1',bundle_id=load_package(a.package)[0]['bundle_id'],environment=dict(torch=torch.__version__,numpy=np.__version__,python=__import__('sys').version,platform=__import__('platform').platform(),threads=2),cases=reports,quality_scope='Quantized D versus frozen D FP32 only; fog/rain labels do not supply clear paired truth; not evidence of deraining or independent camera generalization',all_zero_saturation=all(r['saturation_count']==0 for r in reports),worst_output_mae=max(r['final_error']['mae'] for r in reports),worst_output_max_abs=max(r['final_error']['max_abs'] for r in reports),worst_display_max=max(r['display_error']['max_abs'] for r in reports))
    write_json(out/'summary.json',summary)
    print('D_GOLDEN_SUITE_PASS cases='+str(len(reports)),flush=True)
if __name__=='__main__':main()
