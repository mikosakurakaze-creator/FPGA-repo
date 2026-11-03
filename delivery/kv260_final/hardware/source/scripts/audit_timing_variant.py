"""Bind an RTL timing variant to equivalence, synthesis and reopened route evidence."""
import argparse
import csv
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from verify_timing_margin import xdc_commands, worst
from accept_system import timing_summary, route_summary, critical_rows, bus_skew_summary, ps_clock_proof
from optimize_timing_margin import placement_diagnostics


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def resource_summary(text):
    """Read the exact Vivado 2025.2 summary rows, including capacity."""
    result = {}
    for key, label in [('LUT', 'CLB LUTs'), ('FF', 'CLB Registers'),
                       ('BRAM_tile', 'Block RAM Tile'), ('URAM', 'URAM'), ('DSP', 'DSPs')]:
        rows = re.findall(r'^\|\s*'+re.escape(label)+
                          r'\*?\s*\|\s*([\d.]+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|', text, re.M)
        if not rows or len(set(rows)) != 1:
            raise ValueError('Missing or inconsistent resource row: '+label)
        used, available = map(float, rows[0])
        if not 0 <= used <= available or available <= 0:
            raise ValueError('Invalid resource capacity: '+label)
        result[key] = {'used': used, 'available': available,
                       'percent': round(100*used/available, 3)}
    return result


def intra_clock_summary(text):
    start = text.index('| Intra Clock Table')
    end = text.index('| Inter Clock Table', start)
    result = {}
    for line in text[start:end].splitlines():
        fields = line.split()
        if fields and fields[0] in ('clk_pl_0', 'clk_pl_1'):
            if len(fields) != 13 or fields[0] in result:
                raise ValueError('Unexpected intra-clock timing row')
            result[fields[0]] = {'WNS_ns': float(fields[1]), 'WHS_ns': float(fields[5]),
                                'WPWS_ns': float(fields[9])}
    if set(result) != {'clk_pl_0', 'clk_pl_1'}:
        raise ValueError('Missing expected intra-clock timing')
    return result


def waiver_creation_time(line):
    # Only a waiver's creation timestamp is metadata; keep its type, ID,
    # selectors, tags and scope verbatim.
    if line.startswith('create_waiver '):
        return re.sub(r' -timestamp "[^"]+"', '', line)
    return line


def embedded_constraints(checkpoint):
    """Compare synthesis with synthesis, before opt_design prunes dead scopes."""
    checkpoint = Path(checkpoint)
    root = checkpoint.parent
    result = {}
    with zipfile.ZipFile(checkpoint) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith('.xdc'))
        if not names:
            raise ValueError('Checkpoint contains no constraints')
        for name in names:
            lines = []
            for raw in archive.read(name).decode('utf-8').splitlines():
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('set_property SRC_FILE_INFO '):
                    match = re.search(r'cfile:(\S+) rfile:(\S+) ', line)
                    rx = re.search(r'rxprname:([^}]+)\} \[current_design\]$', line)
                    if not match or not rx:
                        raise ValueError('Unrecognized source-file provenance record')
                    absolute = Path(match[1]).resolve()
                    if (root/match[2]).resolve() != absolute:
                        raise ValueError('Relative constraint source path resolves differently')
                    expression = rx[1]
                    for variable, folder in [('$PPRDIR', root/'project'),
                                             ('$PGENDIR', root/'project/joint_system.gen')]:
                        if expression.startswith(variable+'/'):
                            expression = str(folder)+expression[len(variable):]
                            break
                    if Path(expression).resolve() != absolute:
                        raise ValueError('Symbolic constraint source path resolves differently')
                    try:
                        canonical = '$BUILD/'+absolute.relative_to(root).as_posix().lower()
                    except ValueError:
                        canonical = absolute.as_posix().lower()
                    line = line.replace('cfile:'+match[1], 'cfile:'+canonical, 1)
                    line = line.replace('rfile:'+match[2], 'rfile:'+canonical, 1)
                    line = line.replace('rxprname:'+rx[1], 'rxprname:'+canonical, 1)
                lines.append(waiver_creation_time(line))
            result[name] = lines
    return result


def hold_eco_rows(path):
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != 'buffer\tendpoint\tidentity_init\tconnections\tcontrols':
        raise ValueError('Missing hold ECO connection proof header')
    rows = {}
    for line in lines[1:-1]:
        fields = line.split('\t')
        if len(fields) != 5 or fields[3:] != ['PASS','PASS'] or fields[2].lower() not in ("2'h2","2'b10","2","10"):
            raise ValueError('Failed hold ECO identity/connection proof')
        if fields[0] in rows:
            raise ValueError('Duplicate hold ECO buffer')
        rows[fields[0]] = fields[1]
    if not rows or lines[-1] != 'VERIFIED_IDENTITY_BUFFERS='+str(len(rows)):
        raise ValueError('Incomplete hold ECO connection proof')
    return rows


def cell_snapshot(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        name, ref = line.split('\t')
        if name in result:
            raise ValueError('Duplicate primitive in cell snapshot')
        result[name] = ref
    if not result:
        raise ValueError('Empty primitive snapshot')
    return result


def register_parameter_rows(path, expected_cells):
    """Require all reconstructed FDRE functional parameters and exact coverage."""
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != 'cell\tINIT\tIS_C_INVERTED\tIS_D_INVERTED\tIS_R_INVERTED':
        raise ValueError('Missing reconstructed FDRE parameter header')
    rows = {}
    for line in lines[1:]:
        fields = line.split('\t')
        if len(fields) != 5 or not fields[0] or any(x not in ('0','1') for x in fields[1:]):
            raise ValueError('Invalid reconstructed FDRE parameters')
        if fields[0] in rows:
            raise ValueError('Duplicate reconstructed FDRE parameters')
        rows[fields[0]] = tuple(fields[1:])
    if not rows or set(rows) != set(expected_cells):
        raise ValueError('Incomplete reconstructed FDRE parameter coverage')
    return rows


def relocation_rows(path):
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != 'cell\tendpoint\told_site\tnew_site\tconnections':
        raise ValueError('Missing register relocation proof header')
    rows = {}
    for line in lines[1:-1]:
        fields = line.split('\t')
        if (len(fields) != 5 or fields[4] != 'PASS' or fields[1] != fields[0]+'/D'
                or fields[2] == fields[3] or not all(re.fullmatch(r'SLICE_X\d+Y\d+', s) for s in fields[2:4])):
            raise ValueError('Failed register relocation proof')
        if fields[0] in rows:
            raise ValueError('Duplicate relocated register')
        rows[fields[0]] = tuple(fields[1:4])
    if not rows or lines[-1] != 'VERIFIED_RELOCATED_REGISTERS='+str(len(rows)):
        raise ValueError('Incomplete register relocation proof')
    return rows


def floorplan_rows(path):
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != 'cell\tsite\ttype\tconnections':
        raise ValueError('Missing FIFO floorplan proof header')
    rows = {}
    for line in lines[1:-1]:
        fields = line.split('\t')
        if len(fields)!=4 or fields[2:]!=['FDRE','PASS'] or not re.fullmatch(r'SLICE_X\d+Y\d+', fields[1]):
            raise ValueError('Failed FIFO floorplan connection proof')
        if fields[0] in rows:
            raise ValueError('Duplicate floorplanned register')
        rows[fields[0]] = fields[1]
    if not rows or lines[-1] != 'VERIFIED_FLOORPLAN_REGISTERS='+str(len(rows)):
        raise ValueError('Incomplete FIFO floorplan connection proof')
    return rows


def placement_trial_rows(path, registers, raw_trials=None):
    with Path(path).open(encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    if not rows or list(rows[0]) != ['cell','target','status','diagnostics']:
        raise ValueError('Missing placement trial diagnostics')
    accepted = set()
    rejected = 0
    if raw_trials is not None and len(raw_trials) != len(rows):
        raise ValueError('Placement table differs from raw console trial coverage')
    for index, row in enumerate(rows):
        raw = raw_trials[index] if raw_trials is not None else None
        if raw is not None and (row['cell'] != raw['cell'] or row['target'] != raw['target'] or
                               row['status'] != ('ACCEPTED' if raw['status']==0 else 'REJECTED')):
            raise ValueError('Placement table differs from the ordered raw console trials')
        if row['cell'] not in registers or not re.fullmatch(r'SLICE_X\d+Y\d+/[A-H]FF2?', row['target']):
            raise ValueError('Unexpected placement trial target')
        if row['status'] == 'ACCEPTED':
            if row['cell'] in accepted or re.search(r'(?:ERROR|FATAL):', row['diagnostics']):
                raise ValueError('Duplicate accepted register or hidden accepted-placement error')
            if row['target'].split('/')[0] != registers[row['cell']][2]:
                raise ValueError('Accepted trial differs from final relocation site')
            accepted.add(row['cell'])
        elif row['status'] == 'REJECTED':
            ids = raw['error_ids'] if raw is not None else re.findall(r'(?:ERROR|FATAL): \[([^]]+)\]', row['diagnostics'])
            if not ids or set(ids) != {'Vivado 12-1409'}:
                raise ValueError('Unexpected rejected-placement error')
            rejected += 1
        else:
            raise ValueError('Unknown placement trial status')
    if accepted != set(registers):
        raise ValueError('Incomplete accepted placement trial coverage')
    return {'accepted_registers':len(accepted), 'rejected_bel_attempts':rejected,
            'rejection_policy':'Only Vivado 12-1409 candidate rejection; full messages retained; final route and DRC mandatory'}


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ('build','experiment','equivalence','reopen','reference-audit','out'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('Preserve prior audit')
    root, exp, eq, reopen = a.build.resolve(), a.experiment.resolve(), a.equivalence.resolve(), a.reopen.resolve()
    result = {'pass': False, 'board_operations': 0, 'export_allowed': False, 'bound_files': {},
              'build': root.as_posix(), 'experiment': exp.as_posix(), 'reopen': reopen.as_posix()}

    def bind(p):
        p = Path(p).resolve()
        result['bound_files'][p.as_posix()] = sha(p)
        return p

    def load(p):
        return json.loads(bind(p).read_text())

    def verify_receipt(folder, stage):
        r = load(folder/'result.json')
        if not r['pass'] or r['stage'] != stage or r['exit_code']:
            raise ValueError('Unsuccessful '+stage)
        for name, key in [('console.log','log_sha256'),('timing_margin.tcl','script_sha256')]:
            if sha(bind(folder/name)) != r[key]:
                raise ValueError('Changed '+stage+' log/script')
        if r.get('runner_sha256') and sha(bind(folder/'optimize_timing_margin.py')) != r['runner_sha256']:
            raise ValueError('Changed experiment runner')
        actual_trials = placement_diagnostics((folder/'console.log').read_text(errors='replace'))
        actual_trial_counts = {'accepted':sum(t['status']==0 for t in actual_trials),
            'rejected':sum(t['status']==1 for t in actual_trials), 'raw_diagnostics_retained':True}
        if 'speculative_placement_trials' in r and r['speculative_placement_trials'] != actual_trial_counts:
            raise ValueError('Placement trial receipt differs from raw diagnostics')
        for name, digest in r['reports'].items():
            if sha(bind(folder/name)) != digest:
                raise ValueError('Changed report '+name)
        for name, digest in r.get('support_files', {}).items():
            if sha(bind(folder/name)) != digest:
                raise ValueError('Changed support script '+name)
        return r

    try:
        snapshot = a.out.parent/(a.out.stem+'_script.py')
        if snapshot.exists():
            raise ValueError('Preserve prior audit-script snapshot')
        shutil.copy2(__file__, snapshot)
        result['audit_script_sha256'] = sha(bind(snapshot))
        variant = load(root/'timing_variant.json')
        manifest = load(root/'inputs.json')
        if sha(root/'inputs.json') != variant['derived_manifest_sha256']:
            raise ValueError('Derived source identity changed')
        for name, digest in manifest['source_files'].items():
            if sha(bind(root/name)) != digest:
                raise ValueError('Build source changed: '+name)
        for change in variant['changes']:
            if sha(bind(Path(variant['baseline'])/change['path'])) != change['before_sha256']:
                raise ValueError('Frozen source changed')
            if sha(bind(root/change['path'])) != change['after_sha256']:
                raise ValueError('Variant source changed')
        evidence = load(eq/'result.json')
        if (not evidence['pass'] or evidence['identity_sha256'] != sha(root/'timing_variant.json') or
                evidence['build'] != root.as_posix()):
            raise ValueError('Missing matching RTL equivalence evidence')
        for name, digest in evidence['evidence'].items():
            if sha(bind(eq/name)) != digest:
                raise ValueError('Equivalence evidence changed')
        synth = load(root/'synth_result.json')
        if not synth['pass'] or synth['inputs_sha256'] != sha(root/'inputs.json'):
            raise ValueError('Synthesis does not bind current variant')
        if sha(bind(root/'synth_console.log')) != synth['steps'][0]['log_sha256']:
            raise ValueError('Synthesis log changed')
        if sha(bind(root/'synth_build.tcl')) != synth['script_sha256']:
            raise ValueError('Synthesis script changed')
        for name, digest in synth['reports'].items():
            if sha(bind(root/'reports'/name)) != digest:
                raise ValueError('Synthesis report changed: '+name)
        receipt = verify_receipt(exp, 'implement')
        implementation_log = (exp/'console.log').read_text(errors='replace')
        critical_ids = re.findall(r'^CRITICAL WARNING: \[([^\]]+)\]', implementation_log, re.M)
        clock_warnings = {'Route 35-4475', 'Route 35-359'}
        if set(critical_ids)-{'Vivado 12-8060', 'Route 35-39', *clock_warnings}:
            raise ValueError('Unreviewed implementation critical warning: '+str(sorted(set(critical_ids))))
        # Route 35-39 refers to the deliberately tightened routing target.
        # Do not waive it as a final signoff failure: restored/reopened timing,
        # complete routing and the exact original constraints are checked below.
        if 'Route 35-39' in critical_ids:
            tightened = bind(exp/'tightened_final.rpt').read_text()
            if not re.search(r'WNS\(ns\).*WHS\(ns\)', tightened):
                raise ValueError('Missing tightened timing evidence for Route 35-39')
            result['tightened_target_warning_retained'] = True
        # These transient clock-guidance warnings are only classified after
        # a later successful topology repair and complete global-clock route.
        # Full route, DRC, clock coverage and restored constraints are still
        # mandatory below; the warning is retained in the evidence.
        for match in re.finditer(r'^CRITICAL WARNING: \[(Route 35-4475|Route 35-359)\]', implementation_log, re.M):
            if not re.search(r'Fix Topology Constraints.*?ILP-based clock placer completed successfully\..*?'
                             r'Global Clock Net Routing \| Checksum:', implementation_log[match.end():], re.S):
                raise ValueError('Clock-guidance warning lacks subsequent topology/clock-route repair')
        result['implementation_critical_warnings'] = {
            'counts': {key:critical_ids.count(key) for key in sorted(set(critical_ids))},
            'classification': ('Temporary stricter user uncertainty affects incremental optimization runtime; '
                               'it is kept active then restored before signoff. Clock-guidance warnings are followed by '
                               'successful topology repair and global-clock routing. Route 35-39 records a missed temporary '
                               'tightened target, not permission to miss the original requirements; final restored/reopened '
                               'timing, route, DRC and coverage gates remain mandatory.')}
        if receipt['source_checkpoint_sha256'] != sha(bind(root/'joint_synth.dcp')):
            raise ValueError('Implementation used a different netlist')
        if receipt.get('physical_resume'):
            resumed = receipt['physical_resume']
            saved = bind(resumed['path'])
            producer = saved.parent
            visited_resumes = set()
            ancestor_path = saved
            while True:
                if ancestor_path in visited_resumes:
                    raise ValueError('Cyclic physical-resume evidence')
                visited_resumes.add(ancestor_path)
                ancestor_folder = ancestor_path.parent
                ancestor = load(ancestor_folder/'result.json')
                if ancestor['source_checkpoint_sha256'] != receipt['source_checkpoint_sha256']:
                    raise ValueError('Physical resume ancestry uses different synthesis')
                if sha(bind(ancestor_folder/'console.log')) != ancestor['log_sha256'] or sha(bind(ancestor_folder/'timing_margin.tcl')) != ancestor['script_sha256']:
                    raise ValueError('Physical resume ancestry log or script changed')
                inherited = ancestor.get('physical_resume')
                if not inherited:
                    break
                ancestor_path = bind(inherited['path'])
                if sha(ancestor_path) != inherited['sha256'] or sha(bind(ancestor_folder/'resume_physical.dcp')) != inherited['sha256']:
                    raise ValueError('Physical resume ancestor checkpoint changed')
                if sha(bind(ancestor_path.parent/'result.json')) != inherited['producer_result_sha256']:
                    raise ValueError('Physical resume ancestor receipt changed')
            prior = load(producer/'result.json')
            if sha(saved) != resumed['sha256'] or sha(bind(exp/'resume_physical.dcp')) != resumed['sha256']:
                raise ValueError('Resumed physical checkpoint changed')
            if sha(producer/'result.json') != resumed['producer_result_sha256'] or prior['source_checkpoint_sha256'] != receipt['source_checkpoint_sha256']:
                raise ValueError('Resume producer does not bind the same synthesis')
            if sha(bind(producer/'console.log')) != prior['log_sha256'] or sha(bind(producer/'timing_margin.tcl')) != prior['script_sha256']:
                raise ValueError('Failed producer log or script changed')
            if prior['pass'] != resumed['producer_pass']:
                raise ValueError('Resume producer status changed')
            retained_constraints = xdc_commands(bind(exp/'resumed_constraints.xdc'), True,
                (receipt['setup_margin_ns'], receipt['hold_margin_ns']), require_restoration=False)
            result['physical_resume'] = {**resumed, 'producer_evidence_verified':True,
                'checkpoint_hash_binding':'New resume input hash; no successful producer checkpoint hash is claimed'}
        reference = load(a.reference_audit)
        if not reference['pass']:
            raise ValueError('Reference audit failed')
        if receipt['reference_checkpoint_sha256'] != reference['checkpoint_sha256']:
            raise ValueError('Unexpected incremental reference')
        before = xdc_commands(exp/'baseline_constraints.xdc')
        after = xdc_commands(exp/'restored_constraints.xdc', True,
                             (receipt['setup_margin_ns'],receipt['hold_margin_ns']))
        eco_buffers = {}
        relocated_registers = {}
        floorplanned_registers = {}
        if receipt['strategy'] == 'preplace_hold':
            eco_buffers = hold_eco_rows(bind(exp/'hold_eco_final.tsv'))
            for name in ('hold_eco_before_route.tsv', 'hold_eco_after_eco_route.tsv'):
                if hold_eco_rows(bind(exp/name)) != eco_buffers:
                    raise ValueError('Hold ECO buffer set changed during implementation')
            # Only the named identity buffers may carry new DONT_TOUCH
            # attributes. No new timing exception, clock or delay is allowed.
            filtered = []
            physical_count = 0
            for line in after:
                match = re.fullmatch(r'set_property DONT_TOUCH (?:true|1) \[get_cells (?:\{([^}]+)\}|([^\s]+))\]',line,re.I)
                if match and (match[1] or match[2]) in eco_buffers:
                    physical_count += 1
                else:
                    filtered.append(line)
            after = filtered
            result['hold_eco_physical_property_commands'] = physical_count
            original_cells = cell_snapshot(bind(exp/'hold_eco_before_cells.tsv'))
            expected_cells = {**original_cells, **{name:'LUT1' for name in eco_buffers}}
            if len(expected_cells) != len(original_cells)+len(eco_buffers):
                raise ValueError('Hold ECO overwrites an existing cell')
            for name in ('hold_eco_inserted_cells.tsv','hold_eco_final_cells.tsv'):
                if cell_snapshot(bind(exp/name)) != expected_cells:
                    raise ValueError('Unexpected primitive changes during hold ECO: '+name)
            result['hold_eco'] = {'identity_buffers':len(eco_buffers), 'additional_registers':0,
                                  'additional_pipeline_cycles':0, 'connections_and_controls_verified':True}
        if receipt['strategy'] == 'preplace_relocate':
            relocated_registers = relocation_rows(bind(exp/'relocation_final.tsv'))
            for name in ('relocation_before_route.tsv', 'relocation_after_route.tsv'):
                if relocation_rows(bind(exp/name)) != relocated_registers:
                    raise ValueError('Relocated registers changed during implementation')
            original_cells = cell_snapshot(bind(exp/'relocation_before_cells.tsv'))
            if any(original_cells.get(name) != 'FDRE' for name in relocated_registers):
                raise ValueError('Relocation changed an unexpected primitive')
            for name in ('relocation_moved_cells.tsv','relocation_final_cells.tsv'):
                if cell_snapshot(bind(exp/name)) != original_cells:
                    raise ValueError('Physical relocation changed the primitive netlist')
            result['register_relocation'] = {'registers':len(relocated_registers), 'additional_primitives':0,
                'additional_pipeline_cycles':0, 'connections_and_controls_verified':True}
            reconstructed_parameters = None
            helper_text = (exp/'fifo_hold_relocate.tcl').read_text()
            if 'proc recreate_fifo_register ' in helper_text:
                reconstructed_parameters = register_parameter_rows(bind(exp/'reconstruction_before_parameters.tsv'), relocated_registers)
                for name in ('relocation_before_route.tsv.parameters.tsv', 'relocation_after_route.tsv.parameters.tsv',
                             'relocation_final.tsv.parameters.tsv'):
                    if register_parameter_rows(bind(exp/name), relocated_registers) != reconstructed_parameters:
                        raise ValueError('Reconstructed FDRE functional parameters changed')
                result['register_relocation']['same_type_reconstruction'] = True
                result['register_relocation']['functional_parameters_verified'] = True
            if (exp/'relocation_placement_trials.tsv').is_file():
                result['register_relocation']['placement_trials'] = placement_trial_rows(bind(exp/'relocation_placement_trials.tsv'), relocated_registers,
                    placement_diagnostics(implementation_log))
        if receipt['strategy'] == 'preplace_fifo_logic':
            floorplanned_registers = floorplan_rows(bind(exp/'fifo_floorplan_final.tsv'))
            if set(floorplan_rows(bind(exp/'fifo_floorplan_after_place.tsv'))) != set(floorplanned_registers):
                raise ValueError('FIFO floorplan target set changed')
            evidence_path = bind(receipt['fifo_floor_evidence']['path'])
            if sha(evidence_path) != receipt['fifo_floor_evidence']['sha256']:
                raise ValueError('Reference FIFO path classification changed')
            floor_receipt = load(evidence_path.parent/'result.json')
            if not floor_receipt['pass'] or floor_receipt['source_checkpoint_sha256'] != reference['checkpoint_sha256']:
                raise ValueError('FIFO path classification belongs to another reference')
            historical_table_hash = floor_receipt['reports'].get(evidence_path.name)
            if historical_table_hash and historical_table_hash != sha(evidence_path):
                raise ValueError('Historical FIFO path classification hash changed')
            # The first diagnostic runner predated TSV manifest support.
            # Do not claim an inherited table hash that was never recorded.
            # This experiment binds the table as a new physical-placement
            # input; independent full-design signoff remains mandatory.
            table_binding = 'Inherited diagnostic receipt' if historical_table_hash else 'New experiment receipt; legacy diagnostic did not hash TSV'
            for name, digest in floor_receipt['reports'].items():
                if sha(bind(evidence_path.parent/name)) != digest:
                    raise ValueError('Historical FIFO diagnostic report changed')
            rows = list(csv.DictReader(evidence_path.open(encoding='utf-8'), delimiter='\t'))
            expected = {row['end'].removesuffix('/D') for row in rows if float(row['slack'])<receipt['hold_margin_ns']
                and row['source_ref'] in ('RAMD32','RAMD64E') and row['dest_ref']=='FDRE'
                and row['source_loc']==row['dest_loc'] and row['end'].endswith('/D')}
            if set(floorplanned_registers) != expected:
                raise ValueError('FIFO floorplan omits or adds unexpected reference targets')
            bind(exp/'fifo_floorplan_records.list')
            result['fifo_floorplan'] = {'registers':len(floorplanned_registers), 'additional_pipeline_cycles':0,
                'placement':'Native placer within SLICEL sites; temporary Pblock removed before signoff',
                'connections_and_controls_verified':True, 'classification_table_hash_binding':table_binding}
        # A synthesized design still contains dead SmartConnect reset/FIFO
        # scopes. Compare compiled inputs at the same synthesis stage, then
        # demand the original routed constraint contract at the routed stage.
        old_synth = bind(Path(variant['baseline'])/'joint_synth.dcp')
        new_synth = bind(root/'joint_synth.dcp')
        old_embedded, new_embedded = embedded_constraints(old_synth), embedded_constraints(new_synth)
        if old_embedded != new_embedded:
            raise ValueError('Compiled synthesis constraints differ from the frozen build')
        result['synthesis_constraints_identical'] = True
        result['compiled_constraint_line_counts'] = {k:len(v) for k,v in old_embedded.items()}
        ref_folder = Path(reference['experiment'])
        contract = bind(Path(reference.get('original_routed_constraints_file', ref_folder/'baseline_constraints.xdc')))
        original = xdc_commands(contract)
        result['original_routed_constraints_file'] = contract.as_posix()
        if list(map(waiver_creation_time, original)) != list(map(waiver_creation_time, after)):
            (a.out.parent/(a.out.stem+'_routed_constraint_diff.txt')).write_text('\n'.join(difflib.unified_diff(original,after)),encoding='utf-8')
            raise ValueError('Final routed constraints differ from original; inspect before accepting')
        if receipt.get('physical_resume') and list(map(waiver_creation_time, retained_constraints)) != list(map(waiver_creation_time, original)):
            raise ValueError('Resumed physical checkpoint changed the original constraint contract')
        result['pre_optimization_constraint_commands'] = len(before)
        result['constraint_comparison_policy'] = ('Synthesis checkpoint constraints compared with frozen synthesis; '
            'routed constraints compared with audited original routed constraints. Only waiver creation timestamps '
            'and validated source-file provenance paths are normalized; clock/exception values, selectors and scopes are preserved.')
        clock_text = (exp/'restored_clocks.rpt').read_text()
        rows = re.findall(r'^(clk_pl_[01])\s+(clk_pl_[01])\s+([\d.]+)\s+([\d.]+)\s+rf -> rf$',clock_text,re.M)
        if sorted(rows) != [('clk_pl_0','clk_pl_0','0.000','0.000'),('clk_pl_1','clk_pl_1','0.000','0.000')]:
            raise ValueError('Effective user uncertainty not zero')
        candidate = bind(exp/'optimized_routed.dcp')
        result['checkpoint_sha256'] = sha(candidate)
        proof = verify_receipt(reopen, 'verify')
        if proof['source_checkpoint_sha256'] != result['checkpoint_sha256']:
            raise ValueError('Reopened checkpoint identity differs')
        if eco_buffers:
            if proof.get('hold_manifest_sha256') != sha(bind(exp/'hold_eco_records.list')):
                raise ValueError('Independent reopen used different hold ECO records')
            if sha(bind(reopen/'fifo_hold_eco.tcl')) != sha(bind(exp/'fifo_hold_eco.tcl')):
                raise ValueError('Independent hold ECO verifier differs')
            if hold_eco_rows(bind(reopen/'hold_eco_reopened.tsv')) != eco_buffers:
                raise ValueError('Saved checkpoint hold ECO differs')
            if cell_snapshot(bind(reopen/'hold_eco_reopened_cells.tsv')) != expected_cells:
                raise ValueError('Saved checkpoint primitive set differs')
            result['hold_eco']['independent_reopen_verified'] = True
        if relocated_registers:
            if proof.get('relocation_manifest_sha256') != sha(bind(exp/'relocation_records.list')):
                raise ValueError('Independent reopen used different relocation records')
            if sha(bind(reopen/'fifo_hold_relocate.tcl')) != sha(bind(exp/'fifo_hold_relocate.tcl')):
                raise ValueError('Independent relocation verifier differs')
            if relocation_rows(bind(reopen/'relocation_reopened.tsv')) != relocated_registers:
                raise ValueError('Saved checkpoint register relocation differs')
            if cell_snapshot(bind(reopen/'relocation_reopened_cells.tsv')) != original_cells:
                raise ValueError('Saved checkpoint primitives differ after relocation')
            if reconstructed_parameters is not None:
                if register_parameter_rows(bind(reopen/'relocation_reopened.tsv.parameters.tsv'), relocated_registers) != reconstructed_parameters:
                    raise ValueError('Reopened reconstructed FDRE parameters differ')
            result['register_relocation']['independent_reopen_verified'] = True
        if floorplanned_registers:
            if proof.get('floorplan_manifest_sha256') != sha(bind(exp/'fifo_floorplan_records.list')):
                raise ValueError('Independent reopen used different FIFO floorplan records')
            if sha(bind(reopen/'fifo_hold_floorplan.tcl')) != sha(bind(exp/'fifo_hold_floorplan.tcl')):
                raise ValueError('Independent FIFO floorplan verifier differs')
            if floorplan_rows(bind(reopen/'fifo_floorplan_reopened.tsv')) != floorplanned_registers:
                raise ValueError('Saved checkpoint FIFO floorplan differs')
            result['fifo_floorplan']['independent_reopen_verified'] = True
        unused = ps_clock_proof((reopen/'reopened_unused_ps_clocks.txt').read_text(),
                                (reopen/'reopened_clock_check.rpt').read_text())
        checked = timing_summary((reopen/'reopened_timing.rpt').read_text(), unused)
        result['timing'] = checked
        result['intra_clock_timing'] = intra_clock_summary((reopen/'reopened_timing.rpt').read_text())
        reference_timing = reference.get('optimized', reference.get('timing'))
        if not reference_timing:
            raise ValueError('Reference audit has no timing summary')
        result['reference_timing'] = reference_timing
        result['resources'] = resource_summary(bind(exp/'routed_utilization.rpt').read_text())
        result['reference_resources'] = resource_summary(bind(ref_folder/'routed_utilization.rpt').read_text())
        if any(result['resources'][k]['available'] != result['reference_resources'][k]['available']
               for k in result['resources']):
            raise ValueError('Resource capacities differ from the reference device')
        result['resource_delta'] = {k: v['used']-result['reference_resources'][k]['used']
                                    for k,v in result['resources'].items()}
        actual = {k: worst(exp/'final_path_summary.txt',t) for k,t in [('WNS_ns','max'),('WHS_ns','min')]}
        if any(checked[k] != actual[k] for k in actual):
            raise ValueError('Saved checkpoint differs from candidate reports')
        result['improvement_ns'] = {k:round(actual[k]-reference_timing[k],6) for k in actual}
        result['targets_met'] = actual['WNS_ns']>=receipt['setup_margin_ns'] and actual['WHS_ns']>=receipt['hold_margin_ns']
        result['both_margins_improved'] = all(v>0 for v in result['improvement_ns'].values())
        result['route'] = route_summary((reopen/'reopened_route.rpt').read_text())
        if route_summary((exp/'route_status.rpt').read_text()) != result['route']:
            raise ValueError('Reopened route differs')
        result['bus_skew'] = bus_skew_summary((reopen/'reopened_bus_skew.rpt').read_text())
        for name, severities in [('routed_drc.rpt',{'error','critical warning'}),('routed_cdc.rpt',{'error','critical'})]:
            if critical_rows((exp/name).read_text(),severities):
                raise ValueError('Blocking violation: '+name)
        if critical_rows((reopen/'reopened_drc.rpt').read_text(),{'error','critical warning'}):
            raise ValueError('Reopened DRC violation')
        if (exp/'cnn_address_mapping.txt').read_text().strip() != 'CNN_ADDRESS_DSP_CELLS=0':
            raise ValueError('Address logic mapping did not take effect')
        result['constraint_commands_unchanged'] = len(after)
        result['equivalence_scope'] = evidence['scope']
        result['not_tested'] = evidence['not_tested']
        result['pass'] = True
    except Exception as e:
        result['error'] = str(e)
        raise
    finally:
        a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='bound_files'},indent=2,ensure_ascii=False))


if __name__ == '__main__':
    main()
