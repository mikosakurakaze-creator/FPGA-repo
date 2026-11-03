"""Create a new build from an audited physical optimization; retain all ancestry."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ('parent', 'experiment', 'margin-audit', 'out'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    parent, experiment, out = a.parent.resolve(), a.experiment.resolve(), a.out.resolve()
    if out.exists():
        raise ValueError('Preserve existing build')
    acceptance = json.loads((parent / 'acceptance.json').read_text())
    audit = json.loads(a.margin_audit.read_text())
    receipt = json.loads((experiment / 'result.json').read_text())
    if not (acceptance['pass'] and audit['pass'] and receipt['pass']):
        raise ValueError('Parent or physical optimization not accepted')
    if audit['experiment'] != experiment.as_posix():
        raise ValueError('Audit belongs to another experiment')
    parent_sha = sha(parent / 'joint_routed.dcp')
    if not (parent_sha == acceptance['checkpoint_sha256'] == audit['source_checkpoint_sha256']
            == receipt['source_checkpoint_sha256']):
        raise ValueError('Checkpoint ancestry differs')
    if sha(experiment / 'optimized_routed.dcp') != audit['checkpoint_sha256']:
        raise ValueError('Optimized checkpoint changed')
    for proof in (acceptance, audit):
        for name, digest in proof['bound_files'].items():
            if sha(name) != digest:
                raise ValueError('Inherited evidence changed: ' + name)
    inputs = json.loads((parent / 'inputs.json').read_text())
    for name, digest in inputs['source_files'].items():
        if sha(parent / name) != digest:
            raise ValueError('Parent input changed: ' + name)
    out.mkdir(parents=True)
    (out / 'reports').mkdir()
    lineage = {'pass': False, 'kind': 'postroute_physical_optimization',
               'parent_build': parent.as_posix(), 'parent_checkpoint_sha256': parent_sha,
               'parent_acceptance_sha256': sha(parent / 'acceptance.json'),
               'experiment': experiment.as_posix(),
               'experiment_result_sha256': sha(experiment / 'result.json'),
               'margin_audit_sha256': sha(a.margin_audit),
               'checkpoint_sha256': audit['checkpoint_sha256'],
               'inherited_stages': ['prepare', 'adapter', 'create', 'synth'],
               'source_rtl_model_weights_changed': False, 'board_operations': 0,
               'note': 'Inherited stage records/logs are original historical evidence. Only physical optimization, coverage, acceptance and export are rerun.'}

    def copy(source, relative):
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    try:
        copy(parent / 'inputs.json', 'inputs.json')
        for name in inputs['source_files']:
            copy(parent / name, name)
        old_gates = json.loads((parent / 'gates.json').read_text())
        gates = {}
        for stage in lineage['inherited_stages']:
            name = old_gates[stage]
            copy(parent / name, name)
            record = json.loads((parent / name).read_text())
            if not record['pass']:
                raise ValueError('Inherited stage failed: ' + stage)
            tag = name.removesuffix('_result.json')
            if record.get('steps'):
                log = tag + ('.log' if stage == 'adapter' else '_console.log')
                if len(record['steps']) != 1 or sha(parent / log) != record['steps'][0]['log_sha256']:
                    raise ValueError('Inherited process log differs')
                copy(parent / log, log)
            if 'script_sha256' in record:
                script = tag + '_build.tcl'
                if sha(parent / script) != record['script_sha256']:
                    raise ValueError('Inherited stage script differs')
                copy(parent / script, script)
            gates[stage] = name
        for name in ('fusion_pipeline_acceptance.json', 'prepare_pipeline_acceptance.json'):
            copy(parent / name, name)
        for file in (parent / 'reports').iterdir():
            if file.is_file() and not file.name.startswith(('routed_', 'export_', 'route_status')):
                copy(file, 'reports/' + file.name)
        for name in ('routed_timing.rpt', 'routed_utilization.rpt', 'route_status.rpt',
                     'routed_drc.rpt', 'routed_cdc.rpt', 'routed_clock_interaction.rpt'):
            copy(experiment / name, 'reports/' + name)
        copy(experiment / 'optimized_routed.dcp', 'joint_routed.dcp')
        copy(experiment / 'console.log', 'implement_margin_console.log')
        copy(experiment / 'timing_margin.tcl', 'implement_margin_build.tcl')
        copy(a.margin_audit, 'timing_margin_audit.json')
        for file in experiment.iterdir():
            if file.is_file() and file.suffix in ('.rpt', '.txt', '.xdc', '.json', '.tcl', '.py', '.log', '.jou'):
                copy(file, 'physical_optimization/' + file.name)
        copy(a.margin_audit, 'physical_optimization/audit.json')
        copy(parent / 'acceptance.json', 'inherited_baseline/acceptance.json')
        copy(parent / old_gates['implement'], 'inherited_baseline/implement_result.json')
        copy(parent / 'reports/routed_timing.rpt', 'inherited_baseline/routed_timing.rpt')
        record = {'stage': 'implement', 'pass': True, 'board_operations': 0,
                  'implementation_kind': lineage['kind'], 'parent_build': parent.as_posix(),
                  'source_checkpoint_sha256': parent_sha, 'checkpoint_sha256': audit['checkpoint_sha256'],
                  'source_result_sha256': lineage['experiment_result_sha256'],
                  'margin_audit_sha256': lineage['margin_audit_sha256'],
                  'script_sha256': receipt['script_sha256'],
                  'steps': [{k: receipt[k] for k in ('command', 'exit_code', 'seconds', 'log_sha256')}]}
        save(out / 'implement_margin_result.json', record)
        gates['implement'] = 'implement_margin_result.json'
        save(out / 'gates.json', gates)
        lineage['pass'] = True
    except Exception as exc:
        lineage['error'] = str(exc)
        raise
    finally:
        save(out / 'timing_lineage.json', lineage)
        print(json.dumps(lineage, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
