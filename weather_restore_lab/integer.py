"""Power-of-two INT8 weights / INT16 nodes / checked INT32 MAC reference.

NumPy int64 containers implement exact integer math and detect INT32 overflow.
This is an arithmetic specification, not an FPGA implementation or speed model.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from data import PairedImages, audit_manifest
from run import load_model, write_json, sha, array
from metrics import quality


def round_div(values, power):
    values=np.asarray(values,dtype=np.int64)
    if power < 0:raise ValueError('Negative shift')
    divisor=1<<power
    absolute=np.abs(values)
    quotient,remainder=absolute//divisor,absolute%divisor
    inc=(remainder*2>divisor)|((remainder*2==divisor)&((quotient&1)!=0))
    return np.sign(values)*(quotient+inc)


def rescale(values, old, new):
    values=np.asarray(values,dtype=np.int64)
    return round_div(values,old-new) if old>=new else values*(1<<(new-old))


def fraction(maximum, limit):
    return int(np.clip(np.floor(np.log2(limit/max(float(maximum),1e-12))),-8,20))


def conv_integer(x,w,b,groups=1,pad=0):
    x,w,b=[np.asarray(t,dtype=np.int64) for t in (x,w,b)]
    n,c,h,width=x.shape
    out,ci,kh,kw=w.shape
    if groups not in (1,c) or (groups!=1 and out!=c):
        raise ValueError('Only dense or depthwise convolution supported')
    # Bound all partial sums, including channel-order variations in hardware.
    input_bound=int(np.max(np.abs(x)))
    bound=input_bound*np.abs(w).sum(axis=(1,2,3))+np.abs(b)
    if np.any(bound>(1<<31)-1):
        raise OverflowError('INT32 conservative partial-sum bound exceeded')
    padded=np.pad(x,((0,0),(0,0),(pad,pad),(pad,pad)))
    result=np.broadcast_to(b[None,:,None,None],(n,out,h,width)).copy()
    peak=int(np.max(np.abs(result)))
    for y in range(kh):
        for col in range(kw):
            region=padded[:,:,y:y+h,col:col+width]
            if groups!=1:
                result+=region*w[:,0,y,col][None,:,None,None]
            else:
                result+=np.einsum('nchw,oc->nohw',region,w[:,:,y,col],optimize=True,dtype=np.int64)
            peak=max(peak,int(np.max(np.abs(result))))
            if result.min()<-(1<<31) or result.max()>(1<<31)-1:
                raise OverflowError('INT32 partial accumulator overflow')
    return result,peak


def calibrate(model,dataset,count=8,margin=1.0):
    if count<=0 or margin<1.0 or not np.isfinite(margin):raise ValueError('Invalid calibration coverage/margin')
    maxima={}
    with torch.inference_mode():
        for i in range(min(count,len(dataset))):
            a,_,_=dataset[i]
            taps={};model(a[None],taps)
            for key,value in taps.items():
                maxima[key]=max(maxima.get(key,0),float(value.abs().max()))
    fracs={name:fraction(value*margin,32767) for name,value in maxima.items()}
    fracs['input']=14
    fracs['output']=14
    weights={};layers={}
    input_frac=14
    for name,module in model.named_modules():
        if not isinstance(module,torch.nn.Conv2d):continue
        w=module.weight.detach().numpy();b=module.bias.detach().numpy()
        if name=='stem':input_frac=14
        elif name.endswith('.depth'):
            index=int(name.split('.')[1])
            input_frac=fracs['stem'] if index==0 else fracs[f'blocks.{index-1}.add']
        elif name.endswith('.point'):input_frac=fracs[name.replace('.point','.depth')]
        elif name=='tail':input_frac=fracs[f'blocks.{model.block_count-1}.add']
        wf=[];wb=[];bias=[]
        for channel in range(w.shape[0]):
            f=fraction(np.max(np.abs(w[channel])),127)
            while abs(float(b[channel])*2.0**(input_frac+f))>(1<<31)-1:
                f-=1
                if f < -8:raise OverflowError('Bias cannot fit candidate format')
            wf.append(f)
            wb.append(np.clip(np.rint(w[channel]*2.0**f),-127,127).astype(np.int8))
            bias.append(int(np.rint(float(b[channel])*2.0**(input_frac+f))))
        weights[name+'.weight']=np.stack(wb)
        weights[name+'.bias']=np.array(bias,dtype=np.int32)
        layers[name]={'input_frac':input_frac,'output_frac':fracs[name],
                      'weight_frac':wf,'groups':module.groups,'padding':module.padding[0],
                      'weight_shape':list(w.shape)}
    spec={'config':model.config(),'node_frac':fracs,'layers':layers,'calibration_max_abs':maxima,
          'calibration_margin':margin,'calibration_images':min(count,len(dataset)),
          'format':'signed symmetric power-of-two, real=raw*2^-frac',
          'rounding':'nearest, ties-to-even; signed symmetric',
          'weights':'INT8 [-127,127], per-output-channel frac',
          'activations':'INT16 [-32768,32767], per-node frac',
          'accumulator':'INT32 checked after each kernel-position sum; int64 reference containers',
          'output':'RGB NCHW little-endian INT16 Q14, clipped to [0,16384]',
          'residual_add':'rescale each operand separately with ties-to-even, sum, saturate INT16 then ReLU',
          'hardware_deployable':'NOT_VERIFIED'}
    spec['graph']=[{'name':'stem','op':'conv','input':'input'},
                   {'name':'stem_relu','op':'relu','input':'stem'}]
    previous='stem_relu'
    for i in range(model.block_count):
        prefix=f'blocks.{i}'
        spec['graph'] += [
            {'name':prefix+'.depth','op':'conv','input':previous},
            {'name':prefix+'.depth_relu','op':'relu','input':prefix+'.depth'},
            {'name':prefix+'.point','op':'conv','input':prefix+'.depth_relu'},
            {'name':prefix+'.add','op':'rescale_add_saturate','inputs':[previous,prefix+'.point']},
            {'name':prefix+'.relu','op':'relu','input':prefix+'.add'}]
        previous=prefix+'.relu'
    spec['graph'] += [{'name':'tail','op':'conv','input':previous},
                      {'name':'output','op':'rescale_add_clip_q14','inputs':['input','tail']}]
    for layer in layers.values():layer.update({'stride':1,'dilation':1,'padding_mode':'zeros'})
    return spec,weights


class IntegerRestore:
    def __init__(self,spec,weights):
        self.spec,self.weights=spec,weights
        self.saturations={};self.accumulator_peaks={}

    def clip(self,name,values):
        self.saturations[name]=int(np.sum((values < -32768)|(values > 32767)))
        return np.clip(values,-32768,32767).astype(np.int16)

    def conv(self,name,x):
        layer=self.spec['layers'][name]
        raw,peak=conv_integer(x,self.weights[name+'.weight'],self.weights[name+'.bias'],
                              layer['groups'],layer['padding'])
        self.accumulator_peaks[name]=peak
        for channel,wf in enumerate(layer['weight_frac']):
            raw[:,channel]=rescale(raw[:,channel],layer['input_frac']+wf,layer['output_frac'])
        return self.clip(name,raw)

    def __call__(self,x,taps=None):
        self.saturations={};self.accumulator_peaks={}
        def record(name,value):
            if taps is not None:taps[name]=value.copy()
            return value
        x=record('input',np.asarray(x,dtype=np.int16))
        z=np.maximum(0,record('stem',self.conv('stem',x)))
        old=self.spec['node_frac']['stem']
        for i in range(self.spec['config']['blocks']):
            name=f'blocks.{i}'
            d=np.maximum(0,record(name+'.depth',self.conv(name+'.depth',z)))
            p=record(name+'.point',self.conv(name+'.point',d))
            f=self.spec['node_frac'][name+'.add']
            add=rescale(z,old,f)+rescale(p,self.spec['node_frac'][name+'.point'],f)
            z=np.maximum(0,record(name+'.add',self.clip(name+'.add',add)))
            old=f
        residual=record('tail',self.conv('tail',z))
        output=x.astype(np.int64)+rescale(residual,self.spec['node_frac']['tail'],14)
        return record('output',np.clip(output,0,16384).astype(np.int16))


def tiled_integer(model,x,core=128):
    if x.ndim!=4 or core<=0:raise ValueError('Expected NCHW and positive core')
    h,w=x.shape[-2:];halo=model.spec['config']['blocks']+1
    result=np.empty_like(x,dtype=np.int16)
    saturation_counts={};peaks={}
    for y in range(0,h,core):
        for col in range(0,w,core):
            top,left=max(0,y-halo),max(0,col-halo)
            y1,x1=min(h,y+core),min(w,col+core)
            patch=x[...,top:min(h,y1+halo),left:min(w,x1+halo)]
            output=model(patch)
            result[...,y:y1,col:x1]=output[...,y-top:y1-top,col-left:x1-left]
            for name,count in model.saturations.items():saturation_counts[name]=saturation_counts.get(name,0)+count
            for name,peak in model.accumulator_peaks.items():peaks[name]=max(peaks.get(name,0),peak)
    model.saturations=saturation_counts;model.accumulator_peaks=peaks
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True);p.add_argument('--checkpoint',required=True)
    p.add_argument('--output',required=True);p.add_argument('--calibration-images',type=int,default=8)
    p.add_argument('--calibration-margin',type=float,default=1.0)
    p.add_argument('--test-images',type=int,default=4);p.add_argument('--crop',type=int,default=96)
    p.add_argument('--golden-split',choices=['val','test'],default='val')
    args=p.parse_args()
    if min(args.calibration_images,args.test_images,args.crop)<=0:raise ValueError('Counts/crop must be positive')
    audit=audit_manifest(args.manifest)
    model,checkpoint=load_model(args.checkpoint,'cpu')
    if checkpoint['task']!=audit['task']:raise ValueError('Task mismatch')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    # Full-image train split only for calibration; test split is never consulted for scales.
    trainset=PairedImages(args.manifest,'train')
    spec,weights=calibrate(model,trainset,args.calibration_images,args.calibration_margin)
    spec.update({'task':audit['task'],'checkpoint_sha256':sha(args.checkpoint),
                 'manifest_sha256':audit['manifest_sha256'],'calibration_split':'train'})
    write_json(output/'integer_spec.json',spec)
    np.savez(output/'integer_weights.npz',**weights)
    layer_folder=output/'layers';layer_folder.mkdir()
    binaries=[]
    for name,value in weights.items():
        dtype='i1' if name.endswith('.weight') else '<i4'
        path=layer_folder/(name+'.bin')
        value.astype(dtype).tofile(path)
        binaries.append({'name':name,'path':path.relative_to(output).as_posix(),
                         'shape':list(value.shape),'dtype':dtype,'bytes':path.stat().st_size,
                         'layout':'OIHW' if name.endswith('.weight') else 'O',
                         'sha256':sha(path)})
    write_json(output/'weight_binaries.json',binaries)
    integer= IntegerRestore(spec,weights)
    tests=PairedImages(args.manifest,args.golden_split)
    rows=[]
    for i in range(min(args.test_images,len(tests))):
        a,b,identity=tests[i]
        a,b=a[:,:args.crop,:args.crop],b[:,:args.crop,:args.crop]
        x=np.rint(a[None].numpy()*16384).astype(np.int16)
        taps={};q=integer(x,taps)
        with torch.inference_mode():fp=model(a[None]).clamp(0,1)
        restored=q[0].astype(np.float32).transpose(1,2,0)/16384
        error=np.abs(restored-array(fp[0]))
        rows.append({'id':identity,'evaluated_shape':list(x.shape),'fp32_vs_integer_mae':float(error.mean()),
                     'fp32_vs_integer_max_abs':float(error.max()),'quality':quality(restored,array(b)),
                     'saturation_counts':dict(integer.saturations),
                     'int32_partial_accumulator_peaks':dict(integer.accumulator_peaks)})
        if i==0:
            np.savez(output/'golden_layer_tensors.npz',**taps)
            gold_folder=output/'golden_layers';gold_folder.mkdir()
            golden=[]
            for name,value in taps.items():
                path=gold_folder/(name+'.bin');value.astype('<i2').tofile(path)
                golden.append({'name':name,'path':path.relative_to(output).as_posix(),
                    'shape':list(value.shape),'dtype':'<i2','layout':'RGB NCHW' if value.shape[1]==3 else 'NCHW',
                    'frac':spec['node_frac'][name],'bytes':path.stat().st_size,'sha256':sha(path),
                    'stage':'conv nodes and block adds are after requant/saturation, before ReLU'})
            write_json(output/'golden_layers.json',golden)
            x.astype('<i2').tofile(output/'input_q14_nchw_le.bin')
            q.astype('<i2').tofile(output/'output_q14_nchw_le.bin')
            write_json(output/'golden_manifest.json',{'shape':list(q.shape),'layout':'RGB NCHW int16 Q14 little-endian',
                'input_sha256':sha(output/'input_q14_nchw_le.bin'),'output_sha256':sha(output/'output_q14_nchw_le.bin')})
    write_json(output/'quantization_results.json',{'task':audit['task'],'data_kind':audit['kind'],
        'scope':f'top-left {args.golden_split} crops only; not full-image quality or FPGA acceptance',
        'checkpoint_step':checkpoint['step'],'identity_control':checkpoint['step']==0,
        'results':rows,'hardware_deployable':'NOT_VERIFIED'})
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
