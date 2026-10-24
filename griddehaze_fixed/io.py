"""Raw tensor interchange and exact host pixel conversion (no torch dependency)."""
import hashlib
import json
from pathlib import Path
import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def input_rgb8(rgb, frac):
    """round_half_away_from_zero((2*v-255)*2**frac/255), RGB HWC -> NCHW."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Expected uint8 HWC RGB')
    if not 0 <= frac <= 14:
        raise ValueError('input frac must be 0..14')
    n = (rgb.astype(np.int64) * 2 - 255) * (1 << frac)
    q = np.sign(n) * ((np.abs(n) + 127) // 255)
    return np.ascontiguousarray(q.transpose(2, 0, 1)[None], dtype='<i2')


def display_rgb8(q, frac):
    """Clamp AFTER network; round nonnegative ties up. Returns RGB HWC."""
    a = np.clip(q.astype(np.int64), 0, 1 << frac) * 255
    a = (a + (1 << (frac - 1))) >> frac if frac else a
    return a[0].transpose(1, 2, 0).astype(np.uint8)


def save_tensor(directory, name, a):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    a = np.ascontiguousarray(a.astype(a.dtype.newbyteorder('<')))
    path = directory / (name + '.raw')
    path.write_bytes(a.tobytes())
    meta = {'file': path.name, 'shape': list(a.shape), 'dtype': a.dtype.str,
            'layout': 'NCHW' if a.ndim == 4 else 'HWC', 'bytes': path.stat().st_size,
            'sha256': sha256(path)}
    write_json(directory / (name + '.json'), meta)
    return meta


def read_tensor(meta_path):
    meta_path = Path(meta_path)
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    p = meta_path.parent / meta['file']
    if p.stat().st_size != meta['bytes'] or sha256(p) != meta['sha256']:
        raise ValueError('Tensor length/hash mismatch: ' + str(p))
    a = np.frombuffer(p.read_bytes(), dtype=meta['dtype']).reshape(meta['shape'])
    return a


def difference(expected, actual):
    if expected.shape != actual.shape or expected.dtype != actual.dtype:
        return {'exact': False, 'reason': 'shape/dtype mismatch',
                'expected_shape': list(expected.shape), 'actual_shape': list(actual.shape),
                'expected_dtype': str(expected.dtype), 'actual_dtype': str(actual.dtype)}
    d = actual.astype(np.float64) - expected.astype(np.float64)
    where = np.argwhere(d != 0)
    first = where[0].tolist() if len(where) else None
    return {'exact': not bool(len(where)), 'different_elements': len(where),
            'first_difference_nchw': first,
            'expected_at_first': expected[tuple(first)].item() if first else None,
            'actual_at_first': actual[tuple(first)].item() if first else None,
            'max_abs_error': float(np.abs(d).max()), 'mean_abs_error': float(np.abs(d).mean()),
            'mean_signed_error': float(d.mean())}
