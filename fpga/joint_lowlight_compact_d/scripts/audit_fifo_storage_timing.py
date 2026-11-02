"""Bind a FIFO structure implementation to simulation, mapping and timing evidence.

Margins are comparison metrics, not fixed acceptance thresholds. No board/export actions.
"""
import argparse
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

from accept_system import bus_skew_summary, critical_rows, ps_clock_proof, route_summary, timing_summary
from audit_timing_variant import embedded_constraints, intra_clock_summary, resource_summary, waiver_creation_time
from optimize_timing_margin import placement_diagnostics
from verify_timing_margin import worst, xdc_commands


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiled_contract(lines):
    """Allow only re-enumerated provenance and independent additive XPM reset cuts.

    All other timing commands retain their scope, values and global sequence.
    Source metadata stays a checked multiset with exact scopes and source lines.
    """
    sources = {}
    for line in lines:
        if line.startswith('set_property SRC_FILE_INFO '):
            match = re.search(r' id:(\d+) order:', line)
            if not match or match[1] in sources:
                raise ValueError('Malformed or duplicate compiled source ID')
            sources[match[1]] = line.replace(' id:' + match[1] + ' order:', ' id:ENUMERATION order:', 1)
    scope, ordered, reset_cuts, source_lines = '', [], [], []
    reset_cut = 'set_false_path -through [get_ports -scoped_to_current_instance -no_traverse src_arst]'
    for line in lines:
        if line.startswith('set_property SRC_FILE_INFO '):
            continue
        if line.startswith('set_property src_info '):
            match = re.search(r' file:(\d+) line:', line)
            if not match or match[1] not in sources:
                raise ValueError('Compiled source-line provenance cannot be resolved')
            source_lines.append((sources[match[1]], line.replace(' file:' + match[1] + ' line:', ' file:ENUMERATION line:', 1)))
            continue
        if line == 'current_instance -quiet':
            scope = ''
        elif line.startswith('current_instance system_i/'):
            scope = line.removeprefix('current_instance ')
        elif (match := re.fullmatch(r'current_instance \{(system_i/[^{}]+)\}', line)):
            scope = match[1]
        elif line.startswith('current_instance '):
            raise ValueError('Unrecognized compiled instance scope')
        elif line == reset_cut and re.fullmatch(r'system_i/[\w/]+/(?:[ms]_sc_)?xpm_cdc_async_rst_inst', scope):
            reset_cuts.append((scope, line))
        else:
            ordered.append((scope, line))
    return (ordered, Counter(reset_cuts), Counter(sources.values()), Counter(source_lines))


def main():
    ap = argparse.ArgumentParser(__doc__)
    for name in ('build', 'flow', 'mapping', 'width-proof', 'experiment', 'reopen', 'reference-audit', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--node-proof', type=Path, help='Correctly isolated 128-bit revalidation, in addition to historical proof')
    args = ap.parse_args()
    if args.out.exists():
        raise ValueError('Preserve the earlier audit')
    out = args.out.resolve()
    root, flow, mapping, exp, reopen = [p.resolve() for p in
        (args.build, args.flow, args.mapping, args.experiment, args.reopen)]
    result = {'pass': False, 'board_operations': 0,
              'export_allowed': False, 'bound_files': {}}

    def bind(path):
        path = Path(path).resolve()
        result['bound_files'][path.as_posix()] = sha(path)
        return path

    def load(path):
        return json.loads(bind(path).read_text(encoding='utf-8'))

    def expected(path, digest):
        path = bind(path)
        if sha(path) != digest:
            raise ValueError('Evidence identity changed: ' + str(path))
        return path

    def physical_receipt(folder, stage):
        receipt = load(folder / 'result.json')
        if not receipt['pass'] or receipt['stage'] != stage or receipt['exit_code']:
            raise ValueError('Physical stage did not pass: ' + str(folder))
        console = expected(folder / 'console.log', receipt['log_sha256'])
        placement_diagnostics(console.read_text(errors='replace'))
        expected(folder / 'timing_margin.tcl', receipt['script_sha256'])
        expected(folder / 'optimize_timing_margin.py', receipt['runner_sha256'])
        expected(receipt['source_checkpoint'], receipt['source_checkpoint_sha256'])
        for name, digest in receipt['reports'].items():
            expected(folder / name, digest)
        return receipt

    try:
        shutil.copy2(__file__, out.parent / (out.stem + '_script.py'))
        bind(out.parent / (out.stem + '_script.py'))
        for name in ('accept_system.py', 'audit_timing_variant.py', 'optimize_timing_margin.py',
                     'verify_timing_margin.py', 'test_fifo_constraint_contract.py'):
            bind(Path(__file__).parent / name)
        manifest = load(root / 'inputs.json')
        for name, digest in manifest['source_files'].items():
            expected(root / name, digest)
        variant = load(root / 'fifo_storage_variant.json')
        expected(root / 'inputs.json', variant['derived_manifest_sha256'])
        synthesis = load(flow / 'result.json')
        if not synthesis['pass'] or synthesis['stage'] != 'through_synthesis':
            raise ValueError('FIFO synthesis flow did not pass')
        if [r['stage'] for r in synthesis['steps']] != ['prepare', 'memory_equivalence', 'create', 'synth']:
            raise ValueError('Missing synthesis dependency')
        for row in synthesis['steps']:
            if row['exit_code']:
                raise ValueError('Failed synthesis dependency')
            expected(flow / (row['stage'] + '.log'), row['log_sha256'])
        synth = expected(root / 'joint_synth.dcp', synthesis['checkpoint_sha256'])
        result['joint_synthesis_completed_at'] = synthesis['joint_synthesis_completed_at']
        local_path = Path(synthesis['memory_proof']['path'])
        expected(local_path, synthesis['memory_proof']['sha256'])
        local = load(local_path)
        expected(root / 'fifo_storage_variant.json', local['identity_sha256'])
        if not local['pass'] or len([r for r in local['tests'] if r['name'].startswith('sim_')]) != 7:
            raise ValueError('Seven-template memory comparison incomplete')
        for row in local['tests']:
            if bool(row['exit_code']) != bool(row['expected_failure']):
                raise ValueError('Unexpected memory simulation outcome')
            expected(local_path.parent / (row['name'] + '.log'), row['log_sha256'])
        node_path = Path(synthesis['node_proof']['path'])
        expected(node_path, synthesis['node_proof']['sha256'])
        node = load(node_path)
        if not node['pass'] or node['changed_channel_nodes'] != 5:
            raise ValueError('AXI output structure verification incomplete')
        for name, digest in node['source_files'].items():
            expected(node_path.parent / name, digest)
        for row in node['steps']:
            if row['exit_code']:
                raise ValueError('AXI verification tool failed')
            expected(node_path.parent / (row['name'] + '.log'), row['log_sha256'])
        if args.node_proof:
            revalidated_path = args.node_proof.resolve()
            revalidated = load(revalidated_path)
            if not revalidated['pass'] or revalidated['changed_channel_nodes'] != 5 or \
               revalidated.get('fifo_mode') != 'output-register-off' or \
               not revalidated['scope'].startswith('Generated 128-bit SI / 128-bit MI '):
                raise ValueError('Correctly isolated 128-bit AXI revalidation incomplete')
            for name,digest in revalidated['source_files'].items():
                expected(revalidated_path.parent/name,digest)
            for name,digest in revalidated['verification_sources'].items():
                expected(revalidated_path.parent/name,digest)
            for row in revalidated['steps']:
                content=expected(revalidated_path.parent/(row['name']+'.log'),row['log_sha256']).read_text(errors='replace')
                if row['exit_code'] or 'overwriting previous definition of module' in content:
                    raise ValueError('AXI reference/variant were not independent')
            result['independent_axi_revalidation'] = revalidated_path.as_posix()
            node = revalidated
        width_path = args.width_proof.resolve()
        width = load(width_path)
        if not width['pass'] or width['changed_channel_nodes'] != 5 or \
           not width['scope'].startswith('Generated 32-bit SI / 128-bit MI '):
            raise ValueError('Width-conversion AXI comparison incomplete')
        for name, digest in width['source_files'].items():
            expected(width_path.parent / name, digest)
        for row in width['steps']:
            if row['exit_code']:
                raise ValueError('Width-conversion AXI verification tool failed')
            expected(width_path.parent / (row['name'] + '.log'), row['log_sha256'])
        if args.node_proof:
            for name,digest in width['verification_sources'].items():
                expected(width_path.parent/name,digest)
            if any('overwriting previous definition of module' in (width_path.parent/(r['name']+'.log')).read_text(errors='replace')
                   for r in width['steps']):
                raise ValueError('Width-conversion reference/variant were not independent')
        generated_path = flow / 'generated_source_identity.json'
        expected(generated_path, synthesis['generated_source_manifest_sha256'])
        generated = load(generated_path)
        if len(generated) != synthesis['generated_fifo_sources'] or len(generated) != 132:
            raise ValueError('Generated FIFO override coverage changed')
        for name, row in generated.items():
            expected(root / name, row['after'])
            expected(root / 'fifo_generated_before' / name, row['before'])
        # This is the explicit partial-mapping classification. The initial
        # all-registers-removal inspection remains failed and is bound below.
        mapped = load(mapping)
        if not mapped['pass'] or mapped['source_checkpoint_sha256'] != sha(synth):
            raise ValueError('Partial mapping classification did not verify this synthesis')
        for name, digest in mapped['bound_files'].items():
            expected(name, digest)
        result['mapping'] = {k: v for k, v in mapped.items() if k != 'bound_files'}
        run = physical_receipt(exp, 'implement')
        if run['source_checkpoint_sha256'] != sha(synth) or run['strategy'] not in ('preplace', 'preplace_fresh'):
            raise ValueError('Unexpected physical implementation source or method')
        targets = (run['setup_margin_ns'], run['hold_margin_ns'])
        if any(value <= 0 for value in targets):
            raise ValueError('Invalid temporary optimization objective')
        reference = load(args.reference_audit)
        if not reference['pass']:
            raise ValueError('Reference has no passing independent audit')
        ref_folder = Path(reference['experiment'])
        ref_dcp = expected(ref_folder / 'optimized_routed.dcp', reference['checkpoint_sha256'])
        if run['reference_checkpoint_sha256'] != sha(ref_dcp):
            raise ValueError('Implementation used a different physical reference')
        result['experiment'] = exp.as_posix()
        result['reference_timing'] = reference['timing']
        old_constraints = embedded_constraints(bind(Path(variant['baseline']) / 'joint_synth.dcp'))
        new_constraints = embedded_constraints(synth)
        if set(old_constraints) != set(new_constraints) or any(
                compiled_contract(old_constraints[k]) != compiled_contract(new_constraints[k]) for k in old_constraints):
            raise ValueError('Compiled synthesis constraints changed; inspect scopes before accepting')
        result['synthesis_constraint_contract_unchanged'] = True
        result['compiled_constraint_comparison_policy'] = ('Preserve all timing commands, scopes and order; '
            'permit only source metadata enumeration and independently additive XPM src_arst false-path block order')
        restored = xdc_commands(bind(exp / 'restored_constraints.xdc'), True, targets)
        original_path = Path(reference['original_routed_constraints_file'])
        original = xdc_commands(bind(original_path))
        # Independent additive XPM reset cuts can be emitted in another order
        # by the fresh netlist. Use the same narrowly scoped comparison as the
        # compiled XDC; every other command/value/scope/order stays exact.
        if compiled_contract(list(map(waiver_creation_time, original))) != \
           compiled_contract(list(map(waiver_creation_time, restored))):
            diff = '\n'.join(difflib.unified_diff(original, restored, fromfile='original', tofile='new'))
            (out.parent / (out.stem + '_constraint_diff.txt')).write_text(diff, encoding='utf-8')
            raise ValueError('Routed constraints changed; inspect the retained diff')
        result['constraint_commands_unchanged'] = len(restored)
        result['routed_constraint_comparison_policy'] = ('Exact ordered non-reset commands and scopes; '
            'exact scoped multiset of additive XPM src_arst cuts; waiver timestamps only normalized')
        result['original_routed_constraints_file'] = original_path.as_posix()
        clocks = bind(exp / 'restored_clocks.rpt').read_text()
        rows = re.findall(r'^(clk_pl_[01])\s+(clk_pl_[01])\s+([\d.]+)\s+([\d.]+)\s+rf -> rf$', clocks, re.M)
        if sorted(rows) != [('clk_pl_0', 'clk_pl_0', '0.000', '0.000'),
                            ('clk_pl_1', 'clk_pl_1', '0.000', '0.000')]:
            raise ValueError('Effective user uncertainty not restored to zero')
        candidate = bind(exp / 'optimized_routed.dcp')
        result['checkpoint_sha256'] = sha(candidate)
        proof = physical_receipt(reopen, 'verify')
        if proof['source_checkpoint_sha256'] != sha(candidate):
            raise ValueError('Independent reopen used a different candidate')
        unused = ps_clock_proof(bind(reopen / 'reopened_unused_ps_clocks.txt').read_text(),
                                bind(reopen / 'reopened_clock_check.rpt').read_text())
        timing_text = bind(reopen / 'reopened_timing.rpt').read_text()
        timing = timing_summary(timing_text, unused)
        actual = {k: worst(bind(exp / 'final_path_summary.txt'), t)
                  for k, t in [('WNS_ns', 'max'), ('WHS_ns', 'min')]}
        if any(actual[k] != timing[k] for k in actual):
            raise ValueError('Saved checkpoint timing differs from implementation reports')
        result['timing'] = timing
        result['intra_clock_timing'] = intra_clock_summary(timing_text)
        result['optimization_guidance_ns'] = {'WNS_ns': targets[0], 'WHS_ns': targets[1]}
        result['guidance_met'] = all(actual[k] >= v for k, v in result['optimization_guidance_ns'].items())
        result['fixed_margin_acceptance_threshold'] = None
        result['improvement_ns'] = {k: round(actual[k] - reference['timing'][k], 6) for k in actual}
        changes = result['improvement_ns'].values()
        result['margin_comparison'] = ('dominates_reference' if all(v >= 0 for v in changes) and any(v > 0 for v in changes)
            else 'dominated_by_reference' if all(v <= 0 for v in changes) and any(v < 0 for v in changes)
            else 'unchanged' if all(v == 0 for v in changes) else 'setup_hold_tradeoff')
        result['route'] = route_summary(bind(reopen / 'reopened_route.rpt').read_text())
        if route_summary(bind(exp / 'route_status.rpt').read_text()) != result['route']:
            raise ValueError('Saved checkpoint route coverage changed')
        result['bus_skew'] = bus_skew_summary(bind(reopen / 'reopened_bus_skew.rpt').read_text())
        bus_skew_summary(bind(exp / 'routed_bus_skew.rpt').read_text())
        for folder, name, severities in [(exp, 'routed_drc.rpt', {'error', 'critical warning'}),
                (exp, 'routed_cdc.rpt', {'error', 'critical'}),
                (reopen, 'reopened_drc.rpt', {'error', 'critical warning'})]:
            if critical_rows(bind(folder / name).read_text(), severities):
                raise ValueError('Blocking violation: ' + name)
        result['resources'] = resource_summary(bind(exp / 'routed_utilization.rpt').read_text())
        result['reference_resources'] = resource_summary(bind(ref_folder / 'routed_utilization.rpt').read_text())
        for key, value in result['resources'].items():
            if value['available'] != result['reference_resources'][key]['available']:
                raise ValueError('Device resource capacity changed')
        result['resource_delta'] = {k: v['used'] - result['reference_resources'][k]['used']
                                   for k, v in result['resources'].items()}
        if bind(exp / 'cnn_address_mapping.txt').read_text().strip() != 'CNN_ADDRESS_DSP_CELLS=0':
            raise ValueError('Address arithmetic mapping regressed')
        result['verification_scope'] = {'local_memory': local['scope'], 'axi_output': node['scope'],
            'width_conversion': width['scope'],
            'physical': 'Independent reopen, original clocks/constraints, global timing, route, DRC, CDC and bus skew',
            'not_tested': ['Complete six-core RTL simulation', 'All multiport/clock-conversion AXI combinations',
                           'Board numerical accuracy', 'Board FPS']}
        result['pass'] = True
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'bound_files'},
                         indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
