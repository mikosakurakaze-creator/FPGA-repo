"""Full-size integer Golden: raw final outputs, all-node hashes/statistics.

Small cases retain every raw intermediate using cli.py; large cases stream node
hashes to bound disk use. No crop, resize, tiling of network or float surrogate.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
from .integer import run
from .io import input_rgb8, display_rgb8, save_tensor, sha256, write_json
from .cli import load_graph


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--package', required=True); p.add_argument('--source', required=True)
    p.add_argument('--image'); p.add_argument('--height', type=int); p.add_argument('--width', type=int)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    if a.image:
        rgb = np.asarray(Image.open(a.image).convert('RGB'))
    else:
        rgb = np.random.default_rng(20261024).integers(0, 256, (a.height, a.width, 3), dtype=np.uint8)
    m, graph = load_graph(a.package)
    q = input_rgb8(rgb, m['quantization']['activation_frac'])
    save_tensor(out, 'rgb8', rgb)
    imeta = save_tensor(out, 'input', q)
    imeta['activation_frac'] = m['quantization']['activation_frac']
    write_json(out / 'input.json', imeta)
    nodes = []
    def observe(name, value, stats):
        nodes.append({'id': name, **stats, 'sha256': hashlib.sha256(value.astype('<i2', copy=False).tobytes()).hexdigest(),
                      'bytes': value.nbytes, 'raw_intermediate_saved': False})
        if len(nodes) % 20 == 0: print(f'{len(nodes)}/320 {name}', flush=True)
    start = time.perf_counter()
    y = run(a.package, q, observer=observe)
    elapsed = time.perf_counter() - start
    ometa = save_tensor(out, 'output', y)
    f = next(n.get('activation_frac', m['quantization']['activation_frac']) for n in graph['nodes'] if n['id'] == graph['output'])
    ometa['activation_frac'] = f
    write_json(out / 'output.json', ometa)
    display = display_rgb8(y, f)
    save_tensor(out, 'display_rgb8', display)
    Image.fromarray(display).save(out / 'integer.png'); Image.fromarray(rgb).save(out / 'input.png')
    # Official FP32 final only; avoid retaining the full float DAG at megapixel resolution.
    import torch
    from .export import load_official
    torch.set_num_threads(2)
    model = load_official(a.source)
    xf = (rgb.transpose(2, 0, 1)[None].astype(np.float32) / np.float32(255) - np.float32(.5)) / np.float32(.5)
    with torch.inference_mode(): reference = model(torch.from_numpy(xf)).numpy()
    save_tensor(out, 'fp32_output', reference)
    Image.fromarray(np.floor(np.clip(reference[0].transpose(1, 2, 0), 0, 1) * 255 + .5).astype(np.uint8)).save(out / 'fp32.png')
    diff = y.astype(np.float64) / (1 << f) - reference.astype(np.float64)
    write_json(out / 'report.json', {'shape': list(q.shape), 'elapsed_seconds_integer': elapsed, 'nodes': nodes,
              'manifest_sha256': sha256(Path(a.package) / 'manifest.json'), 'hardware_test': False,
              'raw_intermediates': 'all-node small cases use cli.py; full-size stores hashes/statistics and final raw',
              'output_vs_fp32': {'max_abs_error': float(np.abs(diff).max()), 'mean_abs_error': float(np.abs(diff).mean())}})
    print(f'complete {elapsed:.3f}s integer; mean_abs_error={np.abs(diff).mean():.8f}', flush=True)


if __name__ == '__main__': main()
