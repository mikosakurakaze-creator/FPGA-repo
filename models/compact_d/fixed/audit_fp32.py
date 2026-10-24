"""Reproduce frozen FP32 evidence independently of fixed-point implementation.

Run from any working directory. Real images are optional and remain local.
This verifies identity, all original FP32 fixtures, and public preprocessing.
It never treats historical GridDehazeNet results as D verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, __version__ as pillow_version
import torch
import torch.nn.functional as F

MODEL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODEL_DIR))
from model import CHECKPOINT_SHA256, load_model, trace  # noqa: E402
from predict import preprocess  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def independent_forward(state, x):
    """Functional graph driven directly by frozen tensors, no model.forward/trace."""
    result = {'input': x}

    def conv(name, parameter, value):
        result[name] = F.conv2d(value, state[parameter + '.weight'],
                                state[parameter + '.bias'], stride=1, padding=1)
        return result[name]

    def relu(name, value):
        result[name] = torch.maximum(value, torch.zeros((), dtype=value.dtype))
        return result[name]

    y = relu('stem.relu', conv('stem.conv', 'stem', x))
    for index in range(3):
        residual = y
        y = conv(f'block{index}.conv0', f'blocks.{index}.0', y)
        y = relu(f'block{index}.relu0', y)
        y = conv(f'block{index}.conv1', f'blocks.{index}.2', y)
        y = residual + y
        result[f'block{index}.add'] = y
        y = relu(f'block{index}.relu1', y)
    correction = conv('head.conv', 'head', y)
    result['input.affine'] = (x + 1) / 2
    result['output.add'] = result['input.affine'] + correction
    relu('output.relu', result['output.add'])
    assert len(result) == 22
    return result


def independent_preprocess(path):
    with Image.open(path) as image:
        oriented = ImageOps.exif_transpose(image)
        rgb = oriented.convert('RGB')
    original_size = rgb.size
    rgb.thumbnail((1280, 720), Image.Resampling.LANCZOS)
    pixels = np.array(rgb, dtype=np.uint8)
    normalized = (pixels.astype(np.float32) / np.float32(255)) * np.float32(2) - np.float32(1)
    x = torch.from_numpy(np.ascontiguousarray(normalized.transpose(2, 0, 1)))[None]
    return x, pixels, original_size


def preprocessing_tests(out):
    folder = out / 'preprocessing'
    folder.mkdir(parents=True, exist_ok=True)
    checks = []
    specs = [('small', (19, 11), 'RGB', None, (19, 11)),
             ('wide', (2560, 1440), 'RGB', None, (1280, 720)),
             ('tall', (1000, 2000), 'RGB', None, (360, 720)),
             ('gray', (31, 17), 'L', None, (31, 17)),
             ('rgba', (23, 29), 'RGBA', None, (23, 29)),
             ('exif6', (41, 19), 'RGB', 6, (19, 41))]
    for name, size, mode, orientation, expected in specs:
        h, w = size[1], size[0]
        channels = {'RGB': 3, 'L': 1, 'RGBA': 4}[mode]
        array = (np.arange(h * w * channels, dtype=np.uint32) % 256).astype(np.uint8)
        array = array.reshape((h, w) if mode == 'L' else (h, w, channels))
        image = Image.fromarray(array)
        path = folder / (name + ('.jpg' if orientation else '.png'))
        if orientation:
            exif = Image.Exif()
            exif[274] = orientation
            image.save(path, exif=exif)
        else:
            image.save(path)
        actual = preprocess(path)
        expected_x, _, oriented_size = independent_preprocess(path)
        assert torch.equal(actual, expected_x), name
        assert tuple(actual.shape[-2:][::-1]) == expected, name
        if orientation == 6:
            # Independent pixel-space expectation: EXIF 6 rotates raw decoded
            # pixels 90 degrees clockwise, not merely an exchange of H and W.
            with Image.open(path) as saved:
                manual_rgb = np.rot90(np.array(saved.convert('RGB')), -1)
            manual_x = torch.from_numpy(np.ascontiguousarray(manual_rgb.transpose(2, 0, 1))).float()[None] / 255 * 2 - 1
            assert torch.equal(actual, manual_x), 'EXIF 6 pixel direction'
        checks.append(dict(name=name, source_size=list(size), oriented_size=list(oriented_size),
                           processed_size=list(expected), mode=mode, exact_equal=True,
                           input_sha256=sha(path.read_bytes())))
    return checks


def real_image_checks(model, state, roots, out):
    split = read_json(MODEL_DIR / 'split_manifest.json')
    train = {entry['sha256'] for entry in split['sets']['train']}
    validation = {entry['sha256'] for entry in split['sets']['validation']}
    entries = split['sets']['holdout']
    records = []
    image_out = out / 'holdout'
    image_out.mkdir(parents=True, exist_ok=True)
    for index, entry in enumerate(entries):
        candidates = [root / entry['filename'] for root in roots]
        path = next((p for p in candidates if p.is_file() and sha(p.read_bytes()) == entry['sha256']), None)
        if path is None:
            raise FileNotFoundError(f"Holdout SHA not located: {entry['filename']}")
        assert entry['sha256'] not in train | validation
        x, pixels, oriented_size = independent_preprocess(path)
        assert torch.equal(preprocess(path), x)
        start = time.perf_counter()
        with torch.inference_mode():
            nodes = independent_forward(state, x)
            y = model(x)
        elapsed = time.perf_counter() - start
        assert torch.equal(y, nodes['output.relu'])
        array = y.cpu().numpy().astype('<f4')
        rgb = np.rint(np.clip(array[0].transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
        stem = f"{index:02d}_{path.stem}"
        array_path = image_out / (stem + '_fp32.npy')
        np.save(array_path, array, allow_pickle=False)
        Image.fromarray(pixels).save(image_out / (stem + '_input.png'))
        rgb_path = image_out / (stem + '_fp32.png')
        Image.fromarray(rgb).save(rgb_path)
        records.append(dict(index=index, label=entry['label'], filename=entry['filename'],
                            path=str(path.resolve()), sha256=entry['sha256'], split='holdout',
                            exact_sha_disjoint_train_validation=True,
                            original_oriented_size=list(oriented_size), processed_shape=list(x.shape),
                            input_rgb_sha256=sha(pixels.tobytes()),
                            fp32_min=float(array.min()), fp32_max=float(array.max()),
                            over_one_count=int((array > 1).sum()),
                            current_independent_vs_forward_exact=True,
                            host_seconds_two_graph_executions=elapsed,
                            fp32_npy=str(array_path.resolve()),
                            fp32_npy_sha256=sha(array_path.read_bytes()),
                            display_png=str(rgb_path.resolve()), display_png_sha256=sha(rgb_path.read_bytes())))
    return records


def independent_integer_audit(package, state, out):
    """Exact Fraction parameter export + scalar Python-int graph, independent MACs.

    Uses production run only as the value being tested. The oracle neither calls
    production rounding, convolution, input conversion nor requantization.
    """
    sys.path.insert(0, str(MODEL_DIR.parents[1]))
    from models.compact_d.fixed.numeric import run, load_package
    package = Path(package).resolve()
    manifest = read_json(package / 'manifest.json')
    graph = read_json(package / 'graph.json')
    blob = (package / 'parameters.bin').read_bytes()
    parameters = {}
    descriptors = {item['name']: item for item in manifest['parameters']}

    def rounded_ratio(numerator, denominator):
        quotient, remainder = divmod(abs(numerator), denominator)
        return (quotient + int(2 * remainder >= denominator)) * (-1 if numerator < 0 else 1)

    def rshift(value, shift):
        return rounded_ratio(value, 1 << shift) if shift >= 0 else value * (1 << -shift)

    def saturate(value):
        return min(32767, max(-32768, value))

    parameter_checks = []
    for name, tensor in state.items():
        item = descriptors[name]
        raw = blob[item['offset']:item['offset'] + item['bytes']]
        actual = np.frombuffer(raw, dtype=item['dtype']).reshape(item['shape'])
        expected = np.empty(actual.shape, dtype=actual.dtype)
        for index in np.ndindex(actual.shape):
            frac = item['frac'][index[0]]
            # Every checkpoint FP32 value is exactly representable by Python's
            # binary64 float; Fraction then recovers its exact rational value.
            value = Fraction(float(tensor[index])) * (1 << frac)
            expected[index] = rounded_ratio(value.numerator, value.denominator)
        assert np.array_equal(expected, actual), name
        assert sha(expected.tobytes()) == item['sha256']
        parameters[name] = expected
        parameter_checks.append(dict(name=name, exact_fraction_quantization=True,
                                     sha256=sha(expected.tobytes())))
    proof = read_json(package / 'overflow_proof.json')
    certified = {layer['node']: layer for layer in proof['layers']}
    proof_checks = []
    for node in graph:
        if node['op'] != 'conv':
            continue
        weight, bias = parameters[node['weight']], parameters[node['bias']]
        layer = certified[node['id']]
        assert layer['input_abs_bound'] == 32768
        for co, channel in enumerate(layer['channels']):
            l1 = sum(abs(int(value)) for value in weight[co].flat)
            bound = 32768 * l1 + abs(int(bias[co]))
            assert channel['channel'] == co
            assert channel['sum_abs_weight'] == l1 and channel['abs_bias'] == abs(int(bias[co]))
            assert channel['absolute_bound'] == bound
            assert channel['signed_bits_sufficient'] == bound.bit_length() + 1
        assert len(layer['channels']) == weight.shape[0]
        assert layer['max_signed_bits'] == max(c['signed_bits_sufficient'] for c in layer['channels'])
        proof_checks.append(dict(node=node['id'], max_signed_bits=layer['max_signed_bits'],
                                 max_absolute_bound=max(c['absolute_bound'] for c in layer['channels']),
                                 all_channel_proofs_exact=True))
    assert len(proof_checks) == len(certified) == 8
    assert proof['max_signed_accumulator_bits'] == max(p['max_signed_bits'] for p in proof_checks)

    def scalar_graph(qinput):
        values = {}
        fracs = {node['id']: node['activation_frac'] for node in graph}
        height, width = qinput.shape[-2:]
        for node in graph:
            node_id, op, frac = node['id'], node['op'], node['activation_frac']
            sources = node.get('inputs', [])
            if op == 'input':
                value = qinput[0].copy()
            elif op == 'conv':
                weight, bias = parameters[node['weight']], parameters[node['bias']]
                value = np.empty((weight.shape[0], height, width), dtype=np.int16)
                source = values[sources[0]]
                for co in range(weight.shape[0]):
                    for y in range(height):
                        for x in range(width):
                            accumulator = int(bias[co])
                            for ci in range(weight.shape[1]):
                                for ky in range(3):
                                    iy = y + ky - 1
                                    for kx in range(3):
                                        ix = x + kx - 1
                                        if 0 <= iy < height and 0 <= ix < width:
                                            accumulator += int(source[ci, iy, ix]) * int(weight[co, ci, ky, kx])
                            value[co, y, x] = saturate(rshift(accumulator, node['requantization_shift'][co]))
            else:
                value = np.empty(values[sources[0]].shape, dtype=np.int16)
                for index in np.ndindex(value.shape):
                    if op == 'relu':
                        scalar = max(0, int(values[sources[0]][index]))
                    elif op == 'add':
                        scalar = sum(rshift(int(values[source][index]), fracs[source] - frac) for source in sources)
                    elif op == 'affine':
                        source = sources[0]
                        scalar = rshift(int(values[source][index]) + (1 << fracs[source]), fracs[source] + 1 - frac)
                    else:
                        raise AssertionError(op)
                    value[index] = saturate(scalar)
            values[node_id] = value
        return values

    cases = []
    generator = np.random.default_rng(20261025)
    for height, width in [(1, 1), (1, 7), (7, 1), (3, 5), (8, 8)]:
        qinput = generator.integers(-16384, 16385, size=(1, 3, height, width), dtype=np.int16)
        expected = scalar_graph(qinput)
        checked = []

        def compare(index, node, value, statistics):
            assert np.array_equal(expected[node['id']], value[0]), (height, width, node['id'])
            checked.append(node['id'])

        result = run(package, qinput, observer=compare)
        assert np.array_equal(result[0], expected['output.relu'])
        assert len(checked) == 22
        cases.append(dict(shape=list(qinput.shape), all_22_nodes_exact=True,
                          input_sha256=sha(qinput.astype('<i2').tobytes()),
                          output_sha256=sha(result.astype('<i2').tobytes())))
    negative = []

    def rewrite_manifest(folder, value):
        identity = {k: v for k, v in value.items() if k != 'bundle_id'}
        canonical = (json.dumps(identity, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
        value['bundle_id'] = sha(canonical)
        (folder / 'manifest.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

    # Temporary copies are created beneath the resolved audit output, and only
    # these generated paths are removed when their scoped context exits.
    with tempfile.TemporaryDirectory(prefix='negative_', dir=out) as temporary:
        temporary = Path(temporary).resolve()
        assert temporary.is_relative_to(out.resolve())
        for kind, expected_error in [('conv_stride', 'Wrong D graph'),
                                     ('affine_scale', 'Wrong D graph'),
                                     ('stale_producer', 'Producer code identity mismatch'),
                                     ('parameter_layout', 'Wrong D parameter shape/layout'),
                                     ('corrupt_blob', 'Package file hash mismatch')]:
            folder = temporary / kind
            shutil.copytree(package, folder)
            copied = read_json(folder / 'manifest.json')
            if kind in ('conv_stride', 'affine_scale'):
                copied_graph = read_json(folder / 'graph.json')
                if kind == 'conv_stride':
                    copied_graph[1]['stride'] = [2, 2]
                else:
                    next(n for n in copied_graph if n['id'] == 'input.affine')['scale'] = 1.0
                (folder / 'graph.json').write_text(json.dumps(copied_graph), encoding='utf-8')
                copied['files']['graph.json'] = sha((folder / 'graph.json').read_bytes())
            elif kind == 'stale_producer':
                first = sorted(copied['producer_hashes'])[0]
                copied['producer_hashes'][first] = '0' * 64
            elif kind == 'parameter_layout':
                copied['parameters'][0]['layout'] = 'IOHW'
            elif kind == 'corrupt_blob':
                changed = bytearray((folder / 'parameters.bin').read_bytes())
                changed[0] ^= 1
                (folder / 'parameters.bin').write_bytes(changed)
            rewrite_manifest(folder, copied)
            try:
                load_package(folder)
            except ValueError as error:
                assert expected_error in str(error), (kind, str(error))
                negative.append(dict(case=kind, rejected=True, reason=str(error),
                                     manifest_identity_recomputed=True))
            else:
                raise AssertionError('Accepted malformed package: ' + kind)
    report = dict(status='PASS', bundle_id=manifest['bundle_id'],
                  oracle='Python arbitrary-precision integers, scalar convolution; Fraction exact parameter rounding',
                  source_checkpoint_sha256=CHECKPOINT_SHA256,
                  parameters=parameter_checks, cases=cases,
                  overflow_proof=proof_checks,
                  negative_package_tests=negative,
                  tested_code_sha256=sha((MODEL_DIR / 'fixed/numeric.py').read_bytes()),
                  limits='Small-shape independent audit; full-size regression and C++/HLS validation are separate evidence.')
    (out / 'audit_fp32_integer.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return dict(bundle_id=manifest['bundle_id'], cases=len(cases), nodes_checked=len(cases) * 22)


def audit_golden_files(golden, package, out):
    """Cross-check saved evidence; this is not another full-size inference run."""
    golden = Path(golden).resolve()
    summary = read_json(golden / 'summary.json')
    manifest = read_json(Path(package) / 'manifest.json')
    graph = read_json(Path(package) / 'graph.json')
    assert summary['bundle_id'] == manifest['bundle_id']
    saved_nodes, inputs = 0, 0
    holdout = {e['sha256'] for e in read_json(MODEL_DIR / 'split_manifest.json')['sets']['holdout']}
    actual_holdout = set()
    for case in summary['cases']:
        folder = (golden / case['case']).resolve()
        assert folder.is_relative_to(golden)
        assert case['bundle_id'] == manifest['bundle_id']
        shape = case['shape']
        raw = (folder / 'input.i16').read_bytes()
        assert len(raw) == int(np.prod(shape)) * 2
        assert sha(raw) == case['input_i16_sha256']
        inputs += 1
        assert [n['id'] for n in case['nodes']] == manifest['node_order']
        for descriptor, node in zip(case['nodes'], graph):
            assert descriptor['activation_frac'] == node['activation_frac']
            if descriptor['file'] is None:
                continue
            path = (folder / descriptor['file']).resolve()
            assert path.is_relative_to(folder)
            payload = path.read_bytes()
            assert len(payload) == descriptor['bytes'] == int(np.prod(descriptor['shape'])) * 2
            assert sha(payload) == descriptor['sha256']
            tensor = np.frombuffer(payload, dtype='<i2').reshape(descriptor['shape'])
            assert int(tensor.min()) == descriptor['min'] and int(tensor.max()) == descriptor['max']
            saved_nodes += 1
        final = case['nodes'][-1]
        tensor = np.frombuffer((folder / final['file']).read_bytes(), dtype='<i2').reshape(final['shape'])
        # Values times 255 / a power of two are exactly representable in binary64.
        pixels = np.rint(np.clip(tensor.astype(np.float64) / (1 << final['activation_frac']), 0, 1) * 255)
        pixels = pixels[0].transpose(1, 2, 0).astype(np.uint8)
        with Image.open(folder / 'int16.png') as image:
            assert np.array_equal(pixels, np.array(image))
        if case['input_source_sha256']:
            assert case['input_source_sha256'] in holdout
            actual_holdout.add(case['input_source_sha256'])
    report = dict(status='PASS', bundle_id=manifest['bundle_id'], input_files_verified=inputs,
                  saved_node_files_verified=saved_nodes, display_files_verified=len(summary['cases']),
                  holdout_sha_entries_verified=len(actual_holdout), all_published_holdout_present=actual_holdout == holdout,
                  scope='Recorded file SHA/size/range/scale and integer display identity; no additional full-size inference',
                  summary_sha256=sha((golden / 'summary.json').read_bytes()))
    (out / 'audit_golden_files.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, action='append', default=[])
    parser.add_argument('--package', type=Path, help='Optional independent exact integer audit of exported package')
    parser.add_argument('--golden', type=Path, help='Optional saved Golden SHA/metadata/display audit; requires --package')
    args = parser.parse_args()
    if args.golden and not args.package:
        parser.error('--golden requires --package')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.manual_seed(20261025)
    reference = MODEL_DIR / 'reference_fp32'
    manifest = read_json(reference / 'manifest.json')
    checkpoint_path = MODEL_DIR / 'weights/d_best_fp32.pth'
    checkpoint_bytes = checkpoint_path.read_bytes()
    assert sha(checkpoint_bytes) == CHECKPOINT_SHA256 == manifest['checkpoint_sha256']
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    state = checkpoint['state_dict']
    model = load_model(device='cpu')
    assert len(state) == len(manifest['parameters']) == 16
    assert sum(p.numel() for p in model.parameters()) == manifest['parameter_count'] == 3947
    blob = (reference / 'weights_fp32.bin').read_bytes()
    assert len(blob) == manifest['weights_bytes'] == 15788
    assert sha(blob) == manifest['weights_sha256']
    parameter_checks = []
    reconstructed = bytearray()
    for name, tensor in state.items():
        metadata = manifest['parameters'][name]
        raw = tensor.numpy().astype('<f4').tobytes()
        assert list(tensor.shape) == metadata['shape']
        assert metadata['dtype'] == 'float32-le'
        assert metadata['layout'] == ('OIHW' if tensor.ndim == 4 else 'O')
        assert len(reconstructed) == metadata['offset']
        assert len(raw) == metadata['bytes'] and sha(raw) == metadata['sha256']
        assert raw == blob[metadata['offset']:metadata['offset'] + metadata['bytes']]
        reconstructed.extend(raw)
        parameter_checks.append(dict(name=name, shape=list(tensor.shape), sha256=sha(raw), exact_equal=True))
    assert bytes(reconstructed) == blob
    fixture_checks = []
    for case in manifest['cases']:
        folder = reference / case['case']
        metas = case['nodes']
        rgb = np.frombuffer((folder / 'input_rgb_nchw_u8.bin').read_bytes(), dtype=np.uint8).reshape(metas[0]['shape'])
        x = torch.from_numpy(rgb.astype(np.float32) / 255) * 2 - 1
        with torch.inference_mode():
            independent = independent_forward(state, x)
            actual = trace(model, x)
            assert torch.equal(model(x), independent['output.relu'])
        assert list(independent) == list(actual) == [m['id'] for m in metas] == [g['id'] for g in manifest['graph']]
        for metadata in metas:
            node = metadata['id']
            raw = (folder / metadata['file']).read_bytes()
            assert len(raw) == metadata['bytes'] and sha(raw) == metadata['sha256']
            expected = np.frombuffer(raw, dtype='<f4').reshape(metadata['shape'])
            current = independent[node].numpy()
            assert torch.equal(independent[node], actual[node])
            difference = np.abs(expected.astype(np.float64) - current.astype(np.float64))
            # Published fixtures were produced with PyTorch 2.7.1 CPU. Preserve
            # their identity while allowing FP32 kernel drift in a newer runtime.
            assert np.allclose(current, expected, rtol=2e-5, atol=3e-6), (case['case'], node, difference.max())
            fixture_checks.append(dict(case=case['case'], node=node, source_sha256=metadata['sha256'],
                                       source_exact_equal=bool(np.array_equal(current, expected)),
                                       source_max_abs=float(difference.max()),
                                       current_independent_vs_trace_exact=True))
    report = dict(status='PASS', scope='D FP32 identity/reference/preprocessing; no fixed-point, HLS or board claim',
                  environment=dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
                                   torch=str(torch.__version__), numpy=np.__version__, pillow=pillow_version,
                                   device='cpu', torch_threads=torch.get_num_threads()),
                  source_checkpoint_sha256=CHECKPOINT_SHA256, selected_step=checkpoint['step'],
                  source_teacher_sha256=checkpoint['teacher_sha256'],
                  parameter_count=3947, parameter_tensors=16, conv_layers=8, semantic_nodes=22,
                  original_fixture_runtime=manifest['torch_version'], original_fixture_tolerance=dict(rtol=2e-5, atol=3e-6),
                  parameters=parameter_checks, fixture_nodes=fixture_checks,
                  preprocessing=preprocessing_tests(out),
                  holdout=real_image_checks(model, state, args.image_root, out) if args.image_root else [],
                  integer_audit=independent_integer_audit(args.package, state, out) if args.package else None,
                  golden_file_audit=audit_golden_files(args.golden, args.package, out) if args.golden else None,
                  limitations=['Holdout means exact-SHA training/validation exclusion only; near duplicates and camera independence are unaudited.',
                               'Student target is a dehazing teacher, not clear/rain ground truth.',
                               'Host timing includes two graph executions; it is not an inference benchmark or FPGA performance.',
                               'Original private training programs were not present; source provenance hashes are recorded, not independently reproduced.'])
    report_path = out / 'audit_fp32.json'
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS', report=str(report_path), fixture_nodes=len(fixture_checks),
                          holdout_images=len(report['holdout']),
                          max_fixture_abs=max(r['source_max_abs'] for r in fixture_checks))))


if __name__ == '__main__':
    main()
