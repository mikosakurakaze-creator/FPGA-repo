"""One-command D package, Golden, independent oracle, and delivery reproduction.

python -m models.compact_d.fixed.reproduce --out NEW_DIRECTORY
  [--image-list PRIVATE_IMAGES_JSON] [--compiler g++] [--skip-scalar-audit]

The image list is an optional JSON array of paths; relative paths are resolved
against its containing directory. No dataset or hardware tool is downloaded.
Every run includes synthetic and full720p evidence. HLS/Vivado and physical-board
flows are separate, explicit operations and are not launched by this command.
The output directory must not exist; evidence from earlier runs is preserved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')


def compare_packages(first, second):
    first_files = {p.relative_to(first).as_posix(): p for p in first.rglob('*') if p.is_file()}
    second_files = {p.relative_to(second).as_posix(): p for p in second.rglob('*') if p.is_file()}
    if first_files.keys() != second_files.keys():
        raise ValueError('Deterministic export filenames differ')
    files = []
    for name in sorted(first_files):
        a, b = first_files[name], second_files[name]
        # Compare actual bytes as well as hashes, not only a reported bundle ID.
        if a.read_bytes() != b.read_bytes():
            raise ValueError('Deterministic export bytes differ: '+name)
        files.append(dict(file=name, bytes=a.stat().st_size, sha256=sha(a), byte_exact=True))
    a = json.loads((first/'manifest.json').read_text(encoding='utf-8'))
    b = json.loads((second/'manifest.json').read_text(encoding='utf-8'))
    if a['bundle_id'] != b['bundle_id']:
        raise ValueError('Deterministic export bundle identities differ')
    return dict(status='D_DETERMINISTIC_EXPORT_PASS', bundle_id=a['bundle_id'],
                compared_files=len(files), all_bytes_identical=True, files=files)


def image_manifest(source, out):
    source = Path(source).resolve()
    paths = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(paths, list) or not paths or any(not isinstance(p, str) for p in paths):
        raise ValueError('Image list must be a nonempty JSON array of paths')
    reserved = {'black', 'white', 'gray', 'red', 'green', 'blue', 'checker', 'impulse', 'random',
                'random_1x1', 'random_1x7', 'random_7x1', 'random_2x3', 'random_8x8', 'random_33x47', 'pattern_720p'}
    resolved, records, names = [], [], set()
    for value in paths:
        path = Path(value)
        path = (source.parent/path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_file():
            raise FileNotFoundError('Listed image not found: '+str(path))
        if not path.stem or path.stem in reserved or path.stem in names:
            raise ValueError('Duplicate or reserved image case name: '+path.stem)
        names.add(path.stem)
        resolved.append(str(path))
        records.append(dict(case=path.stem, path=str(path), bytes=path.stat().st_size, sha256=sha(path)))
    target = out/'resolved_image_list.json'
    write_json(target, resolved)
    identity = dict(source_list=str(source), source_list_sha256=sha(source), images=records)
    write_json(out/'private_image_identity.json', identity)
    return target, identity


def reproduce(out, image_list=None, compiler=None, scalar_audit=True):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Refuse to overwrite reproduction output: '+str(out))
    out.mkdir(parents=True)
    (out/'logs').mkdir()
    scales = HERE/'scales.json'
    snapshot = {p.relative_to(ROOT).as_posix(): sha(p)
                for p in sorted(HERE.iterdir()) if p.is_file() and p.suffix in ('.py', '.cpp', '.json', '.md')}
    state = dict(format='compact-d-reproduction-v1', status='RUNNING', start_utc=utc_now(),
                 output=str(out), python_executable=sys.executable, python_version=sys.version,
                 platform=platform.platform(), repository_root=str(ROOT),
                 frozen_scales_sha256=sha(scales), source_snapshot_sha256=snapshot,
                 source_checkpoint_sha256=sha(HERE.parent/'weights/d_best_fp32.pth'),
                 scalar_fraction_audit_requested=scalar_audit, subprocesses=[],
                 scope='CPU software reproduction only; no training, network access, HLS/Vivado, FPGA interface mutation or physical-board operation')
    record_path = out/'run_manifest.json'
    write_json(record_path, state)
    environment = os.environ.copy()
    environment['PYTHONHASHSEED'] = '0'

    def run_stage(name, module, arguments):
        command = [sys.executable, '-m', module, *map(str, arguments)]
        stdout_path, stderr_path = out/'logs'/(name+'.stdout.txt'), out/'logs'/(name+'.stderr.txt')
        record = dict(stage=name, argv=command, cwd=str(ROOT), start_utc=utc_now(),
                      stdout=str(stdout_path.relative_to(out)), stderr=str(stderr_path.relative_to(out)),
                      environment_overrides={'PYTHONHASHSEED': '0'}, returncode=None)
        state['subprocesses'].append(record)
        write_json(record_path, state)
        print('D_REPRODUCE_START '+name, flush=True)
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
        record.update(end_utc=utc_now(), returncode=result.returncode,
                      stdout_sha256=sha(stdout_path), stderr_sha256=sha(stderr_path))
        write_json(record_path, state)
        if result.returncode:
            raise RuntimeError(f'Reproduction stage {name} failed with code {result.returncode}; inspect {stderr_path}')
        print('D_REPRODUCE_PASS '+name, flush=True)

    try:
        normalized_images = None
        if image_list:
            normalized_images, identities = image_manifest(image_list, out)
            state['private_images'] = identities
            write_json(record_path, state)
        run_stage('export', 'models.compact_d.fixed.export', ['--out', out/'package', '--scales', scales])
        run_stage('export_repeat', 'models.compact_d.fixed.export', ['--out', out/'package_repeat', '--scales', scales])
        deterministic = compare_packages(out/'package', out/'package_repeat')
        write_json(out/'deterministic_export.json', deterministic)
        state['bundle_id'] = deterministic['bundle_id']
        run_stage('arithmetic', 'unittest', ['-v', 'models.compact_d.fixed.test_numeric'])
        audit_args = ['--out', out/'fp32_audit']
        if scalar_audit:
            audit_args += ['--package', out/'package']
        run_stage('fp32_audit', 'models.compact_d.fixed.audit_fp32', audit_args)
        golden_args = ['--package', out/'package', '--out', out/'golden', '--720p']
        if normalized_images:
            golden_args += ['--image-list', normalized_images]
        run_stage('golden', 'models.compact_d.fixed.suite', golden_args)
        oracle_args = ['--package', out/'package', '--out', out/'oracle', '--full-frame']
        if compiler:
            oracle_args += ['--compiler', compiler]
        run_stage('cpp_oracle', 'models.compact_d.fixed.check_oracle', oracle_args)
        run_stage('delivery_audit', 'models.compact_d.fixed.verify_delivery',
                  ['--package', out/'package', '--golden', out/'golden', '--oracle', out/'oracle',
                   '--report', out/'delivery_audit.json'])
        # Detect a concurrent source modification rather than combining results
        # from different implementations into an apparently successful run.
        for name, expected in snapshot.items():
            if sha(ROOT/name) != expected:
                raise ValueError('Source changed during reproduction: '+name)
        summary = dict(status='D_REPRODUCTION_PASS', bundle_id=deterministic['bundle_id'],
                       all_package_bytes_identical=True,
                       golden_cases=len(json.loads((out/'golden/summary.json').read_text())['cases']),
                       independent_cpp_nodes=json.loads((out/'oracle/report.json').read_text())['total_exact_node_comparisons'],
                       arithmetic_unittest_passed=True, scalar_fraction_audit_executed=scalar_audit,
                       source_snapshot_unchanged=True,
                       evidence={name: dict(file=name, sha256=sha(out/name)) for name in
                                 ['deterministic_export.json', 'fp32_audit/audit_fp32.json',
                                  'golden/summary.json', 'oracle/report.json', 'delivery_audit.json']},
                       private_images_supplied=bool(image_list), end_utc=utc_now(),
                       hardware_scope='No HLS, RTL, Vivado or physical-board performance result is produced')
        if scalar_audit:
            summary['evidence']['fp32_audit/audit_fp32_integer.json'] = dict(
                file='fp32_audit/audit_fp32_integer.json', sha256=sha(out/'fp32_audit/audit_fp32_integer.json'))
        write_json(out/'summary.json', summary)
        state.update(status='PASS', end_utc=summary['end_utc'], summary_sha256=sha(out/'summary.json'))
        write_json(record_path, state)
        return summary
    except BaseException as error:
        state.update(status='FAIL', end_utc=utc_now(), error_type=type(error).__name__, error=str(error))
        write_json(record_path, state)
        raise


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--image-list')
    parser.add_argument('--compiler')
    parser.add_argument('--skip-scalar-audit', action='store_true', help='Skip optional small-shape Fraction/scalar integer audit')
    args = parser.parse_args()
    report = reproduce(args.out, args.image_list, args.compiler, not args.skip_scalar_audit)
    print(json.dumps({k: report[k] for k in ('status', 'bundle_id', 'golden_cases', 'independent_cpp_nodes')}))


if __name__ == '__main__':
    main()
