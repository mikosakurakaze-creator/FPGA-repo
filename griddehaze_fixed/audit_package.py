"""Independent byte-level package validation without torch or the executor."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .io import sha256, write_json


def audit(package):
    root = Path(package)
    m = json.loads((root / 'manifest.json').read_text())
    b = (root / m['blob_file']).read_bytes()
    assert len(b) == m['blob_nbytes']
    assert hashlib.sha256(b).hexdigest() == m['blob_sha256']
    assert sha256(root / m['graph_file']) == m['graph_sha256']
    descriptors = m['parameters']
    names = set()
    end = 0
    for d in descriptors:
        assert d['name'] not in names
        names.add(d['name'])
        assert d['offset'] % 64 == 0 and d['offset'] >= end
        assert not any(b[end:d['offset']]), 'nonzero alignment padding'
        length = int(np.prod(d['shape'])) * np.dtype(d['dtype']).itemsize
        assert length == d['nbytes'] and d['byte_order'] == 'little'
        raw = b[d['offset']:d['offset'] + length]
        assert len(raw) == length and hashlib.sha256(raw).hexdigest() == d['sha256']
        end = d['offset'] + length
    assert end == len(b)
    graph = json.loads((root / m['graph_file']).read_text())
    known = set()
    for n in graph['nodes']:
        assert n['id'] not in known
        assert all(i in known for i in n['inputs'])
        if n.get('output_like'): assert n['output_like'] in known
        for key in ('weight', 'bias', 'coefficient'):
            if key in n: assert n[key] in names
        known.add(n['id'])
    assert graph['output'] in known
    report = {'byte_validation': True, 'tensor_count': len(descriptors), 'node_count': len(known),
              'blob_bytes': len(b), 'manifest_sha256': sha256(root / 'manifest.json'),
              'graph_sha256': m['graph_sha256'], 'blob_sha256': m['blob_sha256'],
              'max_accumulator_bound': max(d['max_accumulator_abs_bound'] for d in m['overflow_proof'])}
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('package'); p.add_argument('--report', required=True)
    a = p.parse_args()
    result = audit(a.package)
    write_json(a.report, result)
    print(json.dumps(result, indent=2))
