"""Verify every local handoff file against its delivery SHA-256 inventory."""
import argparse
import json
from pathlib import Path
from .io import sha256


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'DELIVERY.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Missing or invalid path: ' + entry['path'])
        if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
            raise ValueError('Delivery checksum mismatch: ' + entry['path'])
    print(f'PASS: {len(manifest["files"])} files, bundle={manifest["bundle_id"]}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('root')
    verify(p.parse_args().root)
