"""Rebuild the six changed FIFO nodes in context; stop at joint synthesis."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def main():
    ap = argparse.ArgumentParser(__doc__)
    for name in ('parent', 'parent-audit', 'prepared', 'build', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--proof', type=Path, action='append', required=True)
    a = ap.parse_args()
    out, build = a.out.resolve(), a.build.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'pass': False, 'stage': 'through_synthesis', 'started_at': now(),
              'board_operations': 0, 'export_allowed': False, 'steps': [], 'bound_files': {}}

    def bind(path, digest=None):
        path = Path(path).resolve()
        actual = sha(path)
        if digest is not None and digest != actual:
            raise ValueError('Input identity changed: ' + str(path))
        result['bound_files'][path.as_posix()] = actual
        return path

    def save():
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')

    def run(name, script, argv):
        command = [sys.executable, '-X', 'utf8', '-B', str(ROOT / script), *map(str, argv)]
        print('TARGETED_SOURCE_STAGE=' + name + ' START=' + now(), flush=True)
        start = time.perf_counter()
        with (out / (name + '.log')).open('xb') as f:
            process = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=out)
        row = {'stage': name, 'exit_code': process.returncode, 'finished_at': now(),
               'seconds': time.perf_counter() - start, 'log_sha256': sha(out / (name + '.log')), 'command': command}
        result['steps'].append(row)
        save()
        if process.returncode:
            raise RuntimeError(name + ' failed; preserve its receipt')
        print('TARGETED_SOURCE_COMPLETE=' + name + ' AT=' + row['finished_at'], flush=True)

    try:
        for name in ('prepare_targeted_fifo_build.py', 'targeted_fifo_policy.tcl', 'targeted_fifo_mapping.py', 'build_system.py'):
            shutil.copy2(ROOT / name, out / name)
            bind(out / name)
        scopes = []
        for path in a.proof:
            proof = json.loads(bind(path).read_text())
            if not proof['pass'] or proof.get('fifo_mode') != 'targeted' or not proof.get('saturation_checked'):
                raise ValueError('Correctly isolated targeted saturation proof required')
            for group in ('source_files', 'verification_sources'):
                for name, digest in proof[group].items():
                    bind(path.parent / name, digest)
            for row in proof['steps']:
                bind(path.parent / (row['name'] + '.log'), row['log_sha256'])
                if row['exit_code']:
                    raise ValueError('AXI proof tool failed')
            scopes.append(proof['scope'])
        if len(scopes) != 2 or sum('32-bit SI / 128-bit MI' in s for s in scopes) != 1 or sum('128-bit SI / 128-bit MI' in s for s in scopes) != 1:
            raise ValueError('Both AXI widths are required')
        result['proofs'] = scopes
        run('prepare', 'prepare_targeted_fifo_build.py', ['--parent', a.parent, '--parent-audit', a.parent_audit,
            '--prepared', a.prepared, '--out', build])
        run('create', 'build_system.py', ['--out', build, '--stage', 'create'])
        sources = json.loads(bind(build / 'targeted_generated_sources.json').read_text())
        if len(sources) != 132 or len([row for row in sources if row['method'] != 'inherit']) != 12:
            raise ValueError('Only six sim/synth pairs may differ from the current parent')
        for row in sources:
            bind(build / row['path'], row['after'])
            bind(build / row['backup'], row['before'])
            bind(a.parent / row['path'], row['parent_current_sha256'])
        run('synth', 'build_system.py', ['--out', build, '--stage', 'synth'])
        for row in sources:
            bind(build / row['path'], row['after'])
        result['joint_synthesis_completed_at'] = result['steps'][-1]['finished_at']
        result['checkpoint_sha256'] = sha(bind(build / 'joint_synth.dcp'))
        result['build'] = build.as_posix()
        result['pass'] = True
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        result['finished_at'] = now()
        shutil.copy2(__file__, out / Path(__file__).name)
        bind(out / Path(__file__).name)
        save()
        print(json.dumps({k: v for k, v in result.items() if k != 'bound_files'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
