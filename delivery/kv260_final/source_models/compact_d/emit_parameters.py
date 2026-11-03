"""Emit frozen D parameters from A's manifest, without requantization."""
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_BUNDLE = '2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a'
EXPECTED_PARAMETERS = 'b30ccd73ad10a685db4c591d3c4a31286178bc80be8e65ff3801364458706e57'


def emit(package, output):
    package, output = Path(package), Path(output)
    manifest = json.loads((package/'manifest.json').read_text())
    if manifest['bundle_id'] != EXPECTED_BUNDLE:
        raise ValueError('D bundle differs from the selected A delivery')
    identity = {k:v for k,v in manifest.items() if k != 'bundle_id'}
    canonical = (json.dumps(identity,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    if hashlib.sha256(canonical).hexdigest() != EXPECTED_BUNDLE:
        raise ValueError('Invalid manifest identity')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((package/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Invalid package file '+name)
    graph = json.loads((package/'graph.json').read_text())
    proof = json.loads((package/'overflow_proof.json').read_text())
    if proof['max_signed_accumulator_bits'] != 37:
        raise ValueError('Accumulator certificate changed')
    blob = (package/'parameters.bin').read_bytes()
    if hashlib.sha256(blob).hexdigest() != EXPECTED_PARAMETERS:
        raise ValueError('Parameters differ from A')
    descriptors = {p['name']:p for p in manifest['parameters']}
    lines = ['// Generated from the frozen A manifest; no numerical conversion.',
             '// bundle '+EXPECTED_BUNDLE, '#ifndef D_GENERATED_PARAMETERS_HPP',
             '#define D_GENERATED_PARAMETERS_HPP', '#include <stdint.h>',
             'namespace compact_d {', 'template<int L> struct Layer;']
    layers = []
    for node_index,node in enumerate(graph):
        if node['op'] != 'conv':
            continue
        weight, bias = [descriptors[node[key]] for key in ('weight','bias')]
        co,ci,kh,kw = weight['shape']
        if (kh,kw) != (3,3) or weight['dtype'] != '<i2' or bias['dtype'] != '<i8':
            raise ValueError('Unsupported parameter layout')
        raw_w = blob[weight['offset']:weight['offset']+weight['bytes']]
        raw_b = blob[bias['offset']:bias['offset']+bias['bytes']]
        if hashlib.sha256(raw_w).hexdigest()!=weight['sha256'] or hashlib.sha256(raw_b).hexdigest()!=bias['sha256']:
            raise ValueError('Tensor hash mismatch')
        weights = struct.unpack('<'+'h'*(len(raw_w)//2),raw_w)
        biases = struct.unpack('<'+'q'*co,raw_b)
        l = len(layers)
        initializer = []
        for oc in range(co):
            channels=[]
            for ic in range(ci):
                rows=[]
                for y in range(3):
                    offset=((oc*ci+ic)*3+y)*3
                    rows.append('{'+','.join(map(str,weights[offset:offset+3]))+'}')
                channels.append('{'+','.join(rows)+'}')
            initializer.append('{'+','.join(channels)+'}')
        lines += [f'template<> struct Layer<{l}> {{',
                  f'    static const int node={node_index};',
                  '    static int16_t weight(int co,int ci,int ky,int kx) {',
                  '#pragma HLS INLINE',
                  f'        static const int16_t values[{co}][{ci}][3][3] = {{'+','.join(initializer)+'};',
                  '#pragma HLS ARRAY_PARTITION variable=values complete dim=0',
                  '        return values[co][ci][ky][kx];', '    }',
                  '    static int64_t bias(int co) {', '#pragma HLS INLINE',
                  f'        static const int64_t values[{co}] = {{'+','.join(str(x)+'LL' for x in biases)+'};',
                  '#pragma HLS ARRAY_PARTITION variable=values complete',
                  '        return values[co];', '    }',
                  '    static int shift(int co) {', '#pragma HLS INLINE',
                  f'        static const int values[{co}] = {{'+','.join(map(str,node['requantization_shift']))+'};',
                  '#pragma HLS ARRAY_PARTITION variable=values complete',
                  '        return values[co];', '    }', '};']
        layers.append(dict(layer=l,node=node['id'],trace_index=node_index,cin=ci,cout=co))
    channels = {}
    for node in graph:
        if node['op']=='input':
            channels[node['id']]=3
        elif node['op']=='conv':
            channels[node['id']]=descriptors[node['weight']]['shape'][0]
        else:
            sources=[channels[name] for name in node['inputs']]
            if len(set(sources))!=1:
                raise ValueError('Elementwise channel mismatch')
            channels[node['id']]=sources[0]
    lines += ['static const char* const NODE_NAMES[22] = {'+','.join(json.dumps(n['id']) for n in graph)+'};',
              'static const int NODE_CHANNELS[22] = {'+','.join(str(channels[n['id']]) for n in graph)+'};',
              '} // namespace compact_d', '#endif', '']
    output.write_text('\n'.join(lines),encoding='ascii',newline='\n')
    return dict(bundle_id=EXPECTED_BUNDLE,parameters_sha256=EXPECTED_PARAMETERS,layers=layers,
                generated_sha256=hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(emit(a.package,a.out),indent=2))
