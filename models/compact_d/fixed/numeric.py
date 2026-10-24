"""Torch-free D integer graph. Reuses previously tested arithmetic primitives only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from griddehaze_fixed.integer import round_shift, conv2d_accumulate, requantize
from griddehaze_fixed.io import input_rgb8, sha256, write_json

VERSION = 'compact-d-int16-v1'
CHECKPOINT_SHA = '0d2678ba533a83c797d5b7a2a922461440fa47f93043525a9165f0a1f9fc28fc'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCERS = ['models/compact_d/fixed/numeric.py','models/compact_d/fixed/export.py',
             'griddehaze_fixed/integer.py','griddehaze_fixed/io.py','models/compact_d/model.py',
             'models/compact_d/reference_fp32/manifest.json']

def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()

def display_rgb8(q, frac=14):
    """Exact np.rint-style ties-to-even on the rational q*255/2**F."""
    value = np.clip(q.astype(np.int64), 0, 1 << frac)*255
    whole = value >> frac
    remainder = value & ((1 << frac)-1)
    half = 1 << (frac-1)
    result = whole + ((remainder > half) | ((remainder == half) & ((whole & 1) != 0)))
    return result[0].transpose(1, 2, 0).astype(np.uint8)

def load_package(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    if manifest.get('format') != VERSION or manifest.get('checkpoint_sha256') != CHECKPOINT_SHA:
        raise ValueError('Wrong D model/version identity')
    identity = {k:v for k,v in manifest.items() if k != 'bundle_id'}
    if hashlib.sha256(canonical(identity)).hexdigest() != manifest.get('bundle_id'):
        raise ValueError('Manifest identity mismatch')
    if set(manifest.get('producer_hashes',{})) != set(PRODUCERS):
        raise ValueError('Incomplete producer identities')
    for name,digest in manifest['producer_hashes'].items():
        if sha256(ROOT/name) != digest: raise ValueError('Producer code identity mismatch: '+name)
    for name, digest in manifest['files'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path) != digest:
            raise ValueError('Package file hash mismatch: '+name)
    graph = json.loads((folder/'graph.json').read_text())
    blob = (folder/'parameters.bin').read_bytes()
    tensors = {}
    spans = []
    for item in manifest['parameters']:
        offset, nbytes = item['offset'], item['bytes']
        dtype = np.dtype(item['dtype'])
        shape = item['shape']
        if dtype.str not in ('<i2', '<i8') or offset < 0 or offset % 64 or nbytes != int(np.prod(shape))*dtype.itemsize or offset+nbytes > len(blob):
            raise ValueError('Invalid parameter bounds/dtype')
        payload = blob[offset:offset+nbytes]
        if hashlib.sha256(payload).hexdigest() != item['sha256'] or item['name'] in tensors:
            raise ValueError('Invalid parameter identity')
        tensors[item['name']] = np.frombuffer(payload, dtype=dtype).reshape(shape)
        spans.append((offset, offset+nbytes))
    if any(a[1] > b[0] for a,b in zip(sorted(spans),sorted(spans)[1:])):
        raise ValueError('Overlapping parameter spans')
    official = json.loads((HERE.parent/'reference_fp32/manifest.json').read_text())
    numeric_keys = {'activation_frac','weight_frac','requantization_shift'}
    semantic_graph = [{k:v for k,v in n.items() if k not in numeric_keys} for n in graph]
    expected_graph = []
    for original in official['graph']:
        expected = dict(original,dtype='int16-le',layout='NCHW')
        if original['op']=='input':expected.update(range=[-16384,16384],real_range=[-1,1])
        expected_graph.append(expected)
    if semantic_graph != expected_graph or [n['id'] for n in graph] != manifest['node_order']:
        raise ValueError('Wrong D graph')
    config = json.loads((folder/'scales.json').read_text())['node_fracs']
    if config != {n['id']:n['activation_frac'] for n in graph}: raise ValueError('Graph/scales mismatch')
    descriptors = {p['name']:p for p in manifest['parameters']}
    if set(tensors) != set(official['parameters']):raise ValueError('Wrong D parameters')
    for name,parameter in descriptors.items():
        expected = official['parameters'][name]
        if parameter['shape'] != expected['shape'] or parameter['layout'] != expected['layout']:
            raise ValueError('Wrong D parameter shape/layout')
    for n in graph:
        if type(n['activation_frac']) is not int or not 0 <= n['activation_frac'] <= 14:raise ValueError('Invalid node F')
        if n['op']=='conv':
            weight,bias = descriptors[n['weight']],descriptors[n['bias']]
            fin=config[n['inputs'][0]]
            if weight['dtype'] != '<i2' or bias['dtype'] != '<i8' or weight['frac'] != n['weight_frac'] or bias['frac'] != [fin+f for f in n['weight_frac']]:
                raise ValueError('Wrong D parameter dtype/scale')
            if n['requantization_shift'] != [fin+f-n['activation_frac'] for f in n['weight_frac']]:raise ValueError('Wrong requantization shift')
        elif n['op']=='relu' and config[n['inputs'][0]] != n['activation_frac']:raise ValueError('ReLU changes F')
    if config['input'] != 14:raise ValueError('Wrong input F')
    return manifest, graph, tensors

def run(package, qinput, backend='numpy', observer=None):
    manifest, graph, tensors = load_package(package)
    qinput = np.asarray(qinput)
    if qinput.dtype != np.int16 or qinput.ndim != 4 or qinput.shape[:2] != (1,3) or not qinput.flags.c_contiguous:
        raise ValueError('Expected contiguous NCHW int16, N=1 C=3')
    h,w = qinput.shape[-2:]
    if not 1 <= h <= 720 or not 1 <= w <= 1280:
        raise ValueError('D numerical contract supports 1<=H<=720, 1<=W<=1280')
    if np.any(qinput < -16384) or np.any(qinput > 16384):
        raise ValueError('Input must represent normalized RGB in [-1,1], F14')
    values, fracs = {}, {n['id']:n['activation_frac'] for n in graph}
    uses = {n['id']:0 for n in graph}
    for n in graph:
        for src in n.get('inputs',[]): uses[src] += 1
    uses['output.relu'] += 1
    for index,node in enumerate(graph):
        ident, op, frac = node['id'], node['op'], node['activation_frac']
        sources = node.get('inputs',[])
        lo = hi = 0
        if op == 'input':
            value = qinput[0].copy()
        elif op == 'conv':
            accumulator = conv2d_accumulate(values[sources[0]], tensors[node['weight']], tensors[node['bias']], padding=1, backend=backend)
            value, stats = requantize(accumulator, node['requantization_shift'])
            lo,hi = stats['saturated_low'],stats['saturated_high']
        elif op == 'relu':
            if fracs[sources[0]] != frac: raise ValueError('D ReLU must preserve scale')
            value = np.maximum(values[sources[0]],0).astype(np.int16)
        elif op == 'add':
            wide = sum(round_shift(values[src],fracs[src]-frac) for src in sources)
            lo,hi = int(np.count_nonzero(wide < -32768)),int(np.count_nonzero(wide > 32767))
            value = np.clip(wide,-32768,32767).astype(np.int16)
        elif op == 'affine':
            src = sources[0]
            wide = round_shift(values[src].astype(np.int64)+(1 << fracs[src]),fracs[src]+1-frac)
            lo,hi = int(np.count_nonzero(wide < -32768)),int(np.count_nonzero(wide > 32767))
            value = np.clip(wide,-32768,32767).astype(np.int16)
        else: raise ValueError('Unsupported D op '+op)
        values[ident] = value
        if observer:
            observer(index, node, value[None], {'min':int(value.min()),'max':int(value.max()),'saturated_low':lo,'saturated_high':hi})
        for src in sources:
            uses[src] -= 1
            if uses[src] == 0: del values[src]
    return np.ascontiguousarray(values['output.relu'][None])
