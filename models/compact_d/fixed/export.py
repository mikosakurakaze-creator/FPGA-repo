"""Deterministic D INT16 weights/bias/graph/absolute-accumulator proof export."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from models.compact_d.model import load_model, CHECKPOINT_SHA256
from .numeric import VERSION, canonical, sha256, write_json, PRODUCERS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def rhaz(value):
    value = np.asarray(value,dtype=np.float64)
    return np.copysign(np.floor(np.abs(value)+0.5),value).astype(np.int64)

def build(out, scales):
    out, scales = Path(out),Path(scales)
    if out.exists(): raise FileExistsError('Refuse to overwrite package: '+str(out))
    config = json.loads(scales.read_text())
    model = load_model()
    state = {k:v.detach().cpu().numpy().astype(np.float64) for k,v in model.state_dict().items()}
    graph = copy.deepcopy(json.loads((HERE.parent/'reference_fp32/manifest.json').read_text())['graph'])
    fracs = config['node_fracs']
    if set(fracs) != {n['id'] for n in graph} or fracs['input'] != 14:
        raise ValueError('Invalid D scale graph')
    if any(type(f) is not int or not 0 <= f <= 14 for f in fracs.values()): raise ValueError('Invalid scale')
    blob = bytearray(); parameters=[]; proofs=[]
    def append(name, array, frac, layout):
        blob.extend(b'\0'*((-len(blob))%64))
        raw = array.tobytes()
        parameters.append(dict(name=name,offset=len(blob),bytes=len(raw),dtype=array.dtype.str,shape=list(array.shape),layout=layout,frac=frac,sha256=hashlib.sha256(raw).hexdigest()))
        blob.extend(raw)
    for node in graph:
        node['dtype'] = 'int16-le'
        node['layout'] = 'NCHW'
        if node['op'] == 'input':
            node['range'] = [-16384,16384]
            node['real_range'] = [-1,1]
        node['activation_frac'] = fracs[node['id']]
        if node['op'] == 'conv':
            weight, bias = state[node['weight']], state[node['bias']]
            fin, fout = fracs[node['inputs'][0]],fracs[node['id']]
            wfracs=[]; quant=[]
            for channel in weight:
                # Power-of-two scale and FP64 conversion are deterministic for FP32 tensors.
                f = next(f for f in range(30,-1,-1) if np.max(np.abs(rhaz(channel*(1 << f)))) <= 32767)
                wfracs.append(f); quant.append(rhaz(channel*(1 << f)))
            qw = np.asarray(quant,dtype='<i2')
            qb = np.asarray([int(rhaz(b*(1 << (fin+f)))) for b,f in zip(bias,wfracs)],dtype='<i8')
            append(node['weight'],qw,wfracs,'OIHW');append(node['bias'],qb,[fin+f for f in wfracs],'O')
            node['weight_frac'] = wfracs
            node['requantization_shift'] = [fin+f-fout for f in wfracs]
            channel_proofs=[]
            for co in range(len(qb)):
                l1 = sum(abs(int(v)) for v in qw[co].flat)
                # Applies to all signed INT16 sources and every partial sum, incl zero padding.
                bound = 32768*l1+abs(int(qb[co]))
                bits = bound.bit_length()+1
                if bits > 63: raise OverflowError('Unproved INT64 accumulator')
                channel_proofs.append(dict(channel=co,sum_abs_weight=l1,abs_bias=abs(int(qb[co])),absolute_bound=bound,signed_bits_sufficient=bits))
            proofs.append(dict(node=node['id'],input_abs_bound=32768,channels=channel_proofs,max_signed_bits=max(p['signed_bits_sufficient'] for p in channel_proofs)))
        elif node['op'] == 'relu' and fracs[node['inputs'][0]] != fracs[node['id']]:
            raise ValueError('ReLU scale must be unchanged')
    out.mkdir(parents=True)
    (out/'parameters.bin').write_bytes(blob)
    write_json(out/'graph.json',graph)
    (out/'scales.json').write_bytes(scales.read_bytes())
    proof=dict(formula='B=32768*sum(abs(qweight))+abs(qbias); every partial sum <= B',scope='All signed INT16 inputs to each certified convolution; activation saturation is explicit, not assumed absent',layers=proofs,max_signed_accumulator_bits=max(p['max_signed_bits'] for p in proofs))
    write_json(out/'overflow_proof.json',proof)
    # Portable, whitespace-only oracle descriptor; no inference uses floating point.
    desc=['D_INT16_V1',str(len(graph))]
    for node in graph:
        desc.append(' '.join([node['id'],node['op'],str(fracs[node['id']]),str(len(node.get('inputs',[]))),*node.get('inputs',[])]))
        if node['op'] == 'conv':
            wp,bp = [next(p for p in parameters if p['name']==node[k]) for k in ('weight','bias')]
            desc.append(' '.join(map(str,[wp['shape'][0],wp['shape'][1],wp['offset'],bp['offset'],*node['requantization_shift']])))
    (out/'oracle.txt').write_text('\n'.join(desc)+'\n',encoding='ascii')
    producer_files=[ROOT/name for name in PRODUCERS]
    manifest=dict(format=VERSION,checkpoint_sha256=CHECKPOINT_SHA256,parameter_count=3947,parameter_bytes=len(blob),parameters=parameters,node_order=[n['id'] for n in graph],quantization=dict(activations='signed int16; real=q*2^-F',weights='per-output-channel signed int16',bias='signed int64 at Fin+Fw',accumulator='int64 reference; certified narrower hardware width in overflow_proof',rounding='nearest_ties_away_from_zero',saturation='clamp signed int16 at each conv/affine/add, before ReLU',display='clamp [0,1], multiply255, nearest ties even'),files={p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file()},producer_hashes={p.relative_to(ROOT).as_posix():sha256(p) for p in producer_files})
    manifest['bundle_id']=hashlib.sha256(canonical(manifest)).hexdigest()
    write_json(out/'manifest.json',manifest)
    return manifest

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',required=True);p.add_argument('--scales',default=str(HERE/'scales.json'));a=p.parse_args()
    print(json.dumps({'bundle_id':build(a.out,a.scales)['bundle_id'],'status':'D_INT16_EXPORT_PASS'}))
if __name__=='__main__':main()
