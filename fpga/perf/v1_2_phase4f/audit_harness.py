"""Independently audit the eight-frame harness without launching any simulation.

Before/after reports preserve their own filenames.  The unchanged 5,235-file
recovery audit remains the responsibility of Phase 4E's verify_protection.py.
"""
import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = Path('E:/HLS/kv260_three_module_v1_2_phase4')
BASE = ROOT / 'phase4b_build_02'
PHASE4E = ROOT / 'phase4e_system_02'
CONFIG = dict(FRAMES=8, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2,
              DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128, CLOCK_MHZ=100)
OVERLAYS = {'zero_dce_cnn_top_row_axi_writer.v',
            'zero_dce_cnn_top_row_axi_writer_2.v',
            'zero_dce_cnn_top_p_anonymous_namespace_output_writer.v'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path):
    # Text comparison permits platform line endings; raw SHA checks do not.
    return path.read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def checked_file(path, expected, records):
    path = path.resolve()
    require(path.is_file(), 'Missing protected file: ' + str(path))
    observed = sha(path)
    require(observed == expected, 'Protected SHA mismatch: ' + str(path))
    records[path.as_posix()] = observed


def audit_tb(run, manifest, records):
    checked_file(BASE / 'system_tb.sv', manifest['original_source_manifest']['generated_tb_sha256'], records)
    checked_file(run / 'system_tb.sv', manifest['generated_tb_sha256'], records)
    original = text(BASE / 'system_tb.sv')
    generated = text(run / 'system_tb.sv')
    observer = text(run / 'observer_append.sv')
    require(original.endswith('endmodule\n'), 'Unexpected original TB ending')
    suffix = observer + 'endmodule\n'
    require(generated.endswith(suffix), 'Generated observer differs from saved append')
    records[(run / 'observer_append.sv').resolve().as_posix()] = sha(run / 'observer_append.sv')
    restored = generated[:-len(suffix)] + 'endmodule\n'
    edits = [
        ('if(frames!=8) $fatal(1,"PHASE4F requires FRAMES=8");',
         'if(frames<1 || frames>100) $fatal(1,"FRAMES must be 1..100");'),
        ('            phase4f_stage_drained(m,f);\n            numerical_check(m,f);',
         '            numerical_check(m,f);'),
        ('    phase4f_finish();\n    ddr.print_stats();', '    ddr.print_stats();'),
    ]
    for added, frozen in edits:
        require(restored.count(added) == 1, 'Allowed harness edit missing or duplicated: ' + added)
        require(original.count(frozen) == 1, 'Original anchor missing or duplicated: ' + frozen)
        restored = restored.replace(added, frozen)
    require(restored == original, 'Original TB was changed beyond three allowed edits and observer append')
    require(re.search(r'^`timescale\s+1ns/1ps\s*$', generated, re.M), 'TB timescale is not 1ns/1ps')
    require(generated.count('always #5 ap_clk=~ap_clk;') == 1, 'TB clock is not the original 100 MHz clock')
    require('always @(negedge ap_clk)' in observer, 'Missing passive owner/wait sampling')
    require(not re.search(r'\b(force|release)\b\s+(dut|ddr)\.', observer), 'Observer forces a DUT or DDR signal')
    require(not re.search(r'\b(dut|ddr)\.[\w.\[\]]+\s*(?:<=|=(?!=))', observer), 'Observer writes a DUT or DDR signal')
    require(not re.search(r'\b(wait|repeat)\s*\(', observer), 'Observer inserts a timing wait')
    for owner in ('low_owner', 'input_owner', 'full_owner', 'enh_owner', 'model_owner'):
        require(owner + '[next_frame[t]%2]!=next_frame[t]' in observer,
                'Own CSR reservation is not excluded for ' + owner)
    return dict(status='PASS', original_prefix_restored_exactly=True,
                normalized_text_sha256=hashlib.sha256(restored.encode()).hexdigest(),
                allowed_edits=['scope FRAMES=8 guard', 'stage drain assertion before numerical check',
                               'passive finish before original DDR stats'],
                observer_append_sha256=sha(run / 'observer_append.sv'),
                original_scheduler_numerical_guard_access_irq_unchanged=True,
                own_csr_reservation_excluded_from_buffer_wait=True,
                clock_mhz=100, timescale='1ns/1ps')


def audit_commands(run, records):
    command = text(run / 'simulate.cmd')
    launches = [line for line in command.splitlines() if re.match(r'^call\s+xsim\s', line, re.I)]
    require(len(launches) == 1, 'Expected exactly one XSIM launch')
    launch = launches[0]
    require(launch.startswith('call xsim phase4f_system -tclbatch run.tcl -log system.log '),
            'Unexpected XSIM snapshot or runtime options')
    arguments = re.findall(r'-testplusarg\s+"([^"\r\n]+)"', launch)
    pairs = [value.split('=', 1) for value in arguments]
    require(all(len(pair) == 2 for pair in pairs), 'Invalid plusarg')
    require(len({pair[0] for pair in pairs}) == len(pairs), 'Duplicate runtime plusarg')
    expected = {key: str(value) for key, value in CONFIG.items() if key != 'CLOCK_MHZ'}
    expected['OUTPUT_DIR'] = (run / 'results').as_posix()
    require(dict(pairs) == expected, 'Runtime plusargs differ from fixed Phase 4F configuration')
    require(text(run / 'run.tcl') == 'run all\nquit\n', 'Unexpected TCL continuation or wave commands')
    elaboration = text(run / 'elaborate.cmd')
    require(elaboration.count('call xelab --relax --mt 2 -prj system.prj -f xelab_options.txt '
                              'xil_defaultlib.phase4_system_tb xil_defaultlib.glbl -s phase4f_system -log elaborate.log') == 1,
            'Unexpected simulation compilation command')
    for name in ('simulate.cmd', 'run.tcl', 'elaborate.cmd'):
        records[(run / name).resolve().as_posix()] = sha(run / name)
    return dict(status='PASS', runtime_plusargs=dict(pairs), simulation_runs=1,
                continuation='natural run all; quit', no_extra_wave_or_debug_options=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--phase', choices=('before', 'after'))
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--protection-audit', type=Path,
                        help='Optional current output from the existing verify_protection.py tool')
    args = parser.parse_args()
    run = args.run.resolve()
    name = 'harness_audit_' + args.phase + '.json' if args.phase else 'harness_audit.json'
    output = run / name
    require(args.overwrite or not output.exists(), 'Audit output exists; use --overwrite explicitly')
    manifest_path = run / 'run_manifest.json'
    manifest = json.loads(text(manifest_path))
    frozen = json.loads(text(BASE / 'source_manifest.json'))
    prior = json.loads(text(PHASE4E / 'run_manifest.json'))
    require(manifest['reference'] == BASE.as_posix(), 'Unexpected base reference')
    require(manifest['phase4e_reference'] == PHASE4E.as_posix(), 'Unexpected overlay reference')
    require(manifest['config'] == CONFIG, 'Manifest configuration differs from Phase 4F')
    require(manifest['original_source_manifest'] == frozen, 'Original source manifest was changed')
    require(manifest['substitutions'] == prior['substitutions'], 'Overlays differ from validated Phase 4E')
    require(len(frozen['source_files']) == 363, 'Expected 363 frozen sources')
    require(len(manifest['substitutions']) == 3, 'Expected exactly three writer substitutions')
    records = {}
    for item in frozen['source_files']:
        checked_file(Path(item['path']), item['sha256'], records)
    require({Path(item['candidate']).name for item in manifest['substitutions']} == OVERLAYS,
            'A non-writer file is substituted')
    for item in manifest['substitutions']:
        checked_file(Path(item['original']), item['original_sha256'], records)
        checked_file(Path(item['candidate']), item['candidate_sha256'], records)
    expected_copies = {p.name for p in BASE.iterdir() if p.is_file() and
                       (p.suffix in ('.hex', '.dat') or p.name in
                        ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt'))}
    require(len(expected_copies) == 16, 'Expected 16 frozen copy files')
    require(set(manifest['protected_copies']) == expected_copies, 'Protected-copy manifest differs from base')
    for name, digest in manifest['protected_copies'].items():
        checked_file(BASE / name, digest, records)
        checked_file(run / name, digest, records)
    for name, key in (('shared_axi_ddr.sv', 'ddr_model_sha256'), ('phase4_pl.v', 'pl_wrapper_sha256')):
        checked_file(BASE / name, frozen[key], records)
        checked_file(run / name, frozen[key], records)
    checked_file(REPO / 'fpga/perf/v1_2_phase4b/shared_axi_ddr_v2.sv', frozen['ddr_model_sha256'], records)
    expected_project = text(BASE / 'system.prj').replace(BASE.as_posix(), run.as_posix())
    for item in manifest['substitutions']:
        old = '"' + item['original'] + '"'
        require(expected_project.count(old) == 1, 'Unexpected writer occurrence in project')
        expected_project = expected_project.replace(old, '"' + item['candidate'] + '"')
    require(text(run / 'system.prj') == expected_project, 'Project source list changed beyond three writer overlays')
    for path in (manifest_path, BASE / 'source_manifest.json', run / 'system.prj'):
        records[path.resolve().as_posix()] = sha(path)
    tb_result = audit_tb(run, manifest, records)
    commands = audit_commands(run, records)
    recovery_path = ROOT / 'recovery_manifest.json'
    recovery = json.loads(text(recovery_path))
    require(len(recovery['files']) == 5235, 'Unexpected original recovery file count')
    protection_tool = REPO / 'fpga/perf/v1_2_phase4e/verify_protection.py'
    recovery_result = dict(status='DELEGATED_TO_EXISTING_TOOL', original_protected_files=5235,
                           recovery_manifest=recovery_path.as_posix(), recovery_manifest_sha256=sha(recovery_path),
                           tool=protection_tool.as_posix(), tool_sha256=sha(protection_tool),
                           current_5235_hash_check_performed_by_this_script=False)
    if args.protection_audit:
        protection = args.protection_audit.resolve()
        evidence = json.loads(text(protection))
        require(evidence['status'] == 'PASS' and evidence['original_protected_files'] == 5235 and
                evidence['original_changed'] == [], 'Referenced full protection audit is not PASS')
        recovery_result.update(status='REFERENCED_PASS', evidence=protection.as_posix(),
                               evidence_sha256=sha(protection))
    before_after = 'NOT_REQUESTED'
    if args.phase == 'after':
        before_path = run / 'harness_audit_before.json'
        require(before_path.is_file(), 'After audit requires a before audit')
        before = json.loads(text(before_path))
        require(before['status'] == 'PASS' and before['run'] == run.as_posix(), 'Before audit is invalid')
        require(before['checked_file_sha256'] == records, 'Protected or harness files changed since before audit')
        require(before['original_recovery']['recovery_manifest_sha256'] == sha(recovery_path),
                'Original recovery manifest changed since before audit')
        before_after = 'PASS'
    result = dict(status='PASS', phase=args.phase or 'single', run=run.as_posix(),
                  checked_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  original_sources=dict(status='PASS', count=363), writer_overlays=dict(status='PASS', count=3),
                  protected_copies=dict(status='PASS', count=16), ddr_model_unchanged='PASS',
                  pl_wrapper_unchanged='PASS', generated_tb_hash='PASS', source_project='PASS',
                  harness=tb_result, commands=commands, before_after_hash_identity=before_after,
                  original_recovery=recovery_result, checked_file_sha256=records,
                  audit_script_sha256=sha(Path(__file__).resolve()))
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], output=output.as_posix(), phase=result['phase'],
                          original_sources=363, writer_overlays=3, protected_copies=16,
                          original_tb_restored=True, fixed_configuration=CONFIG,
                          recovery_audit=recovery_result['status'],
                          before_after_hash_identity=before_after)))


if __name__ == '__main__':
    main()
