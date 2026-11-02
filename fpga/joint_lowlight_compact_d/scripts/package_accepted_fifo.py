"""Package a user-accepted six-FIFO candidate without synthesis or optimization.

Preserve all experimental records. Release approval is a new, checkpoint-bound
record; it does not rewrite the earlier no-export manifests or failed audits.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(__doc__)
    for name in ('source', 'audit', 'baseline', 'build', 'run', 'out', 'host', 'fusion', 'golden', 'controller-tests'):
        ap.add_argument('--' + name, required=True, type=Path)
    a = ap.parse_args()
    source, build, run = a.source.resolve(), a.build.resolve(), a.run.resolve()
    if build.exists() or run.exists() or a.out.exists() or a.out.with_suffix('.zip').exists():
        raise ValueError('Preserve earlier builds and packages')
    run.mkdir(parents=True)
    shutil.copy2(__file__, run / Path(__file__).name)
    result = {'pass': False, 'board_operations': 0, 'optimization_stages': 0, 'steps': [],
              'started_at': datetime.now().astimezone().isoformat(timespec='seconds')}

    def execute(name, script, arguments):
        command = [sys.executable, '-X', 'utf8', '-B', str(ROOT / 'scripts' / script), *map(str, arguments)]
        log = run / (name + '.log')
        print('ACCEPTED_FIFO_DELIVERY_STAGE=' + name, flush=True)
        start = time.perf_counter()
        with log.open('xb') as stream:
            proc = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, cwd=run)
        result['steps'].append({'stage': name, 'command': command, 'exit_code': proc.returncode,
                                'seconds': time.perf_counter()-start, 'log_sha256': sha(log)})
        save(run / 'result.json', result)
        if proc.returncode:
            raise RuntimeError(name + ' failed; preserve ' + str(log))

    try:
        audit = json.loads(a.audit.read_text())
        if not audit['pass'] or len(audit['replaced_nodes']) != 6 or not audit.get('synthesized_mapping'):
            raise ValueError('Exact six-node source/mapping/timing audit required')
        for name, digest in audit['bound_files'].items():
            if sha(name) != digest:
                raise ValueError('Accepted audit evidence changed: ' + name)
        experiment = Path(audit['experiment'])
        receipt = json.loads((experiment / 'result.json').read_text())
        if not receipt['pass'] or receipt['source_checkpoint_sha256'] != sha(source / 'joint_synth.dcp'):
            raise ValueError('Source synthesis identity differs from accepted physical experiment')
        if sha(experiment / 'optimized_routed.dcp') != audit['checkpoint_sha256']:
            raise ValueError('Accepted routed checkpoint changed')
        inputs = json.loads((source / 'inputs.json').read_text())
        for name, digest in inputs['source_files'].items():
            if sha(source / name) != digest:
                raise ValueError('Accepted build input changed: ' + name)
        build.mkdir(parents=True)
        (build / 'reports').mkdir()

        def copy(path, relative):
            target = build / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

        for name in inputs['source_files']:
            copy(source / name, name)
        approval = {'scope': 'Export and ZIP this accepted candidate only; stop optimization; no Git or board operations',
                    'user_instruction': '可以，这个结果能接受，不用优化了生成压缩包吧',
                    'checkpoint_sha256': audit['checkpoint_sha256'], 'audit_sha256': sha(a.audit),
                    'source_inputs_sha256': sha(source / 'inputs.json'), 'timing': audit['timing'],
                    'export_allowed': True, 'board_operations': 0}
        copy(source / 'inputs.json', 'accepted_original_inputs.json')
        save(build / 'release_approval.json', approval)
        for key in ('rtl_timing_variant', 'targeted_fifo_variant'):
            if key in inputs:
                inputs[key]['export_allowed'] = True
                inputs[key]['release_approval_sha256'] = sha(build / 'release_approval.json')
        inputs['release_approval'] = approval
        save(build / 'inputs.json', inputs)
        save(build / 'prepare_release_result.json', {'pass': True, 'stage': 'prepare', 'board_operations': 0,
             'kind': 'Copy of audited synthesized source; no source generation repeated',
             'source_build': source.as_posix(), 'source_inputs_sha256': approval['source_inputs_sha256'],
             'release_approval_sha256': sha(build / 'release_approval.json')})
        source_gates = json.loads((source / 'gates.json').read_text())
        gates = {'prepare': 'prepare_release_result.json'}
        for stage in ('adapter', 'create', 'synth'):
            name = source_gates[stage]
            copy(source / name, name)
            row = json.loads((source / name).read_text())
            if not row['pass']:
                raise ValueError('Source stage failed: ' + stage)
            tag = name.removesuffix('_result.json')
            if row.get('steps'):
                log = tag + ('.log' if stage == 'adapter' else '_console.log')
                if len(row['steps']) != 1 or sha(source / log) != row['steps'][0]['log_sha256']:
                    raise ValueError('Inherited process identity differs: ' + stage)
                copy(source / log, log)
            if 'script_sha256' in row:
                if sha(source / (tag + '_build.tcl')) != row['script_sha256']:
                    raise ValueError('Inherited Tcl identity differs')
                copy(source / (tag + '_build.tcl'), tag + '_build.tcl')
            gates[stage] = name
        for name in ('fusion_pipeline_acceptance.json', 'prepare_pipeline_acceptance.json'):
            copy(a.baseline / name, name)
        for file in experiment.iterdir():
            if file.is_file() and file.suffix in ('.rpt', '.txt', '.xdc', '.json', '.tcl', '.py', '.log', '.jou'):
                copy(file, 'physical_optimization/' + file.name)
        for folder in ('mapping01', 'reopen01'):
            for file in (a.audit.parent / folder).iterdir():
                if file.is_file() and file.suffix in ('.rpt', '.txt', '.tsv', '.xdc', '.json', '.tcl', '.py', '.log', '.jou'):
                    copy(file, 'physical_optimization/' + folder + '/' + file.name)
        for file in (a.audit, a.audit.parent / 'audit01.json', a.audit.parent / 'compiled_constraints02.json'):
            copy(file, 'physical_optimization/' + file.name)
        for name in ('routed_timing.rpt', 'routed_utilization.rpt', 'route_status.rpt', 'routed_drc.rpt',
                     'routed_cdc.rpt', 'routed_clock_interaction.rpt'):
            copy(experiment / name, 'reports/' + name)
        copy(experiment / 'optimized_routed.dcp', 'joint_routed.dcp')
        copy(experiment / 'console.log', 'implement_margin_console.log')
        copy(experiment / 'timing_margin.tcl', 'implement_margin_build.tcl')
        copy(a.audit, 'timing_margin_audit.json')
        save(build / 'implement_margin_result.json', {'pass': True, 'stage': 'implement', 'board_operations': 0,
             'implementation_kind': 'targeted_fifo_rebuild', 'checkpoint_sha256': audit['checkpoint_sha256'],
             'source_checkpoint_sha256': receipt['source_checkpoint_sha256'], 'audit_sha256': sha(a.audit),
             'script_sha256': receipt['script_sha256'],
             'steps': [{k: receipt[k] for k in ('command', 'exit_code', 'seconds', 'log_sha256')}]})
        gates['implement'] = 'implement_margin_result.json'
        save(build / 'gates.json', gates)
        lineage = {'pass': True, 'kind': 'targeted_fifo_rebuild', 'parent_build': source.as_posix(),
                   'experiment': experiment.as_posix(), 'checkpoint_sha256': audit['checkpoint_sha256'],
                   'margin_audit_sha256': sha(a.audit), 'source_inputs_sha256': approval['source_inputs_sha256'],
                   'release_approval_sha256': sha(build / 'release_approval.json'), 'board_operations': 0,
                   'note': 'No optimization during release. Historical no-export/failed records are preserved.'}
        save(build / 'timing_lineage.json', lineage)
        execute('coverage', 'build_system.py', ['--out', build, '--stage', 'coverage'])
        execute('accept', 'accept_system.py', ['--build', build, '--host', a.host, '--fusion', a.fusion, '--golden', a.golden])
        execute('export', 'build_system.py', ['--out', build, '--stage', 'export'])
        execute('collect', 'collect_delivery.py', ['--build', build, '--host', a.host, '--fusion', a.fusion,
                 '--golden', a.golden, '--controller-tests', a.controller_tests, '--out', a.out])
        verified = run / 'zip_verified.json'
        execute('verify', 'verify_delivery.py', ['--zip', a.out.with_suffix('.zip'), '--out', verified])
        result.update({'pass': True, 'zip': a.out.with_suffix('.zip').as_posix(),
                       'zip_sha256': sha(a.out.with_suffix('.zip')), 'verification': verified.as_posix()})
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        result['finished_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
        save(run / 'result.json', result)
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
