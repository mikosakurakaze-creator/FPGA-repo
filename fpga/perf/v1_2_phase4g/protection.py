"""Hash protected Phase 4 inputs/evidence without changing any protected file."""
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')
OUT = RUN / 'phase4g'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def records(roots):
    result = {}
    for root in roots:
        if not root.exists():
            raise RuntimeError('Missing protected input: ' + str(root))
        paths = [root] if root.is_file() else sorted(root.rglob('*'))
        for path in paths:
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                result[path.resolve().as_posix()] = sha(path)
    return result


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('before', 'after'), required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / ('protection_' + args.phase + '.json')
    if output.exists():
        raise RuntimeError('Refusing to overwrite audit: ' + str(output))
    recovery_path = RUN / 'recovery_manifest.json'
    recovery = json.loads(recovery_path.read_text())
    changed = [p for p, entry in recovery['files'].items()
               if not Path(p).is_file() or sha(Path(p)) != entry['sha256']]
    if changed:
        raise RuntimeError('Original recovery audit changed: ' + repr(changed))
    roots = [
        recovery_path,
        REPO / 'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4',
        REPO / 'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4_writecredit',
        REPO / 'fpga/perf/v1_2_phase4e', REPO / 'fpga/perf/v1_2_phase4f',
        REPO / 'fpga/perf/v1_2_phase4b/shared_axi_ddr_v2.sv',
        REPO / 'fpga/docs/v1_fixed_point_protocol.json',
        REPO / 'fpga/docs/v1_fixed_point_protocol.md',
        REPO / 'fpga/reports/v1_2_phase4e_write_retirement_optimization.md',
        REPO / 'fpga/reports/v1_2_phase4f_short_multiframe.md',
        RUN / 'cnn_r4_export/hls/impl/ip', RUN / 'ip_repo',
        RUN / 'phase4e_system_02', RUN / 'phase4e_writer_probe_03',
        RUN / 'phase4f_system_01', RUN / 'phase4f_system_02',
        RUN / 'phase4f_protection_before.json', RUN / 'phase4f_protection_after.json',
    ]
    current = records(roots)
    checkpoint = REPO / 'fpga/reports/v1_2_phase4_checkpoint.md'
    if args.phase == 'before':
        backup = OUT / 'checkpoint_before.md'
        if backup.exists():
            raise RuntimeError('Checkpoint backup already exists')
        shutil.copyfile(checkpoint, backup)
        backup_hash = sha(backup)
        baseline = dict(branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
                        tracked_diff=git('diff', '--stat'), staged_diff=git('diff', '--cached', '--stat'),
                        status=git('status', '--short', '--untracked-files=all'))
    else:
        before = json.loads((OUT / 'protection_before.json').read_text())
        if before['files'] != current:
            missing = sorted(set(before['files']) - set(current))
            added = sorted(set(current) - set(before['files']))
            altered = [p for p in set(before['files']) & set(current) if before['files'][p] != current[p]]
            raise RuntimeError(repr(dict(missing=missing, added=added, altered=altered)))
        baseline = before['git_before']
        if git('branch', '--show-current') != baseline['branch'] or git('rev-parse', 'HEAD') != baseline['head']:
            raise RuntimeError('Branch or HEAD changed')
        if git('diff', '--stat') != baseline['tracked_diff'] or git('diff', '--cached', '--stat') != baseline['staged_diff']:
            raise RuntimeError('Tracked/staged diff changed')
        backup_hash = before['checkpoint_backup_sha256']
        if sha(OUT / 'checkpoint_before.md') != backup_hash:
            raise RuntimeError('Checkpoint backup changed')
    result = dict(status='PASS', phase=args.phase,
                  checked_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  original_protected_files=len(recovery['files']), original_changed=[],
                  additional_protected_files=len(current), before_after_identity='PASS' if args.phase == 'after' else 'BASELINE',
                  git_before=baseline, checkpoint_backup_sha256=backup_hash,
                  protected_roots=[p.as_posix() for p in roots], files=current)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'phase', 'original_protected_files',
                                         'additional_protected_files', 'before_after_identity')}))


if __name__ == '__main__':
    main()
