"""Explicit paired manifests, clean-source split and duplicate-image auditing."""
import hashlib
import json
import random
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset


def read_rgb(path):
    with Image.open(path) as image:
        return np.array(image.convert('RGB'), dtype=np.float32)/255.0


def tensor(image):
    return torch.from_numpy(image.transpose(2,0,1).copy())


def pixel_sha(path):
    with Image.open(path) as image:
        rgb = image.convert('RGB')
        return hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()


def read_manifest(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('task') not in ('derain','dehaze') or not manifest.get('pairs'):
        raise ValueError('Manifest requires task=derain/dehaze and nonempty pairs')
    rows = []
    for row in manifest['pairs']:
        if row.get('split') not in ('train','val','test') or not row.get('clean_id') or not row.get('id'):
            raise ValueError('Each pair needs id, clean_id, split=train/val/test')
        item = dict(row)
        for key in ('input','target'):
            item[key] = (path.parent / row[key]).resolve()
            if not item[key].is_file():
                raise FileNotFoundError(item[key])
        rows.append(item)
    return manifest, rows


def audit_manifest(path):
    manifest, rows = read_manifest(path)
    identities, clean_images, degraded_images, ids = {}, {}, {}, set()
    counts = {key:0 for key in ('train','val','test')}
    for row in rows:
        if row['id'] in ids:
            raise ValueError('Duplicate pair ID: '+row['id'])
        ids.add(row['id'])
        split = row['split']
        counts[split] += 1
        for seen,key in ((identities,row['clean_id']), (clean_images,pixel_sha(row['target'])),
                         (degraded_images,pixel_sha(row['input']))):
            if key in seen and seen[key] != split:
                raise ValueError('Cross-split source/pixel leakage: '+row['id'])
            seen[key] = split
        with Image.open(row['input']) as a, Image.open(row['target']) as b:
            if a.size != b.size:
                raise ValueError('Pair dimensions differ: '+row['id'])
    if not all(counts.values()):
        raise ValueError('All three nonempty splits required')
    return {'task':manifest['task'], 'kind':manifest.get('kind','unspecified'),
            'split_counts':counts, 'unique_clean_sources':len(clean_images),
            'split_audit':'PASS', 'manifest_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


class PairedImages(Dataset):
    def __init__(self, manifest, split, crop=0, cache=False):
        _, rows = read_manifest(manifest)
        self.rows = [row for row in rows if row['split'] == split]
        self.crop = crop
        self.cache = {} if cache else None
        if not self.rows:
            raise ValueError('Empty split: '+split)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        if self.cache is None:
            a,b = read_rgb(row['input']),read_rgb(row['target'])
        else:
            if index not in self.cache:
                self.cache[index]=(read_rgb(row['input']),read_rgb(row['target']))
            a,b=self.cache[index]
        if self.crop:
            h,w = a.shape[:2]
            if min(h,w) < self.crop:
                pads=((0,max(0,self.crop-h)),(0,max(0,self.crop-w)),(0,0))
                a,b = np.pad(a,pads,mode='edge'), np.pad(b,pads,mode='edge')
            y = random.randrange(a.shape[0]-self.crop+1)
            x = random.randrange(a.shape[1]-self.crop+1)
            a,b = a[y:y+self.crop,x:x+self.crop], b[y:y+self.crop,x:x+self.crop]
            if random.random() < .5:
                a,b = a[:,::-1], b[:,::-1]
        return tensor(a),tensor(b),row['id']
