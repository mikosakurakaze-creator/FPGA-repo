"""Deterministic per-node INT16 binary scales from a declared calibration split."""
import argparse
import json
import math
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from .export import load_official, build_graph
from .cli import float_graph
from .io import write_json, sha256


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--source', required=True); p.add_argument('--split', required=True)
    p.add_argument('--out', required=True); p.add_argument('--headroom', type=float, default=2.0)
    a = p.parse_args()
    if Path(a.out).exists(): raise FileExistsError('Preserve prior calibration')
    if a.headroom < 1: raise ValueError('headroom must be >=1')
    import torch
    torch.set_num_threads(2)
    model = load_official(a.source)
    graph = build_graph()
    split = json.loads(Path(a.split).read_text(encoding='utf-8'))
    selected = split['calibration']
    if not selected: raise ValueError('Empty calibration split')
    peaks = {n['id']: 0.0 for n in graph['nodes']}
    samples = []
    for item in selected:
        path = item['path']
        if sha256(path) != item['sha256']: raise ValueError('Calibration input changed')
        im = np.asarray(Image.open(path).convert('RGB'))
        h, w = im.shape[:2]
        # Explicit center crop for bounded calibration cost; never called inference resizing.
        ch, cw = min(64, h), min(64, w)
        y, x = (h - ch) // 2, (w - cw) // 2
        rgb = im[y:y+ch, x:x+cw]
        xf = (rgb.transpose(2, 0, 1)[None].astype(np.float32) / np.float32(255) - np.float32(.5)) / np.float32(.5)
        values = float_graph(model, graph, xf)
        for node, value in values.items():
            peaks[node] = max(peaks[node], float(np.max(np.abs(value))))
        samples.append({'member': item['member'], 'sha256': item['sha256'], 'crop_yxhw': [y, x, ch, cw]})
        print(item['member'], flush=True)
    synthetic = []
    # These are declared calibration probes, separate from held-out real images.
    for h, w in [(33, 47), (64, 64)]:
        for pattern in ['black', 'white', 'channel', 'impulse', 'random']:
            rgb = np.zeros((h, w, 3), dtype=np.uint8)
            if pattern == 'white': rgb[:] = 255
            elif pattern == 'channel': rgb[:] = [0, 127, 255]
            elif pattern == 'impulse': rgb[0, 0] = [255, 127, 0]; rgb[-1, -1] = [0, 255, 127]
            elif pattern == 'random': rgb = np.random.default_rng(20261024).integers(0, 256, rgb.shape, dtype=np.uint8)
            xf = (rgb.transpose(2, 0, 1)[None].astype(np.float32) / np.float32(255) - np.float32(.5)) / np.float32(.5)
            for node, value in float_graph(model, graph, xf).items():
                peaks[node] = max(peaks[node], float(np.max(np.abs(value))))
            synthetic.append({'pattern': pattern, 'height': h, 'width': w, 'seed': 20261024 if pattern == 'random' else None})
    fractions = {}
    for name, peak in peaks.items():
        exponent = math.floor(math.log2(32767 / (max(peak, 1e-12) * a.headroom)))
        fractions[name] = max(0, min(14, exponent))
    fractions['input'] = 14
    membership = {key: [{'member': i['member'], 'sha256': i['sha256']} for i in split[key]]
                  for key in ('calibration', 'validation', 'independent_test')}
    split_identity = hashlib.sha256(json.dumps(membership, sort_keys=True).encode()).hexdigest()
    write_json(a.out, {'format_version': 'griddehaze-calibration-v1', 'node_fracs': fractions,
                      'observed_abs_max': peaks, 'headroom': a.headroom, 'samples': samples,
                      'synthetic_calibration_probes': synthetic,
                      'split_membership_sha256': split_identity, 'script_sha256': sha256(__file__),
                      'protocol': f'{len(selected)} calibration records ({len(set(i["sha256"] for i in selected))} unique images); one center64x64 crop each; ten synthetic probes; no validation/test images',
                      'acceptance': 'exploratory scales, no generalization or official quality threshold'})


if __name__ == '__main__': main()
