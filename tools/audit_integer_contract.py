"""Check frozen header shapes, integer shifts and conservative INT32 bounds.

This checks source arithmetic assumptions, not backend netlist equivalence.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    models = {}
    for task in ('derain', 'dehaze'):
        path = root / f'experiments/stream_frame/src/params_{task}.h'
        source = path.read_text()
        body = source.split('static const ModelParams ', 1)[1].split('=', 1)[1].split(';', 1)[0]
        layers, add_frac, tail_frac = ast.literal_eval(body.replace('{', '[').replace('}', ']'))
        if len(layers) != 12 or len(add_frac) != 5 or tail_frac != layers[-1][6]:
            raise RuntimeError('Unexpected frozen model dimensions/fractions')
        records = []
        for index, layer in enumerate(layers):
            ci, co, kernel, groups, padding, input_frac, output_frac, weight_frac, weights, bias = layer
            shape = ((3, 8, 3, 1, 1) if index == 0 else (8, 3, 1, 1, 0) if index == 11
                     else (8, 8, 3, 8, 1) if index % 2 else (8, 8, 1, 1, 0))
            if tuple(layer[:5]) != shape or len(weight_frac) != co or len(bias) != co:
                raise RuntimeError('Frozen layer shape changed')
            per_channel = ci // groups * kernel * kernel
            if len(weights) != co * per_channel or any(w < -128 or w > 127 for w in weights):
                raise RuntimeError('INT8 weight dimensions/range invalid')
            shifts = [input_frac + f - output_frac for f in weight_frac]
            if any(s < 0 or s > 30 for s in shifts):
                raise RuntimeError('Source rne shift contract violated')
            bound = max(32768 * sum(abs(w) for w in weights[c * per_channel:(c + 1) * per_channel]) + abs(bias[c])
                        for c in range(co))
            if bound > 2147483647:
                raise RuntimeError('Conservative full-INT16 MAC bound exceeds INT32')
            expected_input_frac = (14 if index == 0 else layers[0][6] if index == 1
                                   else add_frac[index // 2 - 1] if index % 2 else layers[index - 1][6])
            if input_frac != expected_input_frac:
                raise RuntimeError('Adjacent source activation fractions disagree')
            records.append({'layer': index, 'int32_absolute_mac_bound': bound, 'right_shifts': shifts})
        residual_bounds = []
        for block in range(5):
            skip_frac = layers[0][6] if block == 0 else add_frac[block - 1]
            point_frac = layers[2 * block + 2][6]
            left_shifts = [max(0, add_frac[block] - f) for f in (skip_frac, point_frac)]
            if any(s > 30 for s in left_shifts):
                raise RuntimeError('Residual rescale shift exceeds source contract')
            bound = sum(32768 << s for s in left_shifts)
            if bound > 2147483647:
                raise RuntimeError('Residual rescale/add can exceed INT32')
            residual_bounds.append(bound)
        tail_bound = 32768 + (32768 << max(0, 14 - tail_frac))
        if tail_bound > 2147483647:
            raise RuntimeError('Tail add can exceed INT32')
        models[task] = {'header_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'layers': records, 'residual_absolute_bounds': residual_bounds,
                        'tail_absolute_bound': tail_bound}
    report = {'pass': True, 'scope': 'Frozen source INT8 weights, full signed INT16 node range and INT32 arithmetic bounds only; not optimized hardware equivalence',
              'models': models}
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('WEATHER_SOURCE_INTEGER_CONTRACT_PASS models=2 layers=24')


if __name__ == '__main__':
    main()
