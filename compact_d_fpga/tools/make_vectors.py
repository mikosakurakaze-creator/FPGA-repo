"""Generate D integration vectors using A's unchanged integer reference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--a-root', type=Path, default=Path('C:/Users/wzh16/Desktop/github clone/feat-software'))
    p.add_argument('--package', type=Path, default=Path('D:/weather_builds/compact_d_numeric01/package'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cases', nargs='+', default=['random_17x1280', 'random_720x1', 'pattern_720p'])
    a = p.parse_args()
    sys.path.insert(0, str(a.a_root))
    import numpy as np
    from models.compact_d.fixed.numeric import run, input_rgb8, load_package
    manifest, _, _ = load_package(a.package)
    a.out.mkdir(parents=True, exist_ok=False)
    for name in a.cases:
        if name == 'pattern_720p':
            y, x = np.indices((720, 1280))
            rgb = np.stack((x % 256, y % 256, (x+y) % 256), axis=2).astype(np.uint8)
        else:
            h, w = map(int, name.removeprefix('random_').split('x'))
            rgb = np.random.default_rng(20261025+h+w).integers(0, 256, (h, w, 3), dtype=np.uint8)
        folder = a.out/name
        folder.mkdir()
        qinput = input_rgb8(rgb, 14)
        (folder/'input.i16').write_bytes(qinput.astype('<i2').tobytes())
        nodes = []
        def observe(index, node, value, stats):
            raw = value.astype('<i2').tobytes()
            filename = f'{index:02d}_{node["id"]}.i16'
            (folder/filename).write_bytes(raw)
            nodes.append(dict(index=index, id=node['id'], file=filename, shape=list(value.shape),
                              bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), **stats))
        start = time.perf_counter()
        run(a.package, qinput, observer=observe)
        report = dict(bundle_id=manifest['bundle_id'], shape=list(qinput.shape), nodes=nodes,
                      input_i16_sha256=hashlib.sha256((folder/'input.i16').read_bytes()).hexdigest(),
                      scope='A integer reference; generated integration vector, not FPGA result', seconds=time.perf_counter()-start)
        (folder/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
        print('D_VECTOR_READY '+name+' seconds='+str(round(report['seconds'], 3)), flush=True)


if __name__ == '__main__':
    main()
