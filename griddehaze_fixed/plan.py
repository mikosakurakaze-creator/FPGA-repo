"""Static full-image shapes/lifetimes. No inference, DDR addresses or HW claims."""
import argparse
import json
import math
from pathlib import Path
from .io import sha256, write_json


def shape_plan(package, height, width):
    package = Path(package)
    if height < 4 or width < 4:
        raise ValueError('Supported reference dimensions are H,W >= 4')
    manifest_path = package / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    graph_path = package / manifest['graph_file']
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
    if sha256(graph_path) != manifest['graph_sha256']:
        raise ValueError('Graph identity mismatch')
    parameters = {p['name']: p for p in manifest['parameters']}
    shapes, records, by_id = {}, [], {}
    nodes = graph['nodes']
    for index, node in enumerate(nodes):
        name, op = node['id'], node['op']
        if name in shapes:
            raise ValueError('Duplicate node ID: ' + name)
        dependencies = node.get('inputs', [])
        if any(d not in shapes for d in dependencies):
            raise ValueError('Unresolved tensor dependency: ' + name)
        args = [shapes[d] for d in dependencies]
        output_padding = None
        if op == 'input':
            if index != 0 or name != graph['input'] or args:
                raise ValueError('Invalid input node')
            shape = (1, 3, height, width)
        elif op in ('conv', 'deconv'):
            if len(args) != 1 or node.get('groups', 1) != 1:
                raise ValueError('Only single-input groups=1 convolution supported')
            batch, ci, hi, wi = args[0]
            ws = parameters[node['weight']]['shape']
            co, expected_ci = (ws[0], ws[1]) if op == 'conv' else (ws[1], ws[0])
            if ci != expected_ci:
                raise ValueError('Weight/input channel mismatch: ' + name)
            kernel, stride, padding, dilation = (node[k] for k in ('kernel_size', 'stride', 'padding', 'dilation'))
            if tuple(kernel) != tuple(ws[-2:]):
                raise ValueError('Kernel shape mismatch: ' + name)
            if op == 'conv':
                spatial = tuple((v + 2*p - d*(k-1)-1)//s+1
                                for v, p, d, k, s in zip((hi, wi), padding, dilation, kernel, stride))
            else:
                target = node['output_like']
                if target not in shapes:
                    raise ValueError('Unresolved output_like shape dependency: ' + name)
                spatial = shapes[target][-2:]
                minimum = tuple((v-1)*s-2*p+d*(k-1)+1
                                for v, p, d, k, s in zip((hi, wi), padding, dilation, kernel, stride))
                output_padding = [t-m for t, m in zip(spatial, minimum)]
                if any(o < 0 or o >= s for o, s in zip(output_padding, stride)):
                    raise ValueError('Unreachable deconvolution output_size: ' + name)
            shape = (batch, co, *spatial)
        elif op == 'cat':
            if not args or node.get('axis', 1) != 1 or any(a[0] != args[0][0] or a[2:] != args[0][2:] for a in args):
                raise ValueError('Invalid channel concat: ' + name)
            shape = (args[0][0], sum(a[1] for a in args), *args[0][2:])
        elif op == 'add':
            if len(args) != 2 or args[0] != args[1]:
                raise ValueError('Add shape mismatch: ' + name)
            shape = args[0]
        elif op in ('relu', 'mulcoef'):
            if len(args) != 1:
                raise ValueError('Expected one tensor input: ' + name)
            shape = args[0]
            if op == 'mulcoef' and shape[1] != node['channels']:
                raise ValueError('Coefficient channel mismatch: ' + name)
        else:
            raise ValueError('Unknown op: ' + op)
        if any(d <= 0 for d in shape):
            raise ValueError('Nonpositive tensor extent: ' + name)
        shapes[name] = tuple(shape)
        record = {'id': name, 'op': op, 'shape': list(shape), 'bytes': 2*math.prod(shape),
                  'birth': index, 'last_use': index, 'shape_last_use': index,
                  'tensor_dependencies': dependencies, 'shape_dependencies': []}
        for dep in dependencies:
            by_id[dep]['last_use'] = index
        if op == 'deconv':
            target = node['output_like']
            record['shape_dependencies'] = [target]
            record['output_padding'] = output_padding
            by_id[target]['shape_last_use'] = index
        records.append(record)
        by_id[name] = record
    if graph['output'] not in by_id:
        raise ValueError('Missing graph output')
    by_id[graph['output']]['last_use'] = len(nodes)
    peak, peak_node, peak_full, peak_full_node = 0, None, 0, None
    for index, record in enumerate(records):
        # New output coexists with input tensors through this execution step.
        # A shape-only dependency retains metadata, not a feature allocation.
        live = sum(r['bytes'] for r in records if r['birth'] <= index <= r['last_use'])
        record['live_materialized_int16_bytes'] = live
        if live > peak:
            peak, peak_node = live, record['id']
        if record['op'] in ('conv', 'deconv'):
            n, c, _, w = record['shape']
            record['full_output_int64_accumulator_bytes'] = record['bytes']*4
            record['one_row_int64_accumulator_bytes'] = n*c*w*8
            if live + record['bytes']*4 > peak_full:
                peak_full, peak_full_node = live + record['bytes']*4, record['id']
    return {'kind': 'static_shape_and_logical_lifetime_only', 'inference_executed': False,
            'manifest_sha256': sha256(manifest_path), 'graph_sha256': sha256(graph_path),
            'input_shape': list(shapes[graph['input']]), 'output_shape': list(shapes[graph['output']]),
            'node_count': len(records), 'activation_bytes': 2,
            'all_materialized_int16_bytes_without_reuse': sum(r['bytes'] for r in records),
            'peak_live_materialized_int16_bytes': peak, 'peak_live_at_node': peak_node,
            'peak_live_int16_plus_full_output_int64_accumulator_bytes': peak_full,
            'peak_live_plus_full_accumulator_at_node': peak_full_node,
            'assumptions': [
                'Sequential graph order, independently materialized cat and all op outputs.',
                'Free tensor after its last value consumer; retain shape metadata independently.',
                'Output allocated before releasing inputs; no inplace, alias, lane padding or fragmentation.',
                'INT64 accumulator figures are temporary alternatives, not INT16 feature tensors.',
                'Not measured Python RAM: padding, promoted inputs/weights and backend temporaries are excluded.',
                'Not a hardware DDR allocation or peak scratch approval; B must plan alignment and buffering.'
            ], 'nodes': records}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--package', required=True)
    p.add_argument('--height', type=int, required=True)
    p.add_argument('--width', type=int, required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    if Path(a.out).exists():
        raise FileExistsError('Refuse to overwrite evidence: ' + a.out)
    report = shape_plan(a.package, a.height, a.width)
    write_json(a.out, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('nodes', 'assumptions')}))


if __name__ == '__main__':
    main()
