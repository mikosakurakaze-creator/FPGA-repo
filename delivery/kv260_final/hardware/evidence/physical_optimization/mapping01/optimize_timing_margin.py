"""Run isolated timing-margin diagnostics/experiments without changing the baseline."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from run_checks import vendor_runtime

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def placement_diagnostics(content):
    """Keep raw rejected-BEL errors; permit only explicit, bounded 12-1409 trials."""
    outside = []
    active = None
    trials = []
    for line in content.splitlines():
        if line.startswith('PLACEMENT_TRIAL_BEGIN\t'):
            if active is not None or len(line.split('\t')) != 3:
                raise ValueError('Malformed or nested placement trial')
            _, cell, target = line.split('\t')
            active = {'cell':cell, 'target':target, 'lines':[]}
        elif line.startswith('PLACEMENT_TRIAL_END\t'):
            if active is None:
                raise ValueError('Unmatched placement trial end')
            status = line.removeprefix('PLACEMENT_TRIAL_END\t')
            errors = re.findall(r'^\s*(?:ERROR|FATAL): \[([^]]+)\]', '\n'.join(active['lines']), re.M)
            if status == '0':
                if errors:
                    raise ValueError('Accepted placement emitted an error')
            elif status == '1':
                if not errors or set(errors) != {'Vivado 12-1409'}:
                    raise ValueError('Unreviewed speculative placement rejection')
            else:
                raise ValueError('Unexpected placement return code')
            trials.append({**active, 'status':int(status), 'error_ids':errors})
            active = None
        elif active is not None:
            active['lines'].append(line)
        else:
            outside.append(line)
    if active is not None or re.search(r'(?mi)^\s*(ERROR|FATAL):', '\n'.join(outside)):
        raise ValueError('Unbounded placement trial or error outside a speculative trial')
    return trials


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--stage', choices=('help', 'inspect', 'optimize', 'verify', 'implement'), default='inspect')
    parser.add_argument('--setup-margin', type=float, default=0.200)
    parser.add_argument('--hold-margin', type=float, default=0.050)
    parser.add_argument('--strategy', choices=('reroute', 'preplace', 'preplace_fresh', 'preplace_hold', 'preplace_relocate', 'preplace_fifo_logic'), default='reroute')
    parser.add_argument('--reference', type=Path, help='Routed incremental reference for a newly synthesized RTL variant')
    parser.add_argument('--tcl-script', type=Path, default=ROOT / 'scripts/timing_margin.tcl',
                        help='Explicit isolated experiment script; copied and hashed with the run')
    parser.add_argument('--hold-evidence', type=Path, help='Original ECO record list for independent read-only verification')
    parser.add_argument('--relocation-evidence', type=Path, help='Original physical relocation records for independent verification')
    parser.add_argument('--relocation-helper', type=Path, help='Explicit versioned physical relocation helper for a new probe/implementation')
    parser.add_argument('--relocation-collector', type=Path, help='Explicit candidate selection policy, frozen with this experiment')
    parser.add_argument('--resume-physical', type=Path, help='Resume a retained tightened_physopt.dcp from a recorded failed implementation')
    parser.add_argument('--floorplan-evidence', type=Path, help='Original FIFO floorplan records for independent verification')
    parser.add_argument('--fifo-floor', type=Path, default=Path('D:/weather_builds/timing_margin_20261102/hold_floor01/hold_floor.tsv'))
    parser.add_argument('--vivado', type=Path, default=Path('D:/vivado/2025.2/Vivado'))
    parser.add_argument('--desktop-helper', type=Path,
                        default=Path('D:/weather_builds/joint_prepare_pipeline01_20261101/run_windows_desktop.py'))
    args = parser.parse_args()
    if args.stage == 'implement' and (not args.reference or args.strategy not in ('preplace', 'preplace_fresh', 'preplace_hold', 'preplace_relocate', 'preplace_fifo_logic')):
        parser.error('New implementation requires --reference and a preplace strategy')
    source = args.checkpoint.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'pass': False, 'stage': args.stage, 'source_checkpoint': source.as_posix(),
              'source_checkpoint_sha256': sha(source), 'board_operations': 0,
              'setup_margin_ns': args.setup_margin, 'hold_margin_ns': args.hold_margin,
              'strategy': args.strategy}
    try:
        if args.resume_physical:
            if args.stage != 'implement' or args.strategy != 'preplace_relocate' or args.resume_physical.name not in ('tightened_physopt.dcp','initial_routed_candidate.dcp'):
                raise ValueError('Physical resume requires an implementation relocation and the retained physopt checkpoint')
            producer = args.resume_physical.parent
            prior = json.loads((producer/'result.json').read_text())
            if prior['stage'] != 'implement' or prior['source_checkpoint_sha256'] != sha(source):
                raise ValueError('Resume producer used a different synthesis checkpoint')
            if sha(producer/'console.log') != prior['log_sha256'] or sha(producer/'timing_margin.tcl') != prior['script_sha256']:
                raise ValueError('Resume producer evidence changed')
            if prior['setup_margin_ns'] != args.setup_margin or prior['hold_margin_ns'] != args.hold_margin:
                raise ValueError('Resume must preserve the saved tightened targets')
            shutil.copy2(args.resume_physical, out/'resume_physical.dcp')
            if args.resume_physical.name == 'initial_routed_candidate.dcp':
                (out/'resume_initial_route.marker').write_text('Retained initial routed checkpoint; final routing/signoff still required\n')
            result['physical_resume'] = {'path':args.resume_physical.resolve().as_posix(),
                'sha256':sha(args.resume_physical), 'producer_result_sha256':sha(producer/'result.json'),
                'producer_pass':prior['pass'], 'producer_log_sha256':prior['log_sha256'],
                'binding':'Checkpoint newly hashed on resume; failed producer is retained, not reclassified as successful'}
        if args.reference:
            result['reference_checkpoint'] = args.reference.resolve().as_posix()
            result['reference_checkpoint_sha256'] = sha(args.reference)
            result['reference_role'] = 'comparison_only_fresh_placement' if args.strategy in ('preplace_fifo_logic', 'preplace_fresh') else 'incremental_implementation'
        shutil.copy2(__file__, out / 'optimize_timing_margin.py')
        result['runner_sha256'] = sha(out/'optimize_timing_margin.py')
        shutil.copy2(args.tcl_script, out / 'timing_margin.tcl')
        if args.strategy == 'preplace_hold' or args.hold_evidence:
            helper = args.hold_evidence.parent/'fifo_hold_eco.tcl' if args.hold_evidence else ROOT/'scripts/fifo_hold_eco.tcl'
            shutil.copy2(helper, out/'fifo_hold_eco.tcl')
            result['support_files'] = {'fifo_hold_eco.tcl': sha(out/'fifo_hold_eco.tcl')}
        if args.strategy == 'preplace_relocate' or args.relocation_evidence:
            if args.relocation_evidence and args.relocation_helper:
                raise ValueError('Reopen must use the helper frozen with the original relocation evidence')
            helper = args.relocation_evidence.parent/'fifo_hold_relocate.tcl' if args.relocation_evidence else (args.relocation_helper or ROOT/'scripts/fifo_hold_relocate.tcl')
            shutil.copy2(helper, out/'fifo_hold_relocate.tcl')
            result.setdefault('support_files', {})['fifo_hold_relocate.tcl'] = sha(out/'fifo_hold_relocate.tcl')
            result['relocation_helper_source'] = helper.resolve().as_posix()
        if args.strategy == 'preplace_relocate':
            shutil.copy2(args.relocation_collector or ROOT/'scripts/fifo_hold_relocation_collect.tcl', out/'fifo_hold_relocation_collect.tcl')
            result['support_files']['fifo_hold_relocation_collect.tcl'] = sha(out/'fifo_hold_relocation_collect.tcl')
        if args.relocation_evidence:
            if args.stage != 'verify':
                raise ValueError('Relocation evidence is only accepted in read-only verification')
            shutil.copy2(args.relocation_evidence, out/'relocation_records.list')
            result['relocation_manifest_sha256'] = sha(out/'relocation_records.list')
        if args.strategy == 'preplace_fifo_logic' or args.floorplan_evidence:
            helper = args.floorplan_evidence.parent/'fifo_hold_floorplan.tcl' if args.floorplan_evidence else ROOT/'scripts/fifo_hold_floorplan.tcl'
            shutil.copy2(helper, out/'fifo_hold_floorplan.tcl')
            result.setdefault('support_files', {})['fifo_hold_floorplan.tcl'] = sha(out/'fifo_hold_floorplan.tcl')
        if args.strategy == 'preplace_fifo_logic':
            rows = list(csv.DictReader(args.fifo_floor.open(encoding='utf-8'), delimiter='\t'))
            if not rows or float(rows[-1]['slack'])<args.hold_margin or any(float(x['slack'])>float(y['slack']) for x,y in zip(rows, rows[1:])):
                raise ValueError('Reference hold-path coverage does not include the requested margin')
            targets = sorted({row['end'].removesuffix('/D') for row in rows if float(row['slack'])<args.hold_margin
                and row['source_ref'] in ('RAMD32','RAMD64E') and row['dest_ref']=='FDRE'
                and row['source_loc']==row['dest_loc'] and row['end'].endswith('/D')})
            if not targets or any('{' in name or '}' in name for name in targets):
                raise ValueError('Invalid FIFO floorplan target names')
            (out/'fifo_floorplan_targets.list').write_text('\n'.join('{'+name+'}' for name in targets)+'\n', encoding='utf-8')
            result['fifo_floor_evidence'] = {'path':args.fifo_floor.resolve().as_posix(), 'sha256':sha(args.fifo_floor), 'targets':len(targets)}
        if args.floorplan_evidence:
            if args.stage != 'verify':
                raise ValueError('FIFO floorplan evidence is only accepted in read-only verification')
            shutil.copy2(args.floorplan_evidence, out/'fifo_floorplan_records.list')
            result['floorplan_manifest_sha256'] = sha(out/'fifo_floorplan_records.list')
        if args.hold_evidence:
            if args.stage != 'verify':
                raise ValueError('External hold evidence is only accepted in read-only verify stage')
            shutil.copy2(args.hold_evidence, out/'hold_eco_records.list')
            result['hold_manifest_sha256'] = sha(out/'hold_eco_records.list')
        shutil.copy2(args.desktop_helper, out / 'run_windows_desktop.py')
        result['script_sha256'] = sha(out / 'timing_margin.tcl')
        exe, env = vendor_runtime(out, args.vivado)
        env.pop('SHELL', None)
        command = [sys.executable, '-E', str(out / 'run_windows_desktop.py'), '--', str(exe),
                   '-mode', 'batch', '-log', str(out / 'vivado.log'), '-journal', str(out / 'vivado.jou'),
                   '-source', str(out / 'timing_margin.tcl'), '-tclargs', str(source), str(out), args.stage,
                   str(args.setup_margin), str(args.hold_margin), args.strategy,
                   args.reference.resolve().as_posix() if args.reference else '']
        result['command'] = command
        print('TIMING_STAGE=' + args.stage + ' LOG=' + str(out / 'console.log'), flush=True)
        start = time.perf_counter()
        with (out / 'console.log').open('xb') as log:
            proc = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
        result.update(exit_code=proc.returncode, seconds=time.perf_counter()-start,
                      log_sha256=sha(out / 'console.log'))
        content = (out / 'console.log').read_text(errors='replace')
        if proc.returncode:
            raise RuntimeError('Timing experiment failed; preserve the raw console log')
        trials = placement_diagnostics(content)
        result['speculative_placement_trials'] = {'accepted':sum(t['status']==0 for t in trials),
            'rejected':sum(t['status']==1 for t in trials), 'raw_diagnostics_retained':True}
        if 'TIMING_MARGIN_' + args.stage.upper() + '_PASS' not in content.splitlines():
            raise RuntimeError('Missing timing experiment completion marker')
        if sha(source) != result['source_checkpoint_sha256']:
            raise ValueError('Baseline checkpoint changed')
        if args.reference and sha(args.reference) != result['reference_checkpoint_sha256']:
            raise ValueError('Incremental reference checkpoint changed')
        result['reports'] = {p.name: sha(p) for p in out.glob('*') if p.suffix in ('.rpt', '.txt', '.xdc', '.tsv', '.list')}
        result['pass'] = True
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
