"""Compile and independently regress all 22 D INT16 node boundaries.

Run from the repository root: python -m models.compact_d.fixed.check_oracle
  --package PATH --out NEW_DIRECTORY [--compiler g++] [--full-frame]
Only the Python comparison harness needs NumPy; oracle.cpp has no dependencies
beyond the C++17 standard library. Host timings are not HLS or FPGA timings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

import numpy as np

from .numeric import load_package, run


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
I64_MIN, I64_MAX = -(1 << 63), (1 << 63) - 1


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(command, **kwargs):
    result = subprocess.run([str(c) for c in command], capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stdout}\n{result.stderr}")
    return result


def integer_round(value, shift):
    """Pure Python unlimited-integer oracle, independent of NumPy primitives."""
    if not -62 <= shift <= 62:
        return None
    if shift < 0:
        result = value * (1 << -shift)
        return result if I64_MIN <= result <= I64_MAX else None
    if shift == 0:
        return value
    quotient, remainder = divmod(abs(value), 1 << shift)
    result = quotient + (remainder >= 1 << (shift - 1))
    return -result if value < 0 else result


def arithmetic_check(exe):
    cases = set()
    edges = [I64_MIN, I64_MIN + 1, -(1 << 62), -65536, -32769, -32768, -32767,
             -16384, -3, -2, -1, 0, 1, 2, 3, 16384, 32766, 32767, 32768,
             65535, (1 << 62) - 1, 1 << 62, I64_MAX - 1, I64_MAX]
    for shift in range(-63, 64):
        cases.update((value, shift) for value in edges)
        if shift > 0:
            for multiple in [-32768, -3, -2, -1, 0, 1, 2, 3, 32767]:
                for delta in [-1, 0, 1]:
                    value = multiple * (1 << shift) + (1 << (shift - 1)) + delta
                    if I64_MIN <= value <= I64_MAX:
                        cases.add((value, shift))
    rng = random.Random(0xD1A600D)
    cases.update((rng.randint(I64_MIN, I64_MAX), rng.randint(-62, 62)) for _ in range(4096))
    cases = sorted(cases)
    payload = ''.join(f'{value} {shift}\n' for value, shift in cases)
    actual = execute([exe, '--arithmetic'], input=payload).stdout.splitlines()
    if len(actual) != len(cases):
        raise AssertionError('C++ arithmetic result count differs')
    for (value, shift), line in zip(cases, actual):
        expected = integer_round(value, shift)
        target = 'ERROR' if expected is None else f'{expected} {min(32767, max(-32768, expected))}'
        if line != target:
            raise AssertionError(f'RHAZ/sat mismatch for ({value},{shift}): {line!r} != {target!r}')
    return len(cases)


def compiler_default():
    compiler = shutil.which('g++')
    if compiler:
        return compiler
    bundled = Path('C:/msys64/ucrt64/bin/g++.exe')
    if bundled.is_file():
        return str(bundled)
    raise FileNotFoundError('g++ not found; specify --compiler or a prebuilt --exe')


def reject_check(exe, package, out):
    # Validate public dimensions, byte count, representable normalized-input
    # range, and the rule that existing output directories are never replaced.
    good = out/'reject_good.i16'
    good.write_bytes(np.zeros((1, 3, 1, 1), dtype='<i2').tobytes())
    short = out/'reject_short.i16'
    short.write_bytes(b'\0')
    invalid = out/'reject_range.i16'
    invalid.write_bytes(np.array([0, 0, 16385], dtype='<i2').tobytes())
    tests = [
        ('height_zero', good, 0, 1, out/'reject_height'),
        ('height_excess', good, 721, 1, out/'reject_height_excess'),
        ('width_excess', good, 1, 1281, out/'reject_width_excess'),
        ('truncated_input', short, 1, 1, out/'reject_short'),
        ('range_excess', invalid, 1, 1, out/'reject_range'),
        ('existing_output', good, 1, 1, out),
    ]
    report = []
    for name, source, height, width, output in tests:
        result = subprocess.run([str(exe), str(package), str(source), str(height), str(width), str(output)],
                                capture_output=True, text=True)
        if result.returncode == 0 or 'D_CPP_ORACLE_FAIL:' not in result.stderr:
            raise AssertionError('C++ oracle accepted invalid public input: '+name)
        report.append(dict(test=name, rejected=True, reason=result.stderr.strip()))
    return report


def compare_case(exe, package, out, name, qinput):
    case = out/name
    case.mkdir()
    source = case/'input.i16'
    source.write_bytes(qinput.astype('<i2', copy=False).tobytes())
    h, w = qinput.shape[-2:]
    start = time.perf_counter()
    result = execute([exe, package, source, h, w, case/'cpp'])
    host_seconds = time.perf_counter() - start
    layers = []

    def observer(index, node, value, stats):
        filename = f'{index:02}_{node["id"]}.i16'
        path = case/'cpp'/filename
        raw = path.read_bytes()
        expected = value.astype('<i2', copy=False).tobytes()
        if raw != expected:
            actual = np.frombuffer(raw, dtype='<i2')
            target = value.reshape(-1)
            if actual.size != target.size:
                raise AssertionError(f'{name}/{node["id"]}: byte length differs')
            bad = int(np.flatnonzero(actual != target)[0])
            raise AssertionError(f'{name}/{node["id"]}: mismatch at flat NCHW index {bad}, C++={actual[bad]}, Python={target[bad]}')
        layers.append(dict(index=index, node=node['id'], shape=list(value.shape),
                           bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                           exact_equal=True, **stats))

    python_start = time.perf_counter()
    run(package, qinput, observer=observer)
    python_seconds = time.perf_counter() - python_start
    if len(layers) != 22:
        raise AssertionError('D comparison did not inspect all 22 nodes')
    report = dict(case=name, input_shape=list(qinput.shape), input_sha256=digest(source),
                  cpp_stdout=result.stdout.strip(), cpp_host_seconds=host_seconds,
                  python_host_seconds=python_seconds, compared_nodes=len(layers),
                  exact_equal=True, layers=layers)
    (case/'comparison.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    return report


def suite(package, out, compiler=None, exe=None, full_frame=False):
    package, out = Path(package).resolve(), Path(out).resolve()
    manifest, _, _ = load_package(package)  # authenticate bundle and every byte
    if out.exists():
        raise FileExistsError('Refuse to overwrite oracle regression: '+str(out))
    out.mkdir(parents=True)
    compile_command = None
    compiler_version = None
    if exe:
        exe = Path(exe).resolve()
        if not exe.is_file():
            raise FileNotFoundError(exe)
    else:
        compiler = compiler or compiler_default()
        exe = out/('oracle.exe' if os.name == 'nt' else 'oracle')
        compile_command = [str(compiler), '-std=c++17', '-O3', '-Wall', '-Wextra', '-pedantic', str(HERE/'oracle.cpp'), '-o', str(exe)]
        compiler_version = execute([compiler, '--version']).stdout.splitlines()[0]
        build = execute(compile_command)
        (out/'compiler.stdout.txt').write_text(build.stdout, encoding='utf-8')
        (out/'compiler.stderr.txt').write_text(build.stderr, encoding='utf-8')
    arithmetic_cases = arithmetic_check(exe)
    rejected = reject_check(exe, package, out)
    rng = np.random.default_rng(20261025)
    cases = []
    for name, h, w in [('one_pixel', 1, 1), ('single_row', 1, 9), ('single_column', 7, 1),
                       ('odd_edges', 7, 9), ('odd_random', 17, 19), ('tile_random', 64, 96)]:
        qinput = rng.integers(-16384, 16385, size=(1, 3, h, w), dtype=np.int16)
        qinput.reshape(-1)[::7] = -16384
        qinput.reshape(-1)[1::7] = 16384
        qinput.reshape(-1)[2::7] = 0
        cases.append(compare_case(exe, package, out, name, qinput))
    for name, value in [('black', -16384), ('gray', 0), ('white', 16384)]:
        cases.append(compare_case(exe, package, out, name,
                                  np.full((1, 3, 9, 11), value, dtype=np.int16)))
    if full_frame:
        qinput = rng.integers(-16384, 16385, size=(1, 3, 720, 1280), dtype=np.int16)
        cases.append(compare_case(exe, package, out, 'full_720p_random', qinput))
    summary = dict(status='D_CPP_ORACLE_REGRESSION_PASS', bundle_id=manifest['bundle_id'],
                   checkpoint_sha256=manifest['checkpoint_sha256'],
                   oracle_source_sha256=digest(HERE/'oracle.cpp'),
                   harness_source_sha256=digest(Path(__file__)), executable_sha256=digest(exe),
                   compiler_version=compiler_version, compile_command=compile_command,
                   python_version=sys.version, numpy_version=np.__version__,
                   arithmetic_cases=arithmetic_cases, rejection_tests=rejected,
                   cases=cases, total_exact_node_comparisons=sum(c['compared_nodes'] for c in cases),
                   performance_scope='Host executable and Python reference wall-clock only; no HLS, RTL, Vivado or board claim')
    (out/'report.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--out', required=True)
    build = parser.add_mutually_exclusive_group()
    build.add_argument('--compiler')
    build.add_argument('--exe')
    parser.add_argument('--full-frame', action='store_true')
    args = parser.parse_args()
    report = suite(args.package, args.out, args.compiler, args.exe, args.full_frame)
    print(json.dumps({k: report[k] for k in ('status', 'bundle_id', 'arithmetic_cases', 'total_exact_node_comparisons')}))


if __name__ == '__main__':
    main()
