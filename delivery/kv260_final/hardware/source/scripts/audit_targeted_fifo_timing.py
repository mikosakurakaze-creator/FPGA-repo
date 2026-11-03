"""Audit six-node FIFO replacement against the current routed parent; no export."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

from accept_system import bus_skew_summary, critical_rows, ps_clock_proof, route_summary, timing_summary
from audit_fifo_storage_timing import compiled_contract
from audit_timing_variant import embedded_constraints, intra_clock_summary, resource_summary, waiver_creation_time
from optimize_timing_margin import placement_diagnostics
from verify_timing_margin import worst, xdc_commands
from targeted_fifo_constraint_contract import compare_targeted_compiled


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(__doc__)
    for name in ('parent-audit', 'experiment', 'reopen', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--saturation-proof', type=Path, action='append', required=True)
    ap.add_argument('--source-flow', type=Path, help='Rebuild-in-context receipt when routed port optimization prevents direct import')
    ap.add_argument('--build', type=Path, help='Rebuilt six-node source directory; required with --source-flow')
    ap.add_argument('--mapping', type=Path, help='Independent synthesized six-node mapping receipt; required with --source-flow')
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise ValueError('Preserve earlier audit results')
    exp, reopen = args.experiment.resolve(), args.reopen.resolve()
    result = {'pass': False, 'board_operations': 0, 'export_allowed': False, 'bound_files': {}}

    def bind(path, expected=None):
        path = Path(path).resolve()
        digest = sha(path)
        result['bound_files'][path.as_posix()] = digest
        if expected is not None and digest != expected:
            raise ValueError('Evidence identity changed: ' + str(path))
        return path

    def load(path):
        return json.loads(bind(path).read_text(encoding='utf-8'))

    def receipt(folder, stage):
        row = load(folder / 'result.json')
        if not row['pass'] or row['stage'] != stage or row['exit_code']:
            raise ValueError('Physical stage did not pass: ' + str(folder))
        log = bind(folder / 'console.log', row['log_sha256']).read_text(errors='replace')
        placement_diagnostics(log)
        bind(folder / 'timing_margin.tcl', row['script_sha256'])
        bind(folder / 'optimize_timing_margin.py', row['runner_sha256'])
        bind(row['source_checkpoint'], row['source_checkpoint_sha256'])
        for name, digest in row['reports'].items():
            bind(folder / name, digest)
        return row, log

    try:
        saved_script = out.parent / (out.stem + '_script.py')
        shutil.copy2(__file__, saved_script)
        bind(saved_script)
        for name in ('accept_system.py', 'audit_fifo_storage_timing.py', 'audit_timing_variant.py',
                     'optimize_timing_margin.py', 'verify_timing_margin.py', 'targeted_fifo_constraint_contract.py',
                     'test_targeted_fifo_constraints.py'):
            bind(Path(__file__).parent / name)
        parent = load(args.parent_audit)
        if not parent['pass'] or not parent.get('independent_axi_revalidation'):
            raise ValueError('Parent requires the corrected independent AXI proof')
        for name, digest in parent['bound_files'].items():
            bind(name, digest)
        parent_dcp = bind(Path(parent['experiment']) / 'optimized_routed.dcp', parent['checkpoint_sha256'])
        result['parent_checkpoint'] = parent_dcp.as_posix()
        result['parent_checkpoint_sha256'] = sha(parent_dcp)

        if args.source_flow:
            if not args.build or not args.mapping:
                raise ValueError('--build and --mapping are required for rebuilt sources')
            build = args.build.resolve()
            flow = load(args.source_flow / 'result.json')
            if not flow['pass'] or flow['stage'] != 'through_synthesis' or [r['stage'] for r in flow['steps']] != ['prepare', 'create', 'synth']:
                raise ValueError('Rebuild-in-context flow incomplete')
            for name, digest in flow['bound_files'].items():
                bind(name, digest)
            for step in flow['steps']:
                bind(args.source_flow / (step['stage'] + '.log'), step['log_sha256'])
                if step['exit_code']:
                    raise ValueError('Rebuild dependency failed')
            manifest = load(build / 'inputs.json')
            for name, digest in manifest['source_files'].items():
                bind(build / name, digest)
            plan = load(build / 'targeted_fifo_plan.json')
            if plan['parent_checkpoint_sha256'] != sha(parent_dcp) or plan['parent_audit_sha256'] != sha(args.parent_audit):
                raise ValueError('Rebuilt source uses another current parent')
            old_manifest = load(Path(plan['parent_build']) / 'inputs.json')
            expected_extras = {'targeted_fifo_plan.json', 'targeted_fifo_mapping.py'}
            if set(manifest['source_files']) != set(old_manifest['source_files']) | expected_extras:
                raise ValueError('Unexpected rebuilt input files')
            for name, digest in old_manifest['source_files'].items():
                if name != 'fifo_output_policy.tcl' and manifest['source_files'][name] != digest:
                    raise ValueError('Inherited algorithm/integration source changed: ' + name)
            sources = load(build / 'targeted_generated_sources.json')
            changed = [row for row in sources if row['method'] != 'inherit']
            counts = {key: sum(row['key'] == key for row in changed) for key in plan['targets']}
            if len(sources) != 132 or len(changed) != 12 or set(counts.values()) != {2}:
                raise ValueError('Generated source change scope exceeds six sim/synth pairs')
            for row in sources:
                bind(build / row['path'], row['after'])
                bind(build / row['backup'], row['before'])
                bind(Path(plan['parent_build']) / row['path'], row['parent_current_sha256'])
            run, log = receipt(exp, 'implement')
            synthesis = bind(build / 'joint_synth.dcp', flow['checkpoint_sha256'])
            mapping, mapping_log = receipt(args.mapping.resolve(), 'inspect')
            if mapping['source_checkpoint_sha256'] != sha(synthesis) or 'TIMING_MARGIN_INSPECT_PASS' not in mapping_log:
                raise ValueError('Mapping proof must inspect this exact synthesis checkpoint')
            bind(args.mapping / 'timing_margin.tcl', sha(Path(__file__).parent / 'audit_targeted_fifo_mapping.tcl'))
            mapping_rows = bind(args.mapping / 'targeted_node_mapping.tsv').read_text().splitlines()
            expected_rows = ['key\tbram36\tbram18\tidentity_luts']
            for key, method in plan['targets'].items():
                counts = '2\t2\t0' if method == 'bram' else ('0\t0\t344' if key == 'bilinear_ddr_sc/s00_ar_node' else '0\t0\t24')
                expected_rows.append(key + '\t' + counts)
            if mapping_rows != expected_rows:
                raise ValueError('Six-node primitive mapping differs from the frozen plan')
            if bind(args.mapping / 'inherited_mapping.txt').read_text().strip() != 'PRESERVED_LOCAL_DECODERS=3616':
                raise ValueError('Inherited local-memory decoders changed')
            spec_sources = re.findall(r'^source (.+/node_specs\.tcl)$', (args.mapping / 'timing_margin.tcl').read_text(), re.M)
            if len(spec_sources) != 1:
                raise ValueError('Ambiguous mapping target specification')
            spec_path = Path(spec_sources[0])
            prepared = load(bind(spec_path.parent / 'result.json', plan['prepared_nodes_sha256']))
            bind(spec_path, prepared['bound_files'][spec_path.resolve().as_posix()])
            result['synthesized_mapping'] = {'bram36': 8, 'bram18': 8, 'identity_luts': 368, 'inherited_decoders': 3616}
            if run['source_checkpoint_sha256'] != sha(synthesis) or run.get('reference_checkpoint_sha256') != sha(parent_dcp) or run['strategy'] != 'preplace':
                raise ValueError('Implementation must use current parent for incremental reuse')
            old_constraints = embedded_constraints(bind(Path(plan['parent_build']) / 'joint_synth.dcp'))
            new_constraints = embedded_constraints(synthesis)
            if set(old_constraints) != set(new_constraints):
                raise ValueError('Compiled constraint file set changed')
            bram_keys = [key for key, method in plan['targets'].items() if method == 'bram']
            result['compiled_constraints'] = {k: compare_targeted_compiled(old_constraints[k], new_constraints[k], bram_keys) for k in old_constraints}
            for script in ('xpm_memory/tcl/xpm_memory_xdc.tcl', 'xpm_fifo/tcl/xpm_fifo_rst.tcl'):
                bind(Path('D:/vivado/2025.2/Vivado/data/ip/xpm') / script)
            result['replaced_nodes'] = list(plan['targets'])
            result['source_change_scope'] = 'Six generated FIFO sim/synth pairs only; inherited algorithm and integration inputs unchanged'
            result['physical_reference_role'] = 'Current routed parent reused incrementally; outside placement identity after implementation is not claimed'
            result['joint_synthesis_completed_at'] = flow['joint_synthesis_completed_at']
        else:
            run, log = receipt(exp, 'optimize')
            if run['source_checkpoint_sha256'] != sha(parent_dcp):
                raise ValueError('Replacement did not start from the current routed parent')
            inputs = load(exp / 'physical_inputs.json')
            if not inputs['pass'] or inputs['node_count'] != 6 or inputs['parent_checkpoint_sha256'] != sha(parent_dcp):
                raise ValueError('Wrong frozen six-node input identity')
            for name, digest in inputs['files'].items():
                bind(name, digest)
            prepared_paths = [Path(p) for p in inputs['files'] if p.endswith('/fifo_targeted03_nodes/result.json')]
            if len(prepared_paths) != 1:
                raise ValueError('Ambiguous prepared-node manifest')
            prepared = load(prepared_paths[0])
            keys = [row['key'] for row in prepared['nodes']]
            replaced = re.findall(r'^TARGETED_NODE_REPLACE_PASS=(.+)$', log, re.M)
            if replaced != keys or len(set(keys)) != 6:
                raise ValueError('The exact six replacements were not independently gated')
            for key in keys:
                source_dcps = [Path(p) for p in inputs['files'] if p.endswith('/' + key.replace('/', '__') + '.dcp')]
                if len(source_dcps) != 1:
                    raise ValueError('Ambiguous replacement DCP: ' + key)
                bind(exp / source_dcps[0].name, sha(source_dcps[0]))
            boundary = bind(exp / 'replacement_boundary.txt').read_text()
            entries = re.findall(r'^NODE=(.+)\nBEFORE=(.*)\nAFTER=(.*)$', boundary, re.M)
            if [row[0] for row in entries] != keys or any(a != b for _, a, b in entries):
                raise ValueError('Boundary pins, directions or connections changed')
            outside = bind(exp / 'outside_replacement_proof.txt').read_text().strip()
            if not re.fullmatch(r'UNCHANGED_OUTSIDE_PRIMITIVES=[1-9]\d*', outside):
                raise ValueError('Untargeted primitive and placement check is missing')
            result['replaced_nodes'] = keys
            result['outside_primitives_unchanged_during_import'] = int(outside.split('=')[1])

        scopes = []
        for path in args.saturation_proof:
            proof = load(path)
            if (not proof['pass'] or proof.get('fifo_mode') != 'targeted' or
                    not proof.get('saturation_checked') or proof['changed_channel_nodes'] != 3):
                raise ValueError('Missing targeted saturation verification')
            for group in ('source_files', 'verification_sources'):
                for name, digest in proof[group].items():
                    bind(path.parent / name, digest)
            for step in proof['steps']:
                text = bind(path.parent / (step['name'] + '.log'), step['log_sha256']).read_text(errors='replace')
                if step['exit_code'] or re.search(r'(?mi)^\s*(?:ERROR|FATAL):', text) or 'overwriting previous definition of module' in text:
                    raise ValueError('Failed or non-independent AXI simulation')
            sim = bind(path.parent / 'simulate.log').read_text(errors='replace')
            if re.findall(r'^SATURATED_AXI_READ_PASS case=(reference|variant) consecutive_beats=240$', sim, re.M) != ['reference', 'variant']:
                raise ValueError('Continuous 240-beat read proof is incomplete')
            scopes.append(proof['scope'])
        if len(scopes) != 2 or sum('32-bit SI / 128-bit MI' in s for s in scopes) != 1 or sum('128-bit SI / 128-bit MI' in s for s in scopes) != 1:
            raise ValueError('Both tested AXI widths are required')
        result['saturation_verification'] = scopes

        targets = (run['setup_margin_ns'], run['hold_margin_ns'])
        original_path = bind(parent['original_routed_constraints_file'])
        original = xdc_commands(original_path)
        restored = xdc_commands(bind(exp / 'restored_constraints.xdc'), True, targets)
        contract = lambda rows: compiled_contract(list(map(waiver_creation_time, rows)))
        baseline_ok = True
        if not args.source_flow:
            baseline_ok = contract(original) == contract(xdc_commands(bind(exp / 'baseline_constraints.xdc')))
        if not baseline_ok or contract(original) != contract(restored):
            diff = '\n'.join(difflib.unified_diff(original, restored, fromfile='original', tofile='replacement'))
            (out.parent / (out.stem + '_constraint_diff.txt')).write_text(diff, encoding='utf-8')
            raise ValueError('Original constraint contract changed; inspect retained diff')
        result['constraint_commands_unchanged'] = len(restored)
        result['original_routed_constraints_file'] = original_path.as_posix()
        clocks = bind(exp / 'restored_clocks.rpt').read_text()
        periods = re.findall(r'^(clk_pl_[01])\s+([\d.]+)\s+\{[^}]+\}\s+P', clocks, re.M)
        if sorted(periods) != [('clk_pl_0', '10.000'), ('clk_pl_1', '5.000')]:
            raise ValueError('Original 100/200 MHz clocks changed')
        rows = re.findall(r'^(clk_pl_[01])\s+(clk_pl_[01])\s+([\d.]+)\s+([\d.]+)\s+rf -> rf$', clocks, re.M)
        if sorted(rows) != [('clk_pl_0', 'clk_pl_0', '0.000', '0.000'), ('clk_pl_1', 'clk_pl_1', '0.000', '0.000')]:
            raise ValueError('User uncertainty not restored')

        candidate = bind(exp / 'optimized_routed.dcp')
        check, _ = receipt(reopen, 'verify')
        if check['source_checkpoint_sha256'] != sha(candidate):
            raise ValueError('Independent reopen used another checkpoint')
        unused = ps_clock_proof(bind(reopen / 'reopened_unused_ps_clocks.txt').read_text(),
                                bind(reopen / 'reopened_clock_check.rpt').read_text())
        timing_text = bind(reopen / 'reopened_timing.rpt').read_text()
        timing = timing_summary(timing_text, unused)
        actual = {k: worst(bind(exp / 'final_path_summary.txt'), t) for k, t in [('WNS_ns', 'max'), ('WHS_ns', 'min')]}
        if any(actual[k] != timing[k] for k in actual):
            raise ValueError('Reopened timing differs from saved result')
        result['experiment'] = exp.as_posix()
        result['checkpoint_sha256'] = sha(candidate)
        result['timing'] = timing
        result['intra_clock_timing'] = intra_clock_summary(timing_text)
        result['reference_timing'] = parent['timing']
        result['improvement_ns'] = {k: round(actual[k] - parent['timing'][k], 6) for k in actual}
        result['fixed_margin_acceptance_threshold'] = None
        result['route'] = route_summary(bind(reopen / 'reopened_route.rpt').read_text())
        if route_summary(bind(exp / 'route_status.rpt').read_text()) != result['route']:
            raise ValueError('Route coverage changed on reopen')
        result['bus_skew'] = bus_skew_summary(bind(reopen / 'reopened_bus_skew.rpt').read_text())
        bus_skew_summary(bind(exp / 'routed_bus_skew.rpt').read_text())
        for folder, name, severity in [(exp, 'routed_drc.rpt', {'error', 'critical warning'}),
                                      (exp, 'routed_cdc.rpt', {'error', 'critical'}),
                                      (reopen, 'reopened_drc.rpt', {'error', 'critical warning'})]:
            if critical_rows(bind(folder / name).read_text(), severity):
                raise ValueError('Blocking violation: ' + name)
        result['resources'] = resource_summary(bind(exp / 'routed_utilization.rpt').read_text())
        result['resource_delta'] = {k: v['used'] - parent['resources'][k]['used'] for k, v in result['resources'].items()}
        if any(v['available'] != parent['resources'][k]['available'] or v['used'] > v['available'] for k, v in result['resources'].items()):
            raise ValueError('Resource capacity contract changed or exceeded')
        if result['resource_delta']['BRAM_tile'] != 12 or result['resource_delta']['URAM'] != 0 or result['resource_delta']['DSP'] != 0:
            raise ValueError('Unexpected dedicated resource change')
        result['verification_scope'] = {'physical': 'Six targeted FIFO changes, current parent identity, original constraints and independent timing/route/DRC/CDC/bus-skew reports',
            'not_tested': ['Complete six-core RTL', 'All multiport and CDC AXI combinations', 'Board numerical accuracy', 'Board FPS']}
        result['pass'] = True
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'bound_files'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
