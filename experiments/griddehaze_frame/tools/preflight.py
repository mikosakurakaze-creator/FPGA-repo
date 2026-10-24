"""Independent byte/range audit and an executable, aligned DDR allocation plan."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import struct

ROOT = Path(os.environ.get('GDN_PROJECT_ROOT', Path(__file__).resolve().parents[1])).resolve()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')


def audit(root):
    m = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    identity = m['identity']
    payload = dict(identity={k:v for k,v in identity.items() if k!='bundle_id'},
                   quantization=m['quantization'],code_hashes=m['export_code_hashes'],
                   graph_sha256=m['graph_sha256'],blob_sha256=m['blob_sha256'])
    canonical=(json.dumps(payload,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
    assert hashlib.sha256(canonical).hexdigest()==identity['bundle_id']
    assert identity['source_commit']=='481399129614c3e7c8e892b5d52d60173131dda0'
    assert identity['weight_sha256']=='80a8f3aad5fd0ed744f39bd60bda802087fbb48b2fa2ce86261ac443a4dba396'
    for name,expected in m['export_code_hashes'].items():
        assert Path(name).name==name
        assert sha(root.parent/'griddehaze_fixed'/name)==expected
    g = json.loads((root / m['graph_file']).read_text(encoding='utf-8'))
    blob = (root / m['blob_file']).read_bytes()
    assert len(blob) == m['blob_nbytes']
    assert hashlib.sha256(blob).hexdigest() == m['blob_sha256']
    assert sha(root / m['graph_file']) == m['graph_sha256']
    params, end = {}, 0
    for d in m['parameters']:
        assert d['name'] not in params
        fmt, size = {'int8': ('b', 1), 'int16': ('h', 2), 'int64': ('q', 8)}[d['dtype']]
        assert d['offset'] % 64 == 0 and d['offset'] >= end
        assert d['nbytes'] == math.prod(d['shape']) * size
        assert not any(blob[end:d['offset']])
        raw = blob[d['offset']:d['offset'] + d['nbytes']]
        assert len(raw) == d['nbytes'] and hashlib.sha256(raw).hexdigest() == d['sha256']
        params[d['name']] = (d, struct.unpack('<' + fmt * (len(raw) // size), raw))
        end = d['offset'] + d['nbytes']
    assert end == len(blob)
    by_id, records = {}, []
    proof = {p['node']: p for p in m['overflow_proof']}
    for n in g['nodes']:
        assert n['id'] not in by_id and all(x in by_id for x in n['inputs'])
        if n['op'] in ('conv', 'deconv'):
            assert n['groups']==1 and n['dilation']==[1,1]
            d, w = params[n['weight']]
            _, b = params[n['bias']]
            trans = n['op'] == 'deconv'
            assert d['layout'] == ('IOHW' if trans else 'OIHW')
            ci, co = (d['shape'][0], d['shape'][1]) if trans else (d['shape'][1], d['shape'][0])
            taps = math.prod(d['shape'][2:])
            bounds = []
            for o in range(co):
                indices = (i * co * taps + o * taps + k for i in range(ci) for k in range(taps)) if trans else range(o * ci * taps, (o + 1) * ci * taps)
                bound = 32768 * sum(abs(w[i]) for i in indices) + abs(b[o])
                bounds.append(bound)
            assert bounds == n['accumulator_abs_bound'], n['id']
            assert max(bounds) == proof[n['id']]['max_accumulator_abs_bound']
            fin = by_id[n['inputs'][0]]['activation_frac']
            assert n['requantization_shift'] == [fin + f - n['activation_frac'] for f in n['weight_frac']]
            assert params[n['bias']][0]['frac'] == [fin + f for f in n['weight_frac']]
            bound = max(bounds)
            side=10 if trans else 15*n['stride'][0]+n['kernel_size'][0]
            records.append(dict(id=n['id'], op=n['op'], cin=ci, cout=co,
                                maximum_16x16_input_tile_elements=ci*side*side,
                                bound=bound, signed_bits=bound.bit_length()+1,
                                shift_min=min(n['requantization_shift']), shift_max=max(n['requantization_shift'])))
        by_id[n['id']] = n
    max_bound = max(r['bound'] for r in records)
    summary = dict(bundle_id=m['identity']['bundle_id'], manifest_sha256=sha(root/'manifest.json'),
                   parameter_bytes=len(blob), parameter_tensors=len(params), nodes=len(g['nodes']),
                   operations=dict(Counter(n['op'] for n in g['nodes'])),
                   activation_frac_histogram=dict(Counter(n['activation_frac'] for n in g['nodes'])),
                   input_frac=by_id[g['input']]['activation_frac'], output_frac=by_id[g['output']]['activation_frac'],
                   maximum_actual_weight_accumulator_bound=max_bound,
                   minimum_uniform_signed_accumulator_bits=max_bound.bit_length()+1,
                   int32_mac_safe=max_bound <= 2147483647,
                   max_input_channels=max(r['cin'] for r in records), max_output_channels=max(r['cout'] for r in records),
                   maximum_tile_cache_elements=max(r['maximum_16x16_input_tile_elements'] for r in records),
                   convolution_shift_range=[min(r['shift_min'] for r in records), max(r['shift_max'] for r in records)],
                   proof='32768*sum(abs(actual_quantized_weights))+abs(actual_bias), independently recomputed per output channel',
                   layers=records)
    return m, g, params, summary


def plan(g, params, h, w):
    if not (4 <= h <= 720 and 4 <= w <= 1280):
        raise ValueError('Candidate image boundary: 4<=H<=720, 4<=W<=1280')
    records, by_id = [], {}
    for i, n in enumerate(g['nodes']):
        op = n['op']
        args = [by_id[d]['shape'] for d in n['inputs']]
        if op == 'input':
            shape = [3, h, w]
        elif op in ('conv', 'deconv'):
            ws = params[n['weight']][0]['shape']
            co = ws[1] if op == 'deconv' else ws[0]
            if op == 'conv':
                spatial = [(v+2*p-d*(k-1)-1)//s+1 for v,p,d,k,s in zip(args[0][1:],n['padding'],n['dilation'],n['kernel_size'],n['stride'])]
            else:
                spatial = by_id[n['output_like']]['shape'][1:]
                minimum = [(v-1)*s-2*p+d*(k-1)+1 for v,s,p,d,k in zip(args[0][1:],n['stride'],n['padding'],n['dilation'],n['kernel_size'])]
                assert all(0 <= v-base < s for v,base,s in zip(spatial,minimum,n['stride']))
            shape = [co, *spatial]
        elif op == 'cat':
            assert args[0][1:] == args[1][1:]
            shape = [sum(a[0] for a in args), *args[0][1:]]
        else:
            shape = args[0][:]
            if op == 'add':
                assert args[0] == args[1]
        r = dict(index=i, id=n['id'], op=op, shape=shape, bytes=math.prod(shape)*2,
                 birth=i, last_use=i, activation_frac=n['activation_frac'], inputs=n['inputs'])
        for dep in n['inputs']:
            by_id[dep]['last_use'] = i
        records.append(r)
        by_id[n['id']] = r
    by_id[g['output']]['last_use'] = len(records)
    # Strict out-of-place allocation: no input is freed until the producing op ends.
    # Shape dependencies carry metadata only. No graph-wide halo is assumed.
    active, free, end = [], [], 0
    peak_live = max(sum(r['bytes'] for r in records if r['birth'] <= i <= r['last_use']) for i in range(len(records)))
    for r in records:
        if r['id'] in (g['input'], g['output']):
            r.update(region='input' if r['id']==g['input'] else 'output', offset=0, allocation_bytes=(r['bytes']+63)//64*64)
            continue
        still = []
        for a in active:
            if a['last_use'] < r['birth']:
                free.append((a['offset'],a['allocation_bytes']))
            else:
                still.append(a)
        active = still
        merged = []
        for start,size in sorted(free):
            if merged and merged[-1][0]+merged[-1][1] == start:
                merged[-1]=(merged[-1][0],merged[-1][1]+size)
            else:
                merged.append((start,size))
        free = merged
        size = (r['bytes']+63)//64*64
        candidates = [(length,start,j) for j,(start,length) in enumerate(free) if length>=size]
        if candidates:
            length,start,j = min(candidates)
            free.pop(j)
            if length>size: free.append((start+size,length-size))
        else:
            start=end
            end+=size
        r.update(region='scratch',offset=start,allocation_bytes=size)
        active.append(r)
    scratch=[r for r in records if r['region']=='scratch']
    for j,a in enumerate(scratch):
        assert a['offset'] % 64 == 0 and a['offset']+a['allocation_bytes']<=end
        for b in scratch[j+1:]:
            live_overlap=max(a['birth'],b['birth'])<=min(a['last_use'],b['last_use'])
            address_overlap=max(a['offset'],b['offset'])<min(a['offset']+a['allocation_bytes'],b['offset']+b['allocation_bytes'])
            assert not (live_overlap and address_overlap),(a['id'],b['id'])
    conv_macs=0
    for n,r in zip(g['nodes'],records):
        if n['op']=='conv':
            ws=params[n['weight']][0]['shape']
            conv_macs+=math.prod(r['shape'])*ws[1]*math.prod(ws[2:])
        elif n['op']=='deconv':
            ws=params[n['weight']][0]['shape']
            conv_macs+=math.prod(by_id[n['inputs'][0]]['shape'])*ws[1]*math.prod(ws[2:])
    feature_traffic=sum(r['bytes']+sum(by_id[d]['bytes'] for d in r['inputs']) for r in records if r['op']!='input')
    return dict(kind='static_verified_address_plan_not_board_allocation', height=h,width=w,node_count=len(records),
                alignment_bytes=64,scratch_bytes=end,peak_live_logical_bytes=peak_live,
                input_bytes=by_id[g['input']]['bytes'],output_bytes=by_id[g['output']]['bytes'],
                input_dma_slot_bytes=by_id[g['input']]['allocation_bytes'],output_dma_slot_bytes=by_id[g['output']]['allocation_bytes'],
                macs_including_deconv_edge_products=conv_macs,
                materialized_single_read_write_feature_traffic_lower_bound_bytes=feature_traffic,
                lifetime_address_overlap_check=True,inference_executed=False,
                notes=['All 320 nodes materialized, including cat and rescaling boundaries.',
                       '64-byte aligned best-fit with coalescing; no in-place writes.',
                       'Scratch excludes input/output/weights and on-chip tile accumulators.',
                       'Offsets are relative; DMA base/contiguity/CMA availability still require target platform allocation.',
                       'Traffic is a lower bound: tiling may reread input/weights. Not a measured bandwidth or latency.'],nodes=records)


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--candidate',type=Path,default=ROOT/'a_candidate')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    summaries={}
    for variant in ('package','alternative_int8'):
        m,g,params,summary=audit(a.candidate/variant)
        summaries[variant]=summary
        save(a.out/(variant+'_audit.json'),summary)
        if variant=='package':
            for h,w in ((4,4),(32,48),(33,47),(34,46),(675,1280),(720,1280)):
                report=plan(g,params,h,w)
                report['bundle_id']=m['identity']['bundle_id']
                save(a.out/f'memory_{h}x{w}.json',report)
                print(json.dumps({k:v for k,v in report.items() if k not in ('nodes','notes')}))
    print(json.dumps({k:{q:v for q,v in s.items() if q not in ('layers','activation_frac_histogram')} for k,s in summaries.items()},indent=2))


if __name__=='__main__':
    main()
