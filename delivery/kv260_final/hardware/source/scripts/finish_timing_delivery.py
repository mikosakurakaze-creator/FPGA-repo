"""Audit, inherit, sign off and package a completed physical timing experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ('parent', 'experiment', 'build', 'host', 'fusion', 'golden', 'controller-tests', 'out', 'run'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    a.run.mkdir(parents=True, exist_ok=False)
    result = {'pass': False, 'board_operations': 0, 'steps': []}

    def run(name, script, args):
        cmd = [sys.executable, '-X', 'utf8', '-B', str(ROOT/'scripts'/script), *map(str, args)]
        log = a.run / (name + '.log')
        print('TIMING_DELIVERY_STAGE=' + name + ' LOG=' + str(log), flush=True)
        start = time.perf_counter()
        with log.open('xb') as stream:
            proc = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, cwd=a.run)
        result['steps'].append({'stage': name, 'command': cmd, 'exit_code': proc.returncode,
                                'seconds': time.perf_counter()-start, 'log_sha256': sha(log)})
        if proc.returncode:
            raise RuntimeError(name + ' failed; inspect ' + str(log))

    try:
        audit = a.run / 'timing_margin_audit.json'
        run('margin_audit', 'verify_timing_margin.py', ['--experiment', a.experiment, '--out', audit])
        run('inherit', 'inherit_timing_build.py', ['--parent', a.parent, '--experiment', a.experiment,
                                                '--margin-audit', audit, '--out', a.build])
        run('coverage', 'build_system.py', ['--out', a.build, '--stage', 'coverage'])
        run('accept', 'accept_system.py', ['--build', a.build, '--host', a.host, '--fusion', a.fusion, '--golden', a.golden])
        run('export', 'build_system.py', ['--out', a.build, '--stage', 'export'])
        run('collect', 'collect_delivery.py', ['--build', a.build, '--host', a.host, '--fusion', a.fusion,
            '--golden', a.golden, '--controller-tests', a.controller_tests, '--out', a.out])
        archive = a.out.with_suffix('.zip')
        verified = a.out.parent / (a.out.name + '_verified.json')
        run('verify', 'verify_delivery.py', ['--zip', archive, '--out', verified])
        result.update({'pass': True, 'zip': archive.as_posix(), 'zip_sha256': sha(archive),
                       'verification': verified.as_posix()})
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        (a.run/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
