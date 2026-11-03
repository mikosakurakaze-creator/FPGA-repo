"""Continue the authorized six-node build through mapping, routing and audit only.

Wait for the explicitly named synthesis receipt. No fallback builds, export,
packaging, Git actions, board actions or resource/space monitoring are performed.
"""
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
    for name in ('source-flow', 'build', 'parent-audit', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--proof', type=Path, action='append', required=True)
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'pass': False, 'stage': 'waiting_for_named_synthesis', 'started_at': now(),
              'board_operations': 0, 'export_allowed': False, 'steps': [], 'bound_files': {}}

    def bind(path, digest=None):
        path = Path(path).resolve()
        actual = sha(path)
        if digest is not None and digest != actual:
            raise ValueError('Continuation input changed: ' + str(path))
        result['bound_files'][path.as_posix()] = actual
        return path

    def save():
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')

    def run(stage, script, argv):
        # Execution uses the exact script snapshot frozen at startup.
        result['stage'] = stage
        save()
        print('TARGETED_CONTINUE_STAGE=' + stage + ' START=' + now(), flush=True)
        command = [sys.executable, '-X', 'utf8', '-B', str(out / script), *map(str, argv)]
        start = time.perf_counter()
        with (out / (stage + '.log')).open('xb') as f:
            process = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=out)
        row = {'stage': stage, 'exit_code': process.returncode, 'finished_at': now(),
               'seconds': time.perf_counter() - start, 'log_sha256': sha(out / (stage + '.log')), 'command': command}
        result['steps'].append(row)
        save()
        if process.returncode:
            raise RuntimeError(stage + ' failed; inspect the preserved output, no automatic fallback')
        print('TARGETED_CONTINUE_COMPLETE=' + stage + ' AT=' + row['finished_at'], flush=True)

    try:
        # Freeze all direct and imported project scripts, then execute snapshots.
        for path in ROOT.glob('*.py'):
            shutil.copy2(path, out / path.name)
            bind(out / path.name)
        for name in ('timing_margin.tcl', 'audit_targeted_fifo_mapping.tcl'):
            shutil.copy2(ROOT / name, out / name)
            bind(out / name)
        parent = json.loads(bind(a.parent_audit).read_text())
        if not parent['pass'] or not parent.get('independent_axi_revalidation'):
            raise ValueError('The current parent audit is not valid')
        reference = bind(Path(parent['experiment']) / 'optimized_routed.dcp', parent['checkpoint_sha256'])
        save()
        deadline = time.monotonic() + 7200
        while True:
            try:
                flow = json.loads((a.source_flow / 'result.json').read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                flow = {}
            if flow.get('pass') or flow.get('error'):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('The named synthesis flow did not finish; no other build was started')
            time.sleep(5)
        bind(a.source_flow / 'result.json')
        if not flow.get('pass') or flow.get('stage') != 'through_synthesis':
            raise ValueError('The named synthesis flow failed')
        for name, digest in flow['bound_files'].items():
            bind(name, digest)
        synthesis = bind(a.build / 'joint_synth.dcp', flow['checkpoint_sha256'])
        result['joint_synthesis_completed_at'] = flow['joint_synthesis_completed_at']
        print('JOINT_SYNTHESIS_COMPLETED_AT=' + flow['joint_synthesis_completed_at'], flush=True)
        mapping = out / 'mapping01'
        run('mapping', 'optimize_timing_margin.py', ['--checkpoint', synthesis, '--out', mapping,
            '--stage', 'inspect', '--tcl-script', out / 'audit_targeted_fifo_mapping.tcl'])
        implementation = out / 'implement01'
        run('implement', 'optimize_timing_margin.py', ['--checkpoint', synthesis, '--out', implementation,
            '--stage', 'implement', '--strategy', 'preplace', '--reference', reference,
            '--setup-margin', '0.300', '--hold-margin', '0.100', '--tcl-script', out / 'timing_margin.tcl'])
        reopen = out / 'reopen01'
        run('reopen', 'optimize_timing_margin.py', ['--checkpoint', implementation / 'optimized_routed.dcp',
            '--out', reopen, '--stage', 'verify', '--tcl-script', out / 'timing_margin.tcl'])
        audit_args = ['--parent-audit', a.parent_audit, '--source-flow', a.source_flow, '--build', a.build,
            '--experiment', implementation, '--reopen', reopen, '--out', out / 'audit01.json']
        for path in a.proof:
            audit_args += ['--saturation-proof', path]
        run('audit', 'audit_targeted_fifo_timing.py', audit_args)
        audit = json.loads(bind(out / 'audit01.json').read_text())
        if not audit['pass']:
            raise ValueError('Final audit incomplete')
        result.update(timing=audit['timing'], improvement_ns=audit['improvement_ns'], pass_=True,
                      checkpoint_sha256=audit['checkpoint_sha256'])
        result.pop('pass_')
        result['pass'] = True
        result['stage'] = 'audited_no_export'
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        result['finished_at'] = now()
        save()
        print(json.dumps({k: v for k, v in result.items() if k != 'bound_files'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
