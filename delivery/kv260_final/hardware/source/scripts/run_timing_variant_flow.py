"""Finish an already-started timing-variant synthesis, route and independent audit.

Intentionally has no bitstream, hardware export, packaging, Git or board stage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from audit_timing_variant import hold_eco_rows, cell_snapshot, relocation_rows, register_parameter_rows
from accept_system import route_summary

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def validate_hold_probe(folder, setup_target, hold_target):
    probe = json.loads((folder/'result.json').read_text())
    if not probe['pass'] or probe['exit_code']:
        raise ValueError('Scoped hold ECO probe did not complete')
    for name, digest in probe['reports'].items():
        if sha(folder/name) != digest:
            raise ValueError('Scoped hold ECO probe changed: '+name)
    if probe['support_files']['fifo_hold_eco.tcl'] != sha(ROOT/'scripts/fifo_hold_eco.tcl'):
        raise ValueError('Current ECO helper differs from the passing probe')
    buffers = hold_eco_rows(folder/'hold_eco_final.tsv')
    if len(buffers) != 8 or buffers != hold_eco_rows(folder/'hold_eco_before_route.tsv'):
        raise ValueError('Probe must preserve all eight identity-buffer connections')
    expected = cell_snapshot(folder/'hold_eco_before_cells.tsv')
    if set(expected) & set(buffers):
        raise ValueError('Probe buffer overwrites an original primitive')
    expected.update({name:'LUT1' for name in buffers})
    for name in ('hold_eco_inserted_cells.tsv', 'hold_eco_final_cells.tsv'):
        if cell_snapshot(folder/name) != expected:
            raise ValueError('Probe changed original primitives')
    lines = (folder/'changed_path_checks.tsv').read_text().splitlines()
    if lines[0] != 'endpoint\tbefore_hold_ns\tafter_hold_ns\tafter_setup_ns':
        raise ValueError('Missing probe timing comparison')
    seen = set()
    for line in lines[1:]:
        endpoint, before, after, setup = line.split('\t')
        if endpoint in seen or not (float(after) >= hold_target and float(after) > float(before) and float(setup) >= setup_target):
            raise ValueError('Probe timing margin check failed')
        seen.add(endpoint)
    if seen != set(buffers.values()):
        raise ValueError('Incomplete probe endpoint timing coverage')
    route_summary((folder/'route_status.rpt').read_text())
    return sha(folder/'result.json')


def validate_relocation_probe(folder, setup_target, hold_target, helper=None):
    probe = json.loads((folder/'result.json').read_text())
    if not probe['pass'] or probe['exit_code']:
        raise ValueError('Register relocation probe failed')
    for name, digest in probe['reports'].items():
        if sha(folder/name) != digest:
            raise ValueError('Register relocation probe changed: '+name)
    if probe['support_files']['fifo_hold_relocate.tcl'] != sha(helper or ROOT/'scripts/fifo_hold_relocate.tcl'):
        raise ValueError('Current relocation helper differs from passing probe')
    registers = relocation_rows(folder/'relocation_after_route.tsv')
    if len(registers)!=8 or registers != relocation_rows(folder/'relocation_before_route.tsv'):
        raise ValueError('Probe must verify eight register relocations')
    if 'proc recreate_fifo_register ' in (folder/'fifo_hold_relocate.tcl').read_text():
        parameters = register_parameter_rows(folder/'reconstruction_before_parameters.tsv', registers)
        for name in ('relocation_before_route.tsv.parameters.tsv', 'relocation_after_route.tsv.parameters.tsv'):
            if register_parameter_rows(folder/name, registers) != parameters:
                raise ValueError('Probe reconstructed FDRE parameters changed')
    original = cell_snapshot(folder/'relocation_before_cells.tsv')
    for name in ('relocation_moved_cells.tsv','relocation_final_cells.tsv'):
        if cell_snapshot(folder/name) != original:
            raise ValueError('Register relocation probe changed primitive netlist')
    lines = (folder/'changed_path_checks.tsv').read_text().splitlines()
    if lines[0] != 'endpoint\tbefore_hold_ns\tafter_hold_ns\tafter_setup_ns':
        raise ValueError('Missing relocation timing comparison')
    seen = set()
    for line in lines[1:]:
        endpoint, before, after, setup = line.split('\t')
        if endpoint in seen or not (float(after)>=hold_target and float(after)>float(before) and float(setup)>=setup_target):
            raise ValueError('Register relocation probe timing gate failed')
        seen.add(endpoint)
    if seen != {row[0] for row in registers.values()}:
        raise ValueError('Incomplete relocation endpoint timing coverage')
    route_summary((folder/'route_status.rpt').read_text())
    return sha(folder/'result.json')


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ('build', 'equivalence', 'reference-audit', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--setup-margin', type=float, default=0.300)
    p.add_argument('--hold-margin', type=float, default=0.100)
    p.add_argument('--strategy', choices=('preplace', 'preplace_hold', 'preplace_relocate', 'preplace_fifo_logic'), default='preplace')
    p.add_argument('--hold-probe', type=Path, help='Passing small routed ECO probe required for preplace_hold')
    p.add_argument('--relocation-helper', type=Path, help='Versioned helper matching the passed relocation probe')
    p.add_argument('--relocation-collector', type=Path, help='Explicit candidate selection policy')
    p.add_argument('--resume-physical', type=Path, help='Retained physical checkpoint; no resynthesis or replacement of failed evidence')
    a = p.parse_args()
    root, out = a.build.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, out/'run_timing_variant_flow.py')
    result = {'pass': False, 'export_attempted': False, 'board_operations': 0, 'steps': []}

    def execute(name, args):
        command = [sys.executable, '-X', 'utf8', '-B', str(ROOT/'scripts'/args[0]),
                   *[str(x) for x in args[1:]]]
        print('TIMING_FLOW_PHASE='+name, flush=True)
        with (out/(name+'.log')).open('xb') as f:
            proc = subprocess.run(command, cwd=out, stdout=f, stderr=subprocess.STDOUT)
        result['steps'].append({'name': name, 'command': command, 'exit_code': proc.returncode,
                                'log_sha256': sha(out/(name+'.log'))})
        if proc.returncode:
            raise RuntimeError(name+' failed; retain stage log')

    try:
        eq = json.loads((a.equivalence/'result.json').read_text())
        if not eq['pass'] or eq['identity_sha256'] != sha(root/'timing_variant.json'):
            raise ValueError('Missing matching RTL equivalence proof')
        for name, digest in eq['evidence'].items():
            if sha(a.equivalence/name) != digest:
                raise ValueError('Equivalence proof changed: '+name)
        print('TIMING_FLOW_PHASE=wait_for_existing_synthesis', flush=True)
        deadline = time.monotonic()+3600
        while not (root/'synth_result.json').is_file():
            if time.monotonic()>deadline:
                raise TimeoutError('Existing synthesis did not produce its result within one hour')
            time.sleep(5)
        synth = json.loads((root/'synth_result.json').read_text())
        if not synth['pass'] or synth['inputs_sha256'] != sha(root/'inputs.json'):
            raise ValueError('Synthesis failed or source identity changed')
        if a.strategy == 'preplace_hold':
            if not a.hold_probe:
                raise ValueError('Missing scoped hold ECO probe')
            result['hold_probe_result_sha256'] = validate_hold_probe(a.hold_probe, a.setup_margin, a.hold_margin)
        if a.strategy in ('preplace_relocate', 'preplace_fifo_logic'):
            if not a.hold_probe:
                raise ValueError('Missing register relocation probe')
            result['hold_probe_result_sha256'] = validate_relocation_probe(a.hold_probe, a.setup_margin, a.hold_margin, a.relocation_helper)
        ref = json.loads(a.reference_audit.read_text())
        if not ref['pass']:
            raise ValueError('Incremental reference audit failed')
        reference = Path(ref['experiment'])/'optimized_routed.dcp'
        if sha(reference) != ref['checkpoint_sha256']:
            raise ValueError('Incremental reference changed')
        result.update(build=root.as_posix(), synthesis_result_sha256=sha(root/'synth_result.json'),
                      equivalence_result_sha256=sha(a.equivalence/'result.json'))
        implementation, reopen = out/'implement01', out/'reopen01'
        implementation_args = ['optimize_timing_margin.py', '--checkpoint', root/'joint_synth.dcp',
                '--out', implementation, '--stage', 'implement', '--strategy', a.strategy,
                '--reference', reference, '--setup-margin', a.setup_margin, '--hold-margin', a.hold_margin]
        if a.relocation_helper:
            if a.strategy != 'preplace_relocate':
                raise ValueError('Explicit relocation helper requires preplace_relocate')
            implementation_args += ['--relocation-helper', a.relocation_helper]
        if a.resume_physical:
            implementation_args += ['--resume-physical', a.resume_physical]
        if a.relocation_collector:
            implementation_args += ['--relocation-collector', a.relocation_collector]
        execute('implement', implementation_args)
        verify_args = ['optimize_timing_margin.py', '--checkpoint', implementation/'optimized_routed.dcp',
                       '--out', reopen, '--stage', 'verify']
        if a.strategy == 'preplace_hold':
            verify_args += ['--hold-evidence', implementation/'hold_eco_records.list']
        if a.strategy == 'preplace_relocate':
            verify_args += ['--relocation-evidence', implementation/'relocation_records.list']
        if a.strategy == 'preplace_fifo_logic':
            verify_args += ['--floorplan-evidence', implementation/'fifo_floorplan_records.list']
        execute('reopen', verify_args)
        execute('audit', ['audit_timing_variant.py', '--build', root, '--experiment', implementation,
                '--equivalence', a.equivalence, '--reopen', reopen, '--reference-audit', a.reference_audit,
                '--out', out/'audit.json'])
        audit = json.loads((out/'audit.json').read_text())
        result.update(pass_=audit['pass'], targets_met=audit['targets_met'],
                      both_margins_improved=audit['both_margins_improved'], timing=audit['timing'])
        result['pass'] = result.pop('pass_')
    except Exception as e:
        result['error'] = str(e)
        raise
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
