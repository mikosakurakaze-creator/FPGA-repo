"""Reproducible host entry points. Run from repository root with python -m."""
import argparse
from pathlib import Path
import json
import platform
import sys
import time
import numpy as np
from .io import (write_json, sha256, save_tensor, read_tensor, input_rgb8,
                 display_rgb8, difference)


def load_graph(package):
    p = Path(package)
    m = json.loads((p / 'manifest.json').read_text())
    return m, json.loads((p / m['graph_file']).read_text())


def float_graph(model, graph, x):
    import torch
    values = {graph['input']: torch.from_numpy(x)}
    with torch.inference_mode():
        for n in graph['nodes']:
            op = n['op']
            if op == 'input':
                continue
            args = [values[i] for i in n['inputs']]
            if op == 'conv':
                y = model.get_submodule(n['module'])(args[0])
            elif op == 'deconv':
                y = model.get_submodule(n['module'])(args[0], output_size=values[n['output_like']].shape[-2:])
            elif op == 'relu':
                y = torch.relu(args[0])
            elif op == 'cat':
                y = torch.cat(args, dim=1)
            elif op == 'add':
                y = args[0] + args[1]
            elif op == 'mulcoef':
                i, j, branch = n['source_index']
                c = model.coefficient[i, j, branch, :args[0].shape[1]][None, :, None, None]
                y = c * args[0]
            else:
                raise ValueError(op)
            values[n['id']] = y
    return {k: v.numpy() for k, v in values.items()}


def run_case(package, source, out, rgb, backend='numpy', float_reference=True):
    from .integer import run
    out = Path(out)
    if out.exists():
        raise FileExistsError('Refuse to overwrite evidence: ' + str(out))
    out.mkdir(parents=True)
    manifest, graph = load_graph(package)
    frac = manifest['quantization']['activation_frac']
    node_fracs = {n['id']: n.get('activation_frac', frac) for n in graph['nodes']}
    output_frac = node_fracs[graph['output']]
    save_tensor(out, 'rgb8', rgb)
    x = input_rgb8(rgb, frac)
    input_meta = save_tensor(out, 'input', x)
    input_meta['activation_frac'] = frac
    write_json(out / 'input.json', input_meta)
    float_values = None
    if float_reference:
        from .export import load_official
        import torch
        torch.set_num_threads(2)
        model = load_official(source)
        xf = (rgb.transpose(2, 0, 1)[None].astype(np.float32) / np.float32(255) - np.float32(.5)) / np.float32(.5)
        float_values = float_graph(model, graph, xf)
        with torch.inference_mode():
            original = model(torch.from_numpy(xf)).numpy()
        dag = float_values[graph['output']]
        diff = difference(original, dag)
        write_json(out / 'float_graph_vs_official.json', diff)
        if not diff['exact']:
            raise AssertionError('Float graph differs from official network')
        save_tensor(out, 'fp32_output', original)
        from PIL import Image
        Image.fromarray(np.floor(np.clip(original[0].transpose(1, 2, 0), 0, 1) * 255 + .5).astype(np.uint8)).save(out / 'fp32.png')
    nodes = []
    def observer(node, value, stats):
        node_id = node['id'] if isinstance(node, dict) else node
        item = {'id': node_id, **stats, **save_tensor(out / 'nodes', node_id.replace('.', '_'), value)}
        if float_values is not None and node_id in float_values:
            f = float_values[node_id].astype(np.float64)
            d = value.astype(np.float64) / (1 << node_fracs[node_id]) - f
            item['vs_fp32'] = {'max_abs_error': float(np.abs(d).max()), 'mean_abs_error': float(np.abs(d).mean()),
                               'fp32_min': float(f.min()), 'fp32_max': float(f.max())}
        nodes.append(item)
    start = time.perf_counter()
    y = run(package, x, backend=backend, observer=observer)
    elapsed = time.perf_counter() - start
    final = save_tensor(out, 'output', y)
    final['activation_frac'] = output_frac
    write_json(out / 'output.json', final)
    rgbout = display_rgb8(y, output_frac)
    save_tensor(out, 'display_rgb8', rgbout)
    from PIL import Image
    Image.fromarray(rgb).save(out / 'input.png')
    Image.fromarray(rgbout).save(out / 'integer.png')
    report = {'backend': backend, 'elapsed_seconds': elapsed, 'input_shape': list(x.shape),
              'manifest_sha256': sha256(Path(package) / 'manifest.json'), 'output': final, 'nodes': nodes,
              'python': sys.version, 'platform': platform.platform(), 'numpy': np.__version__,
              'command': sys.argv, 'float_reference': float_reference, 'hardware_test': False}
    if float_values is not None:
        f = float_values[graph['output']].astype(np.float64)
        d = y.astype(np.float64) / (1 << output_frac) - f
        report['output_vs_fp32'] = {'mean_abs_error': float(np.abs(d).mean()), 'max_abs_error': float(np.abs(d).max())}
    write_json(out / 'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('nodes', 'python', 'platform', 'command')}))
    return report


def compare_dirs(expected, actual, report):
    expected, actual = Path(expected), Path(actual)
    results, errors = [], []
    try:
        er = json.loads((expected / 'report.json').read_text(encoding='utf-8'))
        ar = json.loads((actual / 'report.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        write_json(report, {'exact': False, 'identity_equal': False, 'errors': [str(error)], 'comparisons': []})
        return False
    # The report is emitted in DAG execution order. Lexically sorted filenames
    # can incorrectly identify a late branch as the first divergent node.
    try:
        expected_ids = [n['id'] for n in er['nodes']]
        actual_ids = [n['id'] for n in ar['nodes']]
        node_files = [Path('nodes') / Path(n['file']).with_suffix('.json') for n in er['nodes']]
        expected_manifest = er['manifest_sha256']
        actual_manifest = ar['manifest_sha256']
    except (KeyError, TypeError, ValueError) as error:
        write_json(report, {'exact': False, 'identity_equal': False, 'errors': ['Malformed run metadata: ' + str(error)], 'comparisons': []})
        return False
    if not expected_ids:
        errors.append('Empty expected node coverage')
    if len(set(expected_ids)) != len(expected_ids) or len(set(actual_ids)) != len(actual_ids):
        errors.append('Duplicate node IDs')
    if set(expected_ids) != set(actual_ids):
        errors.append('Node ID coverage mismatch')
    if {n['id']: n.get('file') for n in er['nodes']} != {n['id']: n.get('file') for n in ar['nodes']}:
        errors.append('Node ID to raw file mapping mismatch')
    expected_coverage = {str(p.relative_to(expected)) for p in expected.glob('nodes/*.json')}
    actual_coverage = {str(p.relative_to(actual)) for p in actual.glob('nodes/*.json')}
    declared_coverage = {str(p) for p in node_files}
    if expected_coverage != declared_coverage or actual_coverage != declared_coverage:
        errors.append('Node metadata file coverage mismatch')
    for relative in [Path('input.json')] + node_files + [Path('output.json'), Path('display_rgb8.json')]:
        e = expected / relative
        a = actual / relative
        hashes = {}
        try:
            em = json.loads(e.read_text(encoding='utf-8'))
            am = json.loads(a.read_text(encoding='utf-8'))
            hashes = {'expected_raw_sha256': em['sha256'], 'actual_raw_sha256': am['sha256']}
            result = difference(read_tensor(e), read_tensor(a))
        except (OSError, ValueError, KeyError, TypeError) as error:
            result = {'exact': False, 'reason': str(error)}
        results.append({'tensor': str(relative), **hashes, **result})
    input_equal = bool(results) and results[0]['exact']
    identity_equal = expected_manifest == actual_manifest and input_equal
    success = bool(results) and identity_equal and not errors and all(r['exact'] for r in results)
    write_json(report, {'exact': success, 'identity_equal': identity_equal, 'comparisons': results,
                        'errors': errors,
                        'first_different_tensor': next((r for r in results if not r['exact']), None)})
    return success


def main():
    p = argparse.ArgumentParser(__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run')
    r.add_argument('--package', required=True); r.add_argument('--source', required=True)
    r.add_argument('--out', required=True); r.add_argument('--image')
    r.add_argument('--pattern', choices=['black', 'white', 'channel', 'impulse', 'random'], default='random')
    r.add_argument('--height', type=int, default=33); r.add_argument('--width', type=int, default=47)
    r.add_argument('--backend', default='numpy'); r.add_argument('--no-float', action='store_true')
    c = sub.add_parser('compare'); c.add_argument('expected'); c.add_argument('actual'); c.add_argument('--report', required=True)
    a = p.parse_args()
    if a.command == 'compare':
        raise SystemExit(0 if compare_dirs(a.expected, a.actual, a.report) else 1)
    if a.image:
        from PIL import Image
        rgb = np.asarray(Image.open(a.image).convert('RGB'))
    else:
        rgb = np.zeros((a.height, a.width, 3), dtype=np.uint8)
        if a.pattern == 'white': rgb[:] = 255
        elif a.pattern == 'channel': rgb[:] = [0, 127, 255]
        elif a.pattern == 'impulse':
            rgb[0, 0] = [255, 127, 0]; rgb[-1, -1] = [0, 255, 127]
        elif a.pattern == 'random': rgb = np.random.default_rng(20261024).integers(0, 256, rgb.shape, dtype=np.uint8)
    run_case(a.package, a.source, a.out, rgb, a.backend, not a.no_float)


if __name__ == '__main__':
    main()
