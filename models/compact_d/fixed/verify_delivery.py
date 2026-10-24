"""Audit a D package and every saved Golden/oracle tensor without modifying it.

python -m models.compact_d.fixed.verify_delivery --package PACKAGE
  --golden GOLDEN_ROOT [--oracle ORACLE_ROOT] [--report NEW_REPORT_JSON]
This checks file identities and internally consistent recorded evidence. It does
not attest that supplied files came from FPGA hardware or rerun inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .numeric import CHECKPOINT_SHA, display_rgb8, load_package

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    def reject_constant(value):
        raise ValueError('Nonfinite JSON constant: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject_constant)


def child(folder, name):
    require(isinstance(name, str) and bool(name), 'Missing evidence member name')
    path = (folder/name).resolve()
    require(path.is_relative_to(folder.resolve()) and path != folder.resolve(), 'Evidence path escapes root')
    return path


def check_hash(path, expected, nbytes=None):
    require(isinstance(expected, str) and len(expected) == 64, 'Invalid SHA-256 field')
    require(path.is_file(), 'Missing evidence file: '+str(path))
    if nbytes is not None:
        require(path.stat().st_size == nbytes, 'Wrong tensor length: '+str(path))
    actual = sha(path)
    require(actual == expected, 'Evidence SHA mismatch: '+str(path))
    return dict(file=str(path), bytes=path.stat().st_size, sha256=actual)


def checked_shape(shape, channels=None):
    require(isinstance(shape, list) and len(shape) == 4 and
            all(type(v) is int and v > 0 for v in shape) and shape[0] == 1,
            'Expected nonempty NCHW batch-one shape')
    require(shape[1] in (3, 8) and 1 <= shape[2] <= 720 and 1 <= shape[3] <= 1280,
            'Shape outside D contract')
    if channels is not None:
        require(shape[1] == channels, 'Wrong node channel count')
    return math.prod(shape)


def tensor_stats(record, value, op):
    require(record['min'] == int(value.min()) and record['max'] == int(value.max()),
            'Recorded min/max differs from saved tensor')
    for key in ('saturated_low', 'saturated_high'):
        require(type(record[key]) is int and 0 <= record[key] <= value.size,
                'Invalid saturation counter')
    require(record['saturated_low'] + record['saturated_high'] <= value.size,
            'Impossible saturation total')
    if op in ('input', 'relu'):
        require(record['saturated_low'] == record['saturated_high'] == 0,
                'Input/ReLU cannot introduce clipping')
    if op == 'relu':
        require(int(value.min()) >= 0, 'Negative value after ReLU')
    if op == 'input':
        require(int(value.min()) >= -16384 and int(value.max()) <= 16384,
                'Input outside normalized F14 range')


def channels_for(index):
    return 3 if index == 0 or index >= 18 else 8


def verify_overflow(package, graph, tensors):
    proof = read_json(package/'overflow_proof.json')
    layers = [n for n in graph if n['op'] == 'conv']
    require(len(proof['layers']) == len(layers) == 8, 'Wrong overflow proof layer count')
    maximum = 0
    for node, recorded in zip(layers, proof['layers']):
        require(recorded['node'] == node['id'] and recorded['input_abs_bound'] == 32768,
                'Wrong overflow proof identity')
        weight, bias = tensors[node['weight']], tensors[node['bias']]
        require(len(recorded['channels']) == weight.shape[0], 'Wrong proof channel count')
        bits = []
        for co, item in enumerate(recorded['channels']):
            l1 = sum(abs(int(v)) for v in weight[co].flat)
            abs_bias = abs(int(bias[co]))
            bound = 32768*l1+abs_bias
            width = bound.bit_length()+1
            require(item == dict(channel=co, sum_abs_weight=l1, abs_bias=abs_bias,
                                 absolute_bound=bound, signed_bits_sufficient=width),
                    'Overflow proof calculation mismatch')
            require(width <= 63, 'INT64 safety cannot be established')
            bits.append(width)
        require(recorded['max_signed_bits'] == max(bits), 'Layer accumulator width mismatch')
        maximum = max(maximum, max(bits))
    require(proof['max_signed_accumulator_bits'] == maximum, 'Global accumulator width mismatch')
    return maximum


def verify_golden(package_manifest, graph, folder):
    summary = read_json(folder/'summary.json')
    require(summary['format'] == 'compact-d-validation-v1' and
            summary['bundle_id'] == package_manifest['bundle_id'], 'Golden summary identity mismatch')
    reports = summary['cases']
    require(isinstance(reports, list) and len(reports) > 0, 'Empty Golden summary')
    names, files, saved_nodes, full720 = set(), [], 0, False
    saturation_total = 0
    direct_cases = 0
    for report in reports:
        name = report['case']
        require(name not in names and Path(name).name == name, 'Duplicate/unsafe Golden case name')
        names.add(name)
        case = child(folder, name)
        require(read_json(case/'report.json') == report, 'Golden case/summary report differs: '+name)
        require(report['bundle_id'] == package_manifest['bundle_id'], 'Golden case bundle differs')
        ninput = checked_shape(report['shape'], 3)
        h, w = report['shape'][-2:]
        files.append(check_hash(case/'input.i16', report['input_i16_sha256'], ninput*2))
        qinput = np.fromfile(case/'input.i16', dtype='<i2').reshape(report['shape'])
        with Image.open(case/'input.png') as image:
            require(image.mode == 'RGB' and image.size == (w, h), 'Input PNG size/mode mismatch')
            rgb = np.array(image)
        require(hashlib.sha256(rgb.tobytes()).hexdigest() == report['input_rgb_sha256'], 'Input RGB hash mismatch')
        # Independent exact rational conversion, no production input helper.
        numerator = (rgb.astype(np.int64)*2-255)*16384
        quotient, remainder = np.divmod(np.abs(numerator), 255)
        expected = (quotient+(remainder*2 >= 255))*np.where(numerator < 0, -1, 1)
        expected = expected.transpose(2, 0, 1)[None].astype('<i2')
        require(np.array_equal(qinput, expected), 'Input PNG/INT16 conversion differs')
        require(len(report['nodes']) == len(graph) == 22, 'Wrong Golden node count')
        declared_i16 = {'input.i16'}
        case_saturation = 0
        output = None
        for index, (node, record) in enumerate(zip(graph, report['nodes'])):
            require(record['index'] == index and record['id'] == node['id'] and
                    record['activation_frac'] == node['activation_frac'], 'Golden node identity/F mismatch')
            nvalues = checked_shape(record['shape'], channels_for(index))
            require(record['shape'][-2:] == [h, w] and record['bytes'] == nvalues*2 and
                    record['dtype'] == 'int16-le' and record['layout'] == 'NCHW', 'Golden node shape/layout mismatch')
            require(-32768 <= record['min'] <= record['max'] <= 32767, 'Invalid recorded INT16 range')
            for key in ('saturated_low', 'saturated_high'):
                require(type(record[key]) is int and 0 <= record[key] <= nvalues, 'Invalid recorded saturation count')
            require(record['saturated_low']+record['saturated_high'] <= nvalues, 'Impossible recorded saturation total')
            filename = f'{index:02d}_{node["id"]}.i16'
            require(record['file'] in (None, filename), 'Golden node filename mismatch')
            if report['all_intermediates_saved'] or index == 21:
                require(record['file'] == filename, 'Required Golden tensor is absent')
            if record['file'] is not None:
                declared_i16.add(filename)
                path = child(case, filename)
                files.append(check_hash(path, record['sha256'], nvalues*2))
                value = np.fromfile(path, dtype='<i2').reshape(record['shape'])
                tensor_stats(record, value, node['op'])
                if index == 0:
                    require(np.array_equal(value, qinput), 'Input node/file differs')
                if index == 21:
                    output = value
                saved_nodes += 1
            elif (case/filename).exists():
                # Optional extra dumps remain auditable rather than ignored.
                declared_i16.add(filename)
                files.append(check_hash(case/filename, record['sha256'], nvalues*2))
                tensor_stats(record, np.fromfile(case/filename, dtype='<i2'), node['op'])
                saved_nodes += 1
            case_saturation += record['saturated_low']+record['saturated_high']
            metric = record['fp32_error']
            require(all(math.isfinite(metric[k]) for k in ('mae', 'max_abs', 'mean_signed')) and
                    0 <= metric['mae'] <= metric['max_abs'], 'Invalid FP32 error metric')
            require(metric['psnr_db'] is None or math.isfinite(metric['psnr_db']), 'Invalid PSNR')
        require({p.name for p in case.glob('*.i16')} == declared_i16, 'Undeclared Golden INT16 file')
        require(report['saturation_count'] == case_saturation, 'Golden saturation sum mismatch')
        require(report['final_error'] == report['nodes'][-1]['fp32_error'], 'Final/per-node error differs')
        require(output is not None, 'Missing final Golden output')
        with Image.open(case/'int16.png') as image:
            integer_png = np.array(image)
        require(np.array_equal(integer_png, display_rgb8(output, graph[-1]['activation_frac'])),
                'INT16 display PNG differs from final tensor')
        with Image.open(case/'fp32.png') as image:
            floating_png = np.array(image)
        require(floating_png.shape == integer_png.shape == rgb.shape, 'Display image shape mismatch')
        diff = np.abs(integer_png.astype(np.int16)-floating_png.astype(np.int16))
        display = dict(mae=float(diff.mean()), max_abs=int(diff.max()),
                       different_channels=int(np.count_nonzero(diff)),
                       different_pixels=int(np.count_nonzero(np.any(diff, axis=2))))
        require(report['display_error'] == display, 'Display error statistics mismatch')
        with Image.open(case/'difference_x32.png') as image:
            require(np.array_equal(np.array(image), np.minimum(diff*32, 255).astype(np.uint8)), 'Difference PNG mismatch')
        require((case/'comparison.png').is_file(), 'Missing visual comparison sheet')
        saturation_total += case_saturation
        direct_cases += bool(report['scipy_direct_all22_exact'])
        full720 |= (h, w) == (720, 1280) and report['all_intermediates_saved']
    require({p.name for p in folder.iterdir() if p.is_dir()} == names, 'Unlisted Golden case directory')
    require(summary['all_zero_saturation'] == (saturation_total == 0), 'Summary saturation assertion mismatch')
    for key, metric in [('worst_output_mae', 'mae'), ('worst_output_max_abs', 'max_abs')]:
        require(summary[key] == max(r['final_error'][metric] for r in reports), 'Summary error maximum mismatch')
    require(summary['worst_display_max'] == max(r['display_error']['max_abs'] for r in reports), 'Summary display maximum mismatch')
    require(full720, 'Full720p all-node Golden evidence is required')
    require(direct_cases > 0, 'No independent SciPy backend evidence')
    return dict(cases=len(reports), saved_node_tensors=saved_nodes,
                file_count=len(files), verified_bytes=sum(f['bytes'] for f in files),
                zero_saturation=saturation_total == 0, full720p_all_nodes=True,
                scipy_direct_all22_cases=direct_cases,
                summary_sha256=sha(folder/'summary.json'), files=files)


def verify_oracle(manifest, graph, folder):
    report = read_json(folder/'report.json')
    require(report['status'] == 'D_CPP_ORACLE_REGRESSION_PASS' and
            report['bundle_id'] == manifest['bundle_id'] and
            report['checkpoint_sha256'] == CHECKPOINT_SHA, 'Oracle report identity mismatch')
    require(report['oracle_source_sha256'] == sha(HERE/'oracle.cpp') and
            report['harness_source_sha256'] == sha(HERE/'check_oracle.py'), 'Oracle source has changed since regression')
    executable = folder/('oracle.exe' if (folder/'oracle.exe').exists() else 'oracle')
    executable_present = executable.exists()
    if executable_present:
        check_hash(executable, report['executable_sha256'])
    require(type(report['arithmetic_cases']) is int and report['arithmetic_cases'] >= 8000, 'Insufficient arithmetic tests')
    require(len(report['rejection_tests']) >= 6 and all(t['rejected'] is True for t in report['rejection_tests']),
            'Missing input rejection evidence')
    files, names, count, full720 = [], set(), 0, False
    for record in report['cases']:
        name = record['case']
        require(name not in names and Path(name).name == name, 'Unsafe/duplicate oracle case')
        names.add(name)
        case = child(folder, name)
        require(read_json(case/'comparison.json') == record, 'Oracle case/report differs')
        require(record['exact_equal'] is True and record['compared_nodes'] == len(record['layers']) == 22,
                'Oracle exact-equality assertion missing')
        ninput = checked_shape(record['input_shape'], 3)
        h, w = record['input_shape'][-2:]
        files.append(check_hash(case/'input.i16', record['input_sha256'], ninput*2))
        require('D_CPP_ORACLE_PASS nodes=22' in record['cpp_stdout'], 'Missing successful C++ result')
        expected_names = set()
        for index, (node, layer) in enumerate(zip(graph, record['layers'])):
            require(layer['index'] == index and layer['node'] == node['id'] and layer['exact_equal'] is True,
                    'Oracle layer identity/assertion mismatch')
            nvalues = checked_shape(layer['shape'], channels_for(index))
            require(layer['shape'][-2:] == [h, w] and layer['bytes'] == nvalues*2, 'Oracle shape/length mismatch')
            filename = f'{index:02d}_{node["id"]}.i16'
            expected_names.add(filename)
            path = child(case/'cpp', filename)
            files.append(check_hash(path, layer['sha256'], nvalues*2))
            tensor_stats(layer, np.fromfile(path, dtype='<i2'), node['op'])
            if index == 0:
                require(layer['sha256'] == record['input_sha256'], 'Oracle input node differs')
            count += 1
        require({p.name for p in (case/'cpp').glob('*.i16')} == expected_names, 'Undeclared/missing oracle tensor')
        full720 |= (h, w) == (720, 1280)
    require(report['total_exact_node_comparisons'] == count and count >= 220 and full720,
            'Oracle full720p/count assertion mismatch')
    return dict(cases=len(names), exact_nodes=count, arithmetic_cases=report['arithmetic_cases'],
                rejection_tests=len(report['rejection_tests']), full720p_all_nodes=True,
                executable_present=executable_present, executable_hash_checked=executable_present,
                file_count=len(files), verified_bytes=sum(f['bytes'] for f in files),
                report_sha256=sha(folder/'report.json'), files=files)


def verify(package, golden, oracle=None):
    package, golden = Path(package).resolve(), Path(golden).resolve()
    manifest, graph, tensors = load_package(package)
    checkpoint = HERE.parent/'weights/d_best_fp32.pth'
    require(sha(checkpoint) == CHECKPOINT_SHA == manifest['checkpoint_sha256'], 'Source checkpoint SHA mismatch')
    require(sha(package/'scales.json') == sha(HERE/'scales.json'), 'Package differs from frozen scales')
    require(len(graph) == 22 and len(tensors) == 16 and manifest['parameter_count'] == 3947,
            'Wrong selected D model size')
    maximum = verify_overflow(package, graph, tensors)
    result = dict(status='D_DELIVERY_AUDIT_PASS', bundle_id=manifest['bundle_id'],
                  checkpoint_sha256=CHECKPOINT_SHA, package_manifest_sha256=sha(package/'manifest.json'),
                  producer_hashes_checked=manifest['producer_hashes'], parameter_tensors=16,
                  parameter_values=3947, semantic_nodes=22, max_certified_accumulator_bits=maximum,
                  verifier_source_sha256=sha(Path(__file__)),
                  golden=verify_golden(manifest, graph, golden),
                  oracle=verify_oracle(manifest, graph, Path(oracle).resolve()) if oracle else None,
                  scope='Read-only source/package/Golden/evidence identity and consistency audit; no inference rerun, HLS, RTL, Vivado or physical-board attestation')
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--golden', required=True)
    parser.add_argument('--oracle')
    parser.add_argument('--report')
    args = parser.parse_args()
    if args.report and Path(args.report).exists():
        raise FileExistsError('Refuse to overwrite delivery audit report')
    result = verify(args.package, args.golden, args.oracle)
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], bundle_id=result['bundle_id'],
                          golden_cases=result['golden']['cases'],
                          golden_files=result['golden']['file_count'],
                          oracle_nodes=result['oracle']['exact_nodes'] if result['oracle'] else None)))


if __name__ == '__main__':
    main()
