"""Report fixed candidates on held-out center64 patches; never recalibrate."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import sys
import time
import numpy as np
from PIL import Image
from .cli import float_graph
from .export import load_official
from .integer import load_package, run
from .io import difference, display_rgb8, input_rgb8, save_tensor, sha256, write_json


def numerical_error(expected, actual):
    difference = actual.astype(np.float64)-expected.astype(np.float64)
    return {'mean_abs_error': float(np.abs(difference).mean()),
            'max_abs_error': float(np.abs(difference).max()),
            'mean_signed_error': float(difference.mean()),
            'per_channel_mean_signed_error_rgb': difference.mean(axis=(0, 2, 3)).tolist()}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--source', required=True); p.add_argument('--split', required=True)
    p.add_argument('--package', required=True); p.add_argument('--alternative', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    import torch
    torch.set_num_threads(2)
    packages = {}
    for label, directory in (('primary', a.package), ('alternative', a.alternative)):
        manifest, graph, _ = load_package(directory)
        packages[label] = {'path': directory, 'manifest': manifest, 'graph': graph,
                           'manifest_sha256': sha256(Path(directory)/'manifest.json')}
    split = json.loads(Path(a.split).read_text(encoding='utf-8'))
    selected = split['validation']
    if len(selected) != 15 or len({i['sha256'] for i in selected}) != 15:
        raise ValueError('Expected exactly 15 distinct held-out validation images')
    calibration_sha = {i['sha256'] for i in split['calibration']}
    if any(i['sha256'] in calibration_sha for i in selected):
        raise ValueError('Validation/calibration source SHA leakage')
    if any(PurePosixPath(i['member']).name.casefold() == 'foggy-001.jpg' for i in split['calibration']):
        raise ValueError('Approved image leaked into calibration')
    model = load_official(a.source)
    cases, aggregates = [], {}
    start = time.perf_counter()
    for index, item in enumerate(selected):
        if sha256(item['path']) != item['sha256']:
            raise ValueError('Validation source image SHA mismatch: '+item['member'])
        with Image.open(item['path']) as image:
            full = np.asarray(image.convert('RGB'))
        h, w = full.shape[:2]
        ch, cw = min(h, 64), min(w, 64)
        y, x = (h-ch)//2, (w-cw)//2
        rgb = np.ascontiguousarray(full[y:y+ch, x:x+cw])
        case_dir = out/(f"{index:02d}_{item['archive']}_"+PurePosixPath(item['member']).stem)
        case_dir.mkdir()
        save_tensor(case_dir, 'input_rgb8', rgb)
        Image.fromarray(rgb).save(case_dir/'input.png')
        xf = (rgb.transpose(2, 0, 1)[None].astype(np.float32)/np.float32(255)-np.float32(.5))/np.float32(.5)
        graph = packages['primary']['graph']
        floats = float_graph(model, graph, xf)
        with torch.inference_mode():
            official = model(torch.from_numpy(xf)).numpy()
        float_check = difference(official, floats[graph['output']])
        if not float_check['exact']:
            raise AssertionError('FP32 explicit graph differs from pinned official forward')
        fp32_meta = save_tensor(case_dir, 'fp32_output', official)
        fp32_rgb8 = np.floor(np.clip(official[0].transpose(1, 2, 0), 0, 1)*255+.5).astype(np.uint8)
        save_tensor(case_dir, 'fp32_display_rgb8', fp32_rgb8)
        Image.fromarray(fp32_rgb8).save(case_dir/'fp32.png')
        case = {'source': item, 'original_shape_hwc': list(full.shape), 'crop_yxhw': [y, x, ch, cw],
                'fp32_graph_vs_official': float_check, 'fp32_output': fp32_meta,
                'candidates': {}}
        real_outputs = {}
        for label, package in packages.items():
            manifest, graph = package['manifest'], package['graph']
            fracs = {n['id']: n.get('activation_frac', manifest['quantization']['activation_frac']) for n in graph['nodes']}
            q = input_rgb8(rgb, fracs[graph['input']])
            folder = case_dir/label
            input_meta = save_tensor(folder, 'input', q)
            nodes = []
            def observer(ident, values, statistics):
                raw = np.ascontiguousarray(values, dtype='<i2').tobytes()
                entry = {'id': ident, **statistics, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                if ident in floats:
                    entry['vs_fp32'] = numerical_error(floats[ident], values.astype(np.float64)/(1 << fracs[ident]))
                nodes.append(entry)
            inference_start = time.perf_counter()
            result = run(package['path'], q, backend='numpy', observer=observer)
            seconds = time.perf_counter()-inference_start
            final_meta = save_tensor(folder, 'output', result)
            final_meta['activation_frac'] = fracs[graph['output']]
            write_json(folder/'output.json', final_meta)
            input_meta['activation_frac'] = fracs[graph['input']]
            write_json(folder/'input.json', input_meta)
            display = display_rgb8(result, fracs[graph['output']])
            display_meta = save_tensor(folder, 'display_rgb8', display)
            Image.fromarray(display).save(folder/'integer.png')
            real = result.astype(np.float64)/(1 << fracs[graph['output']])
            real_outputs[label] = real
            metrics = numerical_error(official, real)
            statistics = {'manifest_sha256': package['manifest_sha256'],
                          'bundle_id': manifest['identity']['bundle_id'],
                          'weight_bits': manifest['quantization']['weight_bits'],
                          'input': input_meta, 'output': final_meta, 'display': display_meta,
                          'output_vs_fp32': metrics, 'elapsed_seconds': seconds,
                          'saturation_count': sum(n['saturated_low']+n['saturated_high'] for n in nodes),
                          'nodes': nodes}
            write_json(folder/'report.json', statistics)
            case['candidates'][label] = {k: v for k, v in statistics.items() if k != 'nodes'}
            aggregate = aggregates.setdefault(label, {'case_mae': [], 'max_abs_error': 0.0,
                'channel_bias_sum': np.zeros(3), 'saturation_count': 0, 'nodes': {}})
            aggregate['case_mae'].append(metrics['mean_abs_error'])
            aggregate['max_abs_error'] = max(aggregate['max_abs_error'], metrics['max_abs_error'])
            aggregate['channel_bias_sum'] += metrics['per_channel_mean_signed_error_rgb']
            aggregate['saturation_count'] += statistics['saturation_count']
            for node in nodes:
                totals = aggregate['nodes'].setdefault(node['id'], {'saturated_low': 0, 'saturated_high': 0})
                for key in totals:
                    totals[key] += node[key]
        case['primary_vs_alternative_real_output'] = numerical_error(real_outputs['alternative'], real_outputs['primary'])
        write_json(case_dir/'report.json', case)
        cases.append(case)
        print(json.dumps({'case': index+1, 'member': item['member'],
                          'metrics': {k: v['output_vs_fp32'] for k, v in case['candidates'].items()},
                          'saturations': {k: v['saturation_count'] for k, v in case['candidates'].items()}}), flush=True)
    summary = {}
    for label, aggregate in aggregates.items():
        summary[label] = {'weight_bits': packages[label]['manifest']['quantization']['weight_bits'],
            'mean_case_mae': float(np.mean(aggregate['case_mae'])),
            'max_case_mae': float(max(aggregate['case_mae'])), 'max_abs_error': aggregate['max_abs_error'],
            'per_channel_mean_signed_error_rgb': (aggregate['channel_bias_sum']/len(cases)).tolist(),
            'saturation_count': aggregate['saturation_count'], 'per_node_saturations': aggregate['nodes']}
    report = {'kind': 'held_out_validation_center64_patch_report', 'case_count': len(cases),
              'split_sha256': sha256(a.split), 'script_sha256': sha256(__file__),
              'packages': {label: {'path': str(Path(pkg['path']).resolve()),
                 'manifest_sha256': pkg['manifest_sha256'], 'bundle_id': pkg['manifest']['identity']['bundle_id']}
                 for label, pkg in packages.items()}, 'summary': summary, 'cases': cases,
              'elapsed_seconds': time.perf_counter()-start, 'command': sys.argv,
              'environment': {'python': sys.version, 'platform': platform.platform(),
                              'numpy': np.__version__, 'torch': torch.__version__},
              'hardware_test': False, 'calibration_or_tuning_performed': False,
              'limitations': ['Each source image is center-cropped to at most64x64 with no resizing.',
                              'These are patch errors against FP32; no full-image quality or restoration-ground-truth claim.',
                              'Validation/calibration exact-byte membership disjoint; scene and near-duplicate independence unverified.',
                              'No official quality threshold or visual acceptance is asserted.',
                              'Per-node raw hashes/statistics retained; full node raw Golden is provided by separate delivery vectors.']}
    write_json(out/'report.json', report)
    print(json.dumps({'case_count': len(cases), 'summary': {k: {n: v for n, v in s.items() if n != 'per_node_saturations'} for k, s in summary.items()}}, indent=2))


if __name__ == '__main__':
    main()
