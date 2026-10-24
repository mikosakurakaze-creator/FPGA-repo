"""Independently verify exported integers against every official FP32 parameter.

The conversion oracle uses Python math.ldexp and scalar half-away rounding. It
does not call the exporter's quantizer or the inference engine. Run with the
pinned upstream source/checkpoint directory and one exported package directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .export import load_official
from .fetch import COMMIT, WEIGHT_SHA256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _scalar_quantization(original, fractions):
    """Deliberately independent from NumPy parameter conversion in export.py."""
    broadcast = np.broadcast_to(fractions, original.shape)

    def values():
        for source, fraction in zip(original.flat, broadcast.flat):
            scaled = math.ldexp(float(source), int(fraction))
            integer = math.floor(abs(scaled) + .5)
            integer = -integer if scaled < 0 else integer
            require(-(1 << 63) <= integer < (1 << 63), "Oracle value outside INT64")
            yield integer

    return np.fromiter(values(), dtype=np.int64, count=original.size).reshape(original.shape)


def check_export(source_dir, package_dir):
    package = Path(package_dir)
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest['format_version'] == 'griddehaze-fixed-v1', 'Unsupported manifest format')
    require(manifest['graph_file'] == 'graph.json' and manifest['blob_file'] == 'parameters.bin',
            'Unexpected package filenames')
    require(manifest['identity']['source_commit'] == COMMIT, 'Source commit mismatch')
    require(manifest['identity']['weight_sha256'] == WEIGHT_SHA256, 'Official checkpoint identity mismatch')
    graph_bytes = (package / 'graph.json').read_bytes()
    data = (package / 'parameters.bin').read_bytes()
    require(hashlib.sha256(graph_bytes).hexdigest() == manifest['graph_sha256'], 'Graph SHA256 mismatch')
    require(hashlib.sha256(data).hexdigest() == manifest['blob_sha256'], 'Blob SHA256 mismatch')
    require(len(data) == manifest['blob_nbytes'], 'Blob length mismatch')
    graph = json.loads(graph_bytes)
    parameters = {p['name']: p for p in manifest['parameters']}
    require(len(parameters) == len(manifest['parameters']), 'Duplicate tensor names')
    conv_nodes = [n for n in graph['nodes'] if n['op'] in ('conv', 'deconv')]
    require(len(conv_nodes) == 111, 'Unexpected convolution count')
    by_weight = {n['weight']: n for n in conv_nodes}
    node_fracs = {n['id']: n.get('activation_frac', manifest['quantization']['activation_frac']) for n in graph['nodes']}
    if manifest.get('scale_config_file') is not None:
        require(manifest['scale_config_file'] == 'scale_config.json', 'Unexpected calibration filename')
        scales_bytes = (package / 'scale_config.json').read_bytes()
        require(hashlib.sha256(scales_bytes).hexdigest() == manifest['scale_config_sha256']
                == manifest['identity']['scale_config_sha256'], 'Calibration configuration SHA256 mismatch')
        config = json.loads(scales_bytes)
        require(config == manifest['calibration'], 'Embedded calibration provenance mismatch')
        require(config['node_fracs'] == node_fracs, 'Calibration node fractions differ from graph')
    require(node_fracs[graph['input']] == manifest['quantization']['activation_frac'], 'Input fraction mismatch')
    require(node_fracs[graph['output']] == manifest['quantization'].get('output_frac', node_fracs[graph['output']]),
            'Output fraction mismatch')
    by_coefficient = {n['coefficient']: n for n in graph['nodes'] if n['op'] == 'mulcoef'}
    state = {k: v.detach().cpu().numpy() for k, v in load_official(source_dir).state_dict().items()}
    activation_frac = manifest['quantization']['activation_frac']
    weight_bits = manifest['quantization']['weight_bits']
    require(weight_bits in (8, 16), 'Unsupported weight bit width')
    require(manifest['quantization']['coefficient_frac'] == 14, 'Coefficient fraction mismatch')
    weight_limit = (1 << (weight_bits - 1)) - 1
    source_names = set()
    previous = 0
    scalar_count = 0
    tensor_reports = []
    for descriptor in manifest['parameters']:
        name = descriptor['name']
        offset, nbytes = descriptor['offset'], descriptor['nbytes']
        require(offset % 64 == 0 and offset >= previous, 'Tensor offset/alignment mismatch: ' + name)
        require(not any(data[previous:offset]), 'Nonzero alignment padding: ' + name)
        raw = data[offset:offset + nbytes]
        require(len(raw) == nbytes, 'Truncated raw tensor: ' + name)
        require(hashlib.sha256(raw).hexdigest() == descriptor['sha256'], 'Tensor SHA256 mismatch: ' + name)
        require(descriptor['byte_order'] == 'little', 'Unsupported byte order: ' + name)
        dtype = np.dtype(descriptor['dtype']).newbyteorder('<')
        require(dtype.kind == 'i' and dtype.itemsize in (1, 2, 8), 'Unsupported tensor type: ' + name)
        require(nbytes == math.prod(descriptor['shape']) * dtype.itemsize, 'Tensor byte count mismatch: ' + name)
        stored = np.frombuffer(raw, dtype=dtype).reshape(descriptor['shape'])
        if name == 'coefficient.full':
            original = state['coefficient']
            fractions = np.full(original.shape, 14)
            source_name = 'coefficient'
            require(descriptor['dtype'] == 'int16' and descriptor['layout'] == 'HWBC'
                    and descriptor['frac'] == 14, 'Full coefficient metadata mismatch')
        elif name.startswith('coefficient.'):
            i, j, branch = descriptor['source_index']
            node = by_coefficient[name]
            require(node['source_index'] == [i, j, branch] and node['coefficient_frac'] == 14,
                    'Coefficient graph metadata mismatch: ' + name)
            original = state['coefficient'][i, j, branch, :node['channels']]
            fractions = np.full(original.shape, 14)
            source_name = 'coefficient'
            require(descriptor['dtype'] == 'int16' and descriptor['layout'] == 'C'
                    and descriptor['frac'] == 14, 'Coefficient metadata mismatch: ' + name)
        elif name.endswith('.weight'):
            original = state[name]
            source_name = name
            node = by_weight[name]
            axis = 1 if node['op'] == 'deconv' else 0
            require(descriptor['quantization_axis'] == axis, 'Weight axis mismatch: ' + name)
            require(descriptor['layout'] == ('IOHW' if axis == 1 else 'OIHW'), 'Weight layout mismatch: ' + name)
            require(descriptor['dtype'] == ('int8' if weight_bits == 8 else 'int16'), 'Weight type mismatch: ' + name)
            require(descriptor['frac'] == node['weight_frac'], 'Weight graph fraction mismatch: ' + name)
            input_frac = node_fracs[node['inputs'][0]]
            expected_shifts = [input_frac + f - node_fracs[node['id']] for f in descriptor['frac']]
            require(node.get('requantization_shift', expected_shifts) == expected_shifts,
                    'Requantization shift mismatch: ' + name)
            fractions = np.asarray(descriptor['frac']).reshape(tuple(original.shape[d] if d == axis else 1 for d in range(4)))
            maxima = np.max(np.abs(original).astype(np.float64), axis=tuple(d for d in range(4) if d != axis))
            for maximum, fraction in zip(maxima, descriptor['frac']):
                if maximum == 0:
                    require(fraction == 0, 'Noncanonical zero-channel fraction: ' + name)
                else:
                    require(math.ldexp(float(maximum), fraction) <= weight_limit,
                            'Quantization fraction clips source weights: ' + name)
                    require(math.ldexp(float(maximum), fraction + 1) > weight_limit,
                            'Quantization fraction is not maximal: ' + name)
        else:
            require(name.endswith('.bias') and name in state, 'Unexpected tensor: ' + name)
            original = state[name]
            source_name = name
            fractions = np.asarray(descriptor['frac'])
            weight_name = name[:-4] + 'weight'
            input_frac = node_fracs[by_weight[weight_name]['inputs'][0]]
            require(descriptor['frac'] == [input_frac + f for f in parameters[weight_name]['frac']],
                    'Bias/weight scale mismatch: ' + name)
            require(descriptor['dtype'] == 'int64' and descriptor['layout'] == 'O', 'Bias metadata mismatch: ' + name)
        require(list(original.shape) == descriptor['shape'], 'Source/export shape mismatch: ' + name)
        expected = _scalar_quantization(original, fractions)
        if not np.array_equal(expected, stored):
            first = tuple(int(v) for v in np.argwhere(expected != stored)[0])
            raise ValueError(f'Integer conversion mismatch: {name} at {first}; expected={expected[first]}, stored={stored[first]}')
        source_names.add(source_name)
        errors = np.abs(np.ldexp(stored.astype(np.float64), -np.broadcast_to(fractions, stored.shape)) - original)
        tensor_reports.append(dict(name=name, shape=descriptor['shape'], dtype=descriptor['dtype'],
                                   exact_integer_conversion=True, source_parameter=source_name,
                                   max_abs_quantization_error=float(errors.max()),
                                   mean_abs_quantization_error=float(errors.mean()), sha256=descriptor['sha256']))
        scalar_count += stored.size
        previous = offset + nbytes
    require(previous == len(data), 'Unaccounted blob tail')
    require(source_names == set(state), 'Official parameters missing from export audit')
    return dict(exact=True, manifest_sha256=hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest(),
                bundle_id=manifest['identity']['bundle_id'], tensor_count=len(parameters),
                official_parameter_count=sum(v.size for v in state.values()), serialized_scalar_count=scalar_count,
                blob_bytes=len(data), all_padding_zero=True, all_official_parameters_exactly_quantized=True,
                oracle='python_math_ldexp_scalar_half_away_independent_of_export_quantizer', tensors=tensor_reports)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('package_dir', type=Path)
    parser.add_argument('--report', type=Path)
    arguments = parser.parse_args()
    try:
        report = check_export(arguments.source_dir, arguments.package_dir)
    except Exception as error:
        report = dict(exact=False, error_type=type(error).__name__, reason=str(error))
        exit_status = 1
    else:
        exit_status = 0
    if arguments.report:
        with arguments.report.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'tensors'}, sort_keys=True))
    raise SystemExit(exit_status)


if __name__ == '__main__':
    main()
