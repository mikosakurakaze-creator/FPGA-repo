"""Build only a fresh Phase 4G V1.2 BD/output-products/synthesis delivery."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[3]
RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')
OUT = RUN / 'phase4g'
# Keep generated Windows IP paths short; the parent directory records Phase 4G.
PROJECT_NAME = 'v12_wc'
BD_SOURCE = REPO / 'fpga/vivado/three_module_integration_v1_2/three_module_integration_v1_2.srcs/sources_1/bd/system/system.bd'
MODULES = (
    'zero_dce_cnn_top_row_axi_writer',
    'zero_dce_cnn_top_row_axi_writer_2',
    'zero_dce_cnn_top_p_anonymous_namespace_output_writer',
)
CHECKS = ('abi', 'filesets', 'rebuild', 'writer_probe', 'cnn_single', 'ooc_synthesis')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def tclword(value):
    value = str(value).replace('\\', '/')
    if any(c in value for c in '{}\n\r'):
        raise ValueError('Unsupported Tcl path/value: ' + value)
    return '{' + value + '}'


def prepare(output, release_gate):
    if output.exists():
        raise RuntimeError('Refusing to overwrite integration output: ' + str(output))
    gate = json.loads(release_gate.read_text(encoding='utf-8'))
    if gate.get('status') != 'PASS':
        raise RuntimeError('Packaged release gate has not passed')
    for key in CHECKS:
        if gate.get('checks', {}).get(key) != 'PASS':
            raise RuntimeError('Release check has not passed: ' + key)
    ip = Path(gate['formal_ip_path']).resolve()
    formal_manifest = Path(gate['formal_manifest_path']).resolve()
    if not (ip / 'component.xml').is_file() or not formal_manifest.is_file():
        raise RuntimeError('Formal packaged IP or build manifest missing')
    manifest = json.loads(formal_manifest.read_text(encoding='utf-8'))
    if Path(manifest['generated_ip_path']).resolve() != ip or formal_manifest.parent != ip:
        raise RuntimeError('Build manifest belongs to a different IP release')
    if manifest.get('status') != 'PACKAGED_IP_GATE_PASS':
        raise RuntimeError('Formal manifest does not record a successful package gate')
    if sha(ip / 'component.xml') != manifest['identity']['component_xml_sha256']:
        raise RuntimeError('Formal component metadata differs from the sealed manifest')
    evidence = {key: {'path': Path(value).resolve().as_posix(), 'sha256': sha(value)}
                for key, value in gate['evidence'].items()}
    if not evidence:
        raise RuntimeError('No release evidence was recorded')
    for mod in MODULES:
        relative = 'hdl/verilog/' + mod + '.v'
        if not (ip / relative).is_file():
            raise RuntimeError('Formal write-credit RTL missing: ' + mod)
        if sha(ip / relative) != manifest['identity']['patched_rtl'][relative]:
            raise RuntimeError('Formal patched RTL differs from the sealed manifest: ' + mod)
    output.mkdir(parents=True)
    reports = output / 'reports'
    reports.mkdir()
    stable_inputs = {}
    stable_copies = []
    for name in ('bilinear', 'curve'):
        source = RUN / 'ip_repo' / name
        hashes = tree(source)
        destination = output / 'stable_ip_repo' / name
        shutil.copytree(source, destination)
        if hashes != tree(destination):
            raise RuntimeError('Stable IP copy is not identical: ' + name)
        stable_inputs[name] = {'source': source.as_posix(), 'copy': destination.as_posix(), 'files': hashes}
        stable_copies.append(destination)
    design = json.loads(BD_SOURCE.read_text(encoding='utf-8'))
    seed = output / 'system_seed.bd'
    design['design']['design_info']['gen_directory'] = '../../../../' + PROJECT_NAME + '.gen/sources_1/bd/system'
    seed.write_text(json.dumps(design, indent=2) + '\n', encoding='utf-8')
    project = output / 'project'
    config = output / 'integration_config.tcl'
    repos = [ip, *stable_copies]
    config.write_text('\n'.join([
        'set project_name ' + tclword(PROJECT_NAME),
        'set project_dir ' + tclword(project.as_posix()),
        'set report_dir ' + tclword(reports.as_posix()),
        'set bd_seed ' + tclword(seed.as_posix()),
        'set ip_repos [list ' + ' '.join(tclword(p.as_posix()) for p in repos) + ']',
        'set patched_modules [list ' + ' '.join(tclword(m) for m in MODULES) + ']',
        '',
    ]), encoding='utf-8')
    before = {
        'status': 'PREPARED', 'created_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'release_gate': release_gate.as_posix(), 'release_gate_sha256': sha(release_gate),
        'release_checks': gate['checks'], 'release_evidence': evidence,
        'formal_ip_path': ip.as_posix(), 'formal_ip_before': tree(ip),
        'formal_manifest_path': formal_manifest.as_posix(), 'formal_manifest_sha256': sha(formal_manifest),
        'formal_release_identity_sha256': manifest['identity_sha256'],
        'saved_v1_2_bd_source': BD_SOURCE.as_posix(), 'saved_v1_2_bd_sha256': sha(BD_SOURCE),
        'seed_bd_path': seed.as_posix(), 'seed_bd_sha256': sha(seed),
        'stable_ip_inputs': stable_inputs, 'ip_repositories': [p.as_posix() for p in repos],
        'project_path': project.as_posix(), 'project_name': PROJECT_NAME,
        'old_project_relation': 'Fresh independent V1.2 project made from the saved V1.2 system.bd; original XPR/runs/cache remain unopened and unchanged.',
        'ip_cache': 'disabled', 'implementation_requested': False,
    }
    write_json(output / 'integration_inputs.json', before)
    return before


def verify_inputs(output):
    before = json.loads((output / 'integration_inputs.json').read_text(encoding='utf-8'))
    for key, hashkey in [('release_gate', 'release_gate_sha256'), ('formal_manifest_path', 'formal_manifest_sha256'),
                         ('saved_v1_2_bd_source', 'saved_v1_2_bd_sha256'), ('seed_bd_path', 'seed_bd_sha256')]:
        if sha(before[key]) != before[hashkey]:
            raise RuntimeError('Integration input changed: ' + before[key])
    if tree(Path(before['formal_ip_path'])) != before['formal_ip_before']:
        raise RuntimeError('Formal IP changed during integration')
    for entry in before['release_evidence'].values():
        if sha(entry['path']) != entry['sha256']:
            raise RuntimeError('Release evidence changed: ' + entry['path'])
    for entry in before['stable_ip_inputs'].values():
        if tree(Path(entry['source'])) != entry['files'] or tree(Path(entry['copy'])) != entry['files']:
            raise RuntimeError('Stable IP copy or source changed')
    return before


def vivado(output, phase):
    verify_inputs(output)
    command = output / ('run_' + phase + '.cmd')
    script = REPO / ('fpga/scripts/vivado_three_module_v1_2_phase4g_' + phase + '.tcl')
    config = output / 'integration_config.tcl'
    command.write_text('\n'.join([
        '@echo off', 'setlocal',
        'if not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"',
        'call "E:\\Xilinx\\2025.2\\data\\settings64.bat" || exit /b 1',
        'cd /d "' + str(output) + '" || exit /b 2',
        'call "E:\\Xilinx\\2025.2\\Vivado\\bin\\vivado.bat" -mode batch -source "' + str(script) +
        '" -log "' + str(output / (phase + '_vivado.log')) + '" -journal "' + str(output / (phase + '_vivado.jou')) +
        '" -notrace -tclargs "' + str(config) + '"',
        'exit /b %ERRORLEVEL%', '',
    ]), encoding='utf-8')
    print('PHASE4G_INTEGRATION_START=' + phase, flush=True)
    started = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    with (output / (phase + '_console.log')).open('wb') as stream:
        result = subprocess.run(['cmd.exe', '/d', '/c', str(command)], cwd=output, stdout=stream, stderr=subprocess.STDOUT,
                                env={**os.environ, 'PROCESSOR_ARCHITECTURE': 'AMD64'})
    write_json(output / (phase + '_exit_status.json'), {'phase': phase, 'returncode': result.returncode,
               'started_at': started, 'ended_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()})
    if result.returncode != 0:
        raise RuntimeError('Vivado ' + phase + ' failed; inspect ' + str(output / (phase + '_console.log')))
    verify_inputs(output)
    print('PHASE4G_INTEGRATION_DONE=' + phase, flush=True)


def compare_bd(before, actual):
    original = json.loads(Path(before['saved_v1_2_bd_source']).read_text())['design']
    fresh = json.loads(actual.read_text())['design']
    for key in ('nets', 'interface_nets', 'addressing', 'design_tree'):
        if original[key] != fresh[key]:
            raise RuntimeError('Saved V1.2 BD field differs: ' + key)
    ps_evidence = None
    ps_added = {}
    for name, cell in original['components'].items():
        new = fresh['components'][name]
        if cell['vlnv'] != new['vlnv']:
            raise RuntimeError('BD VLNV differs: ' + name)
        for key, value in cell.get('parameters', {}).items():
            if new.get('parameters', {}).get(key) != value:
                raise RuntimeError('BD configuration differs: ' + name + ':' + key)
        if name == 'zynq_ultra_ps_e_0':
            # Vivado serialized one already-resolved PS value into this BD.
            # Only this exact addition is allowed; all effective XCI values must agree.
            ps_added = {key: value for key, value in new.get('parameters', {}).items()
                        if key not in cell.get('parameters', {})}
            if ps_added not in ({}, {'PSU_MIO_22_INPUT_TYPE': {'value': 'cmos'}}):
                raise RuntimeError('Unexpected serialized PS parameters: ' + repr(ps_added))
            if {k: v for k, v in cell.items() if k != 'parameters'} != {k: v for k, v in new.items() if k != 'parameters'}:
                raise RuntimeError('PS nonparameter metadata changed')
            relative_xci = 'ip/system_zynq_ultra_ps_e_0_0/system_zynq_ultra_ps_e_0_0.xci'
            old_xci = Path(before['saved_v1_2_bd_source']).parent / relative_xci
            fresh_xci = actual.parent / relative_xci
            old_params = json.loads(old_xci.read_text())['ip_inst']['parameters']
            new_params = json.loads(fresh_xci.read_text())['ip_inst']['parameters']
            groups = {}
            for group in ('component_parameters', 'model_parameters'):
                old_values = {key: [entry.get('value') for entry in entries] for key, entries in old_params[group].items()}
                new_values = {key: [entry.get('value') for entry in entries] for key, entries in new_params[group].items()}
                if old_values != new_values:
                    raise RuntimeError('PS effective XCI configuration changed: ' + group)
                groups[group] = {'status': 'PASS', 'values_checked': len(old_values), 'differences': [],
                                 'actual_value_map_sha256': hashlib.sha256(json.dumps(old_values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
            old_mio = old_params['component_parameters']['PSU_MIO_22_INPUT_TYPE']
            new_mio = new_params['component_parameters']['PSU_MIO_22_INPUT_TYPE']
            if [entry.get('value') for entry in old_mio] != ['cmos'] or [entry.get('value') for entry in new_mio] != ['cmos']:
                raise RuntimeError('PS serialized MIO value differs from the original resolved value')
            ps_evidence = {'status': 'PASS', 'old_xci': old_xci.as_posix(), 'old_xci_sha256': sha(old_xci),
                           'new_xci': fresh_xci.as_posix(), 'new_xci_sha256': sha(fresh_xci),
                           'actual_value_identity': groups, 'PSU_MIO_22_INPUT_TYPE_old': old_mio,
                           'PSU_MIO_22_INPUT_TYPE_new': new_mio,
                           'note': 'The original PS resolved value cmos was explicitly serialized into the fresh BD. All 1692 configurable and 37 model actual values are identical; source tags and project/runtime metadata are not hardware value changes.'}
        elif name == 'zero_dce_cnn_top_0':
            comparable = dict(new)
            comparable['ip_revision'] = cell['ip_revision']
            if comparable != cell or int(new['ip_revision']) != int(cell['ip_revision']) + 1:
                raise RuntimeError('CNN BD changed outside the single sealed IP revision increment')
        elif cell != new:
            raise RuntimeError('Protected BD cell differs: ' + name)
    return {'topology': 'PASS', 'address_map': 'PASS', 'stable_cells': 'PASS', 'all_existing_parameters': 'PASS',
            'cnn_original_revision': original['components']['zero_dce_cnn_top_0'].get('ip_revision'),
            'cnn_final_revision': fresh['components']['zero_dce_cnn_top_0'].get('ip_revision'),
            'ps_serialized_existing_resolved_values': ps_added, 'ps_effective_xci_identity': ps_evidence}


def analyze(output):
    before = verify_inputs(output)
    reports = output / 'reports'
    project = Path(before['project_path'])
    create_log = (output / 'create_console.log').read_text(errors='replace')
    synth_log = (output / 'synth_console.log').read_text(errors='replace')
    if 'PHASE4G_CREATE_VALIDATE=PASS' not in create_log:
        raise RuntimeError('Fresh project did not validate')
    for marker in ('TOPOLOGY', 'VALIDATE', 'OUTPUT_PRODUCTS', 'WRAPPER', 'SYNTH', 'WRITECREDIT_HIERARCHY', 'POST_SYNTHESIS_REPORTS'):
        if 'PHASE4G_' + marker + '=PASS' not in synth_log:
            raise RuntimeError('Missing integration marker: ' + marker)
    if 'ERROR:' in create_log or 'ERROR:' in synth_log:
        raise RuntimeError('Vivado reported an error')
    bd = project / (PROJECT_NAME + '.srcs/sources_1/bd/system/system.bd')
    bd_evidence = compare_bd(before, bd)
    inventory = list(csv.DictReader((reports / 'vivado_source_inventory.tsv').open(encoding='utf-8'), delimiter='\t'))
    formal = Path(before['formal_ip_path'])
    catalog = {}
    for line in (reports / 'catalog_xilinx.com_hls_zero_dce_cnn_top_1.0.txt').read_text().splitlines():
        if '\t' in line:
            key, value = line.split('\t', 1)
            catalog[key] = value
    if Path(catalog['REPOSITORY']).resolve() != formal or Path(catalog['XML_FILE_NAME']).resolve() != formal / 'component.xml':
        raise RuntimeError('CNN catalog resolved outside the formal release')
    formal_identity = json.loads(Path(before['formal_manifest_path']).read_text())['identity']
    if int(catalog['CORE_REVISION']) != formal_identity['core_revision'] or catalog['VLNV'] != 'xilinx.com:hls:zero_dce_cnn_top:1.0':
        raise RuntimeError('CNN catalog revision/VLNV differs from the formal release')
    formal_rtl = {p.name: sha(p) for p in sorted((formal / 'hdl/verilog').iterdir())
                  if p.is_file() and p.suffix in ('.v', '.vh', '.dat')}
    source_matches = {}
    for name, expected in formal_rtl.items():
        matches = [r for r in inventory if Path(r['path']).name == name and r['USED_IN_SYNTHESIS'] == '1']
        if not matches:
            raise RuntimeError('Formal CNN source absent from synthesis inventory: ' + name)
        records = []
        for match in matches:
            path = Path(match['path'])
            digest = sha(path)
            if digest != expected:
                raise RuntimeError('Old or mismatched synthesized CNN source: ' + str(path))
            if not path.resolve().is_relative_to(project.resolve()) and not path.resolve().is_relative_to(formal.resolve()):
                raise RuntimeError('CNN source resolved outside Phase 4G formal IP/project: ' + str(path))
            records.append({'path': path.as_posix(), 'sha256': digest,
                            'used_in_synthesis': match['USED_IN_SYNTHESIS'], 'used_in_simulation': match['USED_IN_SIMULATION']})
        source_matches[name] = records
    for name, records in source_matches.items():
        if not all(r['used_in_simulation'] == '1' for r in records):
            raise RuntimeError('Formal source is not shared with simulation: ' + name)
    hierarchy = list(csv.DictReader((reports / 'writecredit_hierarchy.tsv').open(encoding='utf-8'), delimiter='\t'))
    for mod in MODULES:
        if not any(row['module'] == mod and int(row['primitive_descendants']) > 0 for row in hierarchy):
            raise RuntimeError('Patched module missing actual system primitives: ' + mod)
    implementation_scope = list(csv.DictReader((reports / 'implementation_scope.tsv').open(encoding='utf-8'), delimiter='\t'))
    if any(row['status'] != 'Not started' or row['progress'] != '0%' for row in implementation_scope):
        raise RuntimeError('Implementation unexpectedly started')
    if list(project.rglob('*.bit')) or list(project.rglob('*.xsa')):
        raise RuntimeError('Unexpected bitstream/XSA in synthesis-only project')
    util = (reports / 'system_utilization.rpt').read_text()
    def used(name):
        match = re.search(r'\|\s*' + re.escape(name) + r'\s*\|\s*(\d+)', util)
        if not match:
            raise RuntimeError('Missing utilization: ' + name)
        return int(match[1])
    resources = dict(LUT=used('CLB LUTs*'), FF=used('CLB Registers'), RAMB36=used('RAMB36/FIFO*'),
                     RAMB18=used('RAMB18'), URAM=used('URAM'), DSP=used('DSPs'))
    resources['BRAM18_equivalent'] = 2 * resources['RAMB36'] + resources['RAMB18']
    resources['BRAM_tiles'] = resources['RAMB36'] + resources['RAMB18'] / 2
    limits = dict(LUT=117120, FF=234240, BRAM18_equivalent=288, URAM=64, DSP=1248)
    if not all(resources[key] <= maximum for key, maximum in limits.items()):
        raise RuntimeError('Whole system resource limit exceeded')
    timing_text = (reports / 'system_timing_summary.rpt').read_text()
    row = re.search(r'\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s*\n', timing_text)
    if row is None:
        raise RuntimeError('Missing synthesis timing summary')
    timing = dict(WNS_ns=float(row[1]), TNS_ns=float(row[2]), setup_failing_endpoints=int(row[3]),
                  WHS_ns=float(row[5]), THS_ns=float(row[6]), hold_failing_endpoints=int(row[7]),
                  WPWS_ns=float(row[9]), TPWS_ns=float(row[10]))
    if timing['WNS_ns'] < 0 or timing['TNS_ns'] != 0 or timing['setup_failing_endpoints'] != 0:
        raise RuntimeError('100MHz pre-route setup estimate failed')
    clocks = (reports / 'system_clocks.rpt').read_text()
    if not re.search(r'\b10\.000\b', clocks):
        raise RuntimeError('No 10ns clock recorded')
    drc = (reports / 'system_drc.rpt').read_text()
    if '| Error ' in drc or '| Critical Warning ' in drc:
        raise RuntimeError('Synthesis DRC has a serious violation')
    dcp = project / (PROJECT_NAME + '.runs/synth_1/system_wrapper.dcp')
    cnn_runs = [p for p in (project / (PROJECT_NAME + '.runs')).glob('*zero_dce*synth_1') if p.is_dir()]
    if len(cnn_runs) != 1:
        raise RuntimeError('CNN synthesis run is missing or ambiguous')
    cnn_dcps = list(cnn_runs[0].glob('*.dcp'))
    if len(cnn_dcps) != 1 or not dcp.is_file():
        raise RuntimeError('Fresh synthesis checkpoint missing')
    cnn_log = (cnn_runs[0] / 'runme.log').read_text(errors='replace')
    if 'synth_design completed successfully' not in cnn_log:
        raise RuntimeError('CNN IP run did not actually execute successful synthesis')
    result = {
        'status': 'PASS', 'bd_validate': 'PASS', 'output_products': 'PASS', 'synthesis': 'PASS',
        'tool_version': 'Vivado 2025.2', 'clock_MHz': 100, 'bd_identity': bd_evidence,
        'resources': resources, 'device_limits': limits, 'pre_route_timing': timing,
        'hold_note': 'Unplaced pre-route hold estimate only; no final hold conclusion. Implementation and route were not run.',
        'formal_ip_path': formal.as_posix(), 'release_gate_sha256': before['release_gate_sha256'],
        'formal_release_identity_sha256': before['formal_release_identity_sha256'],
        'source_audit': 'PASS', 'formal_verilog_files_checked': sum(name.endswith('.v') for name in source_matches),
        'formal_hdl_headers_rom_files_checked': len(source_matches), 'resolved_sources': source_matches,
        'cnn_catalog_resolution': {key: catalog[key] for key in ('REPOSITORY', 'XML_FILE_NAME', 'CORE_REVISION', 'VLNV')},
        'writecredit_hierarchy': hierarchy, 'ip_cache': 'disabled',
        'writecredit_retained_nets': (reports / 'writecredit_nets.txt').read_text().splitlines(),
        'cnn_actual_synthesis_log': (cnn_runs[0] / 'runme.log').as_posix(),
        'cnn_dcp': cnn_dcps[0].as_posix(), 'cnn_dcp_sha256': sha(cnn_dcps[0]),
        'system_dcp': dcp.as_posix(), 'system_dcp_sha256': sha(dcp),
        'project': (project / (PROJECT_NAME + '.xpr')).as_posix(),
        'original_project_relation': before['old_project_relation'],
        'protected_inputs_after': 'PASS', 'implementation_run': False, 'route_run': False,
        'implementation_scope': implementation_scope,
        'bitstream_generated': False, 'xsa_generated': False,
    }
    write_json(output / 'integration_gate.json', result)
    print('PHASE4G_INTEGRATION_GATE=PASS', flush=True)
    print(json.dumps({'resources': resources, 'pre_route_timing': timing, 'project': result['project']}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-gate', type=Path, default=OUT / 'release_gate.json')
    parser.add_argument('--out', type=Path, default=OUT / 'integration_01')
    parser.add_argument('--stage', choices=('run', 'prepare', 'create', 'synth', 'analyze'), default='run')
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to(OUT.resolve()):
        raise RuntimeError('Integration output must remain within Phase 4G')
    if args.stage in ('run', 'prepare'):
        prepare(output, args.release_gate.resolve())
    if args.stage in ('run', 'create'):
        vivado(output, 'create')
    if args.stage in ('run', 'synth'):
        vivado(output, 'synth')
    if args.stage in ('run', 'analyze'):
        analyze(output)


if __name__ == '__main__':
    main()
