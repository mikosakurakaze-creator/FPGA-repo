"""Cross-check the generated hardware ROM against A data without compiling code.

This is a Python metadata/geometry audit, not execution of the C++ or RTL core.
Only the standard library and the local preflight data reader are used.
"""
import argparse
import json
import math
from pathlib import Path
import random
import re
import struct

from preflight import ROOT, audit, plan, save, sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_rom(path):
    text = path.read_text(encoding='ascii')
    body = text.split('static const Node graph[NODES]={', 1)[1].split('};', 1)[0]
    rows = [[int(v) for v in row.split(',')] for row in re.findall(r'\{([0-9,]+)\}', body)]
    require(len(rows) == 320 and all(len(row) == 14 for row in rows), 'ROM row schema')
    shifts = list(map(int, text.split('static const std::int8_t shifts[]={', 1)[1].split('};', 1)[0].split(',')))
    words = [int(v.rstrip('u'), 0) for v in text.split('static const std::uint32_t bundle[8]={', 1)[1].split('};', 1)[0].split(',')]
    return text, rows, shifts, words


def rom_shapes(rows, height, width):
    shapes = []
    for i, row in enumerate(rows):
        op, a, b, like, channels, frac, kernel, stride, padding = row[:9]
        require(3 <= frac <= 14, 'ROM scale range')
        if i == 0:
            require(op == 0 and channels == 3, 'RGB input')
            shape = (3, height, width)
        else:
            require(a < i and (op not in (5, 6) or b < i), 'ROM topological dependency')
            ca, ih, iw = shapes[a]
            oh, ow = ih, iw
            if op == 1:
                oh, ow = ((v + 2 * padding - kernel) // stride + 1 for v in (ih, iw))
            elif op == 2:
                require(like < i, 'deconv target precedes node')
                _, oh, ow = shapes[like]
                require(all(0 <= actual - ((before - 1) * stride - 2 * padding + kernel) < stride
                            for before, actual in ((ih, oh), (iw, ow))), 'deconv output padding')
            elif op in (3, 4):
                require(ca == channels, 'unary channels')
            elif op == 5:
                require(shapes[a] == shapes[b] and ca == channels, 'add shape')
            elif op == 6:
                require(shapes[b][1:] == (ih, iw) and ca + shapes[b][0] == channels, 'cat shape/order')
            else:
                raise ValueError('unsupported ROM op')
            shape = (channels, oh, ow)
        require(all(v > 0 for v in shape), 'positive tensor shape')
        shapes.append(shape)
    require(shapes[-1] == (3, height, width), 'RGB output')
    return shapes


def check_cache_axis(length_in, length_out, kernel, stride, padding, transpose):
    # Check first, internal and last tiles against the source's declared halo.
    starts = sorted({0, min(16, (length_out - 1) // 16 * 16), (length_out - 1) // 16 * 16})
    spans = []
    for start in starts:
        count = min(16, length_out - start)
        base = (start + padding - kernel + 1) // stride if transpose else start * stride - padding
        span = (start + count - 1 + padding) // stride - base + 1 if transpose else (count - 1) * stride + kernel
        for delta in range(count):
            for tap in range(kernel):
                numerator = start + delta + padding - tap if transpose else (start + delta) * stride - padding + tap
                if transpose and numerator % stride:
                    continue
                sample = numerator // stride if transpose else numerator
                require(0 <= sample - base < span, 'tile read outside cache halo')
                # Out-of-image samples are intentionally zero filled on load.
        spans.append(span)
    return max(spans)


def run():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    m, graph, params, summary = audit(ROOT / 'a_candidate/package')
    source, rows, shifts, bundle = read_rom(ROOT / 'hls/generated_model.hpp')
    require(m['graph_sha256'] in source, 'ROM graph identity')
    require('PARAMETER_BYTES=' + str(m['blob_nbytes']) + 'u' in source, 'ROM parameter size')
    require(struct.pack('<8I', *bundle).hex() == m['identity']['bundle_id'], 'ROM bundle endian/identity')
    indices = {node['id']: i for i, node in enumerate(graph['nodes'])}
    uses = [i for i in range(len(rows))]
    for i, node in enumerate(graph['nodes']):
        for dependency in node['inputs']:
            uses[indices[dependency]] = i
    uses[indices[graph['output']]] = len(rows)
    opcodes = dict(input=0, conv=1, deconv=2, relu=3, mulcoef=4, add=5, cat=6)
    channels, expected_shifts = [], []
    bias_values = 0
    blob = (ROOT / 'a_candidate/package/parameters.bin').read_bytes()
    for i, (node, row) in enumerate(zip(graph['nodes'], rows)):
        inputs = [indices[d] for d in node['inputs']]
        op = node['op']
        if op == 'input':
            c = 3
        elif op in ('conv', 'deconv'):
            c = params[node['weight']][0]['shape'][int(op == 'deconv')]
        elif op == 'cat':
            c = sum(channels[d] for d in inputs)
        else:
            c = channels[inputs[0]]
        expected = [opcodes[op], inputs[0] if inputs else 0, inputs[1] if len(inputs) > 1 else 0,
                    indices[node['output_like']] if 'output_like' in node else 0, c, node['activation_frac'],
                    node.get('kernel_size', [0])[0], node.get('stride', [1])[0], node.get('padding', [0])[0], uses[i],
                    *[params[node[key]][0]['offset'] // 2 if key in node else 0 for key in ('weight', 'bias', 'coefficient')],
                    len(expected_shifts)]
        require(row == expected, 'ROM differs from A manifest: ' + node['id'])
        channels.append(c)
        expected_shifts.extend(node.get('requantization_shift', []))
        if op in ('conv', 'deconv'):
            for channel in range(c):
                at = (row[11] + 4 * channel) * 2
                raw = sum(word << (16 * j) for j, word in enumerate(struct.unpack_from('<4H', blob, at)))
                decoded = raw if raw < 1 << 63 else -1 - ((~raw) & ((1 << 64) - 1))
                require(decoded == params[node['bias']][1][channel], 'bias INT16-word decode')
                require(-(1 << 43) <= decoded < (1 << 43), 'hardware bias bound')
                bias_values += 1
    require(shifts == expected_shifts, 'ROM per-channel shifts')
    sizes = [(4, 4), (4, 1280), (720, 4), (5, 5), (5, 1279), (719, 5), (33, 47),
             (32, 48), (34, 46), (675, 1280), (720, 1280)]
    rng = random.Random(20261024)
    sizes += [(rng.randint(4, 720), rng.randint(4, 1280)) for _ in range(12)]
    memory_checks, cache_checks = [], 0
    for h, w in sizes:
        memory = plan(graph, params, h, w)
        shapes = rom_shapes(rows, h, w)
        require(shapes == [tuple(n['shape']) for n in memory['nodes']], 'ROM/allocator dimensions')
        require(memory['scratch_bytes'] <= 536870912, 'scratch exceeds HLS logical limit')
        for i, row in enumerate(rows):
            if row[0] in (1, 2):
                cin, ih, iw = shapes[row[1]]
                _, oh, ow = shapes[i]
                ch = check_cache_axis(ih, oh, row[6], row[7], row[8], row[0] == 2)
                cw = check_cache_axis(iw, ow, row[6], row[7], row[8], row[0] == 2)
                require(cin * ch * cw <= 128 * 18 * 18, 'input cache capacity')
                cache_checks += 1
        memory_checks.append(dict(height=h, width=w, nodes=len(rows), scratch_bytes=memory['scratch_bytes']))
    golden_checks = []
    for name in ('random', 'black', 'white', 'channel', 'impulse', 'size_4x4', 'size_32x48', 'size_34x46',
                 'foggy001_675x1280', 'random_720x1280'):
        report_path = ROOT / 'a_candidate/golden' / name / 'report.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        require(report['manifest_sha256'] == sha(ROOT / 'a_candidate/package/manifest.json'), 'Golden manifest identity')
        input_shape = report['nodes'][0]['shape']
        require(input_shape == report.get('input_shape', report.get('shape', input_shape)), 'Golden input shape identity')
        shapes = rom_shapes(rows, *input_shape[-2:])
        require(len(report['nodes']) == len(rows), 'Golden nodes')
        for i, node in enumerate(report['nodes']):
            require(node['id'] == graph['nodes'][i]['id'] and node['shape'] == [1, *shapes[i]], 'Golden node shape/order')
            require(node['bytes'] == 2 * math.prod(shapes[i]) and node['activation_frac'] == rows[i][5], 'Golden bytes/scale')
        golden_checks.append(dict(case=name, nodes=320, report_sha256=sha(report_path)))
    top_text = (ROOT / 'hls/frame_top.cpp').read_text(encoding='utf-8')
    depth = int(re.search(r'm_axi port=scratch[^\n]*depth=(\d+)', top_text).group(1))
    limit = int(re.search(r'scratch_bytes>(\d+)u', top_text).group(1))
    require(depth * 2 >= limit, 'co-sim depth smaller than accepted scratch byte limit')
    result = dict(pass_result=True, verification_scope='Python metadata and tile geometry only',
                  inference_executed=False, cpp_executed=False, rtl_executed=False,
                  bundle_id=m['identity']['bundle_id'], nodes=320, shift_entries=len(shifts), bias_values=bias_values,
                  geometry_nodes_checked=cache_checks, memory_checks=memory_checks, golden_metadata=golden_checks,
                  scratch_interface_depth_bytes=depth * 2, maximum_actual_accumulator=summary['maximum_actual_weight_accumulator_bound'],
                  source_sha256={str(p.relative_to(ROOT)): sha(p) for p in
                                 [ROOT / 'hls/generated_model.hpp', ROOT / 'hls/frame_top.cpp', Path(__file__).resolve()]})
    save(args.out, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('memory_checks', 'golden_metadata', 'source_sha256')}, indent=2))


if __name__ == '__main__':
    run()
