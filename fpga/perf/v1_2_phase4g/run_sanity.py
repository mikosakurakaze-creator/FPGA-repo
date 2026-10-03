"""Run only bounded writer probes or one CNN frame from a packaged-IP snapshot."""
import argparse
import csv
import datetime
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from prepare_sanity import batch_prefix
from sanity_sources import CONFIG, REFERENCE_PROBE, compile_gate, legacy, reverify, sha, verify_list


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def execute(run, command, logfile, statefile, progress=None):
    assert not (run / statefile).exists() and not (run / logfile).exists(), 'refuse repeated execution'
    state = dict(status='RUNNING', started=now(), command=[str(x) for x in command])
    environment = os.environ.copy()
    environment.setdefault('PROCESSOR_ARCHITECTURE', 'AMD64')
    with (run / logfile).open('w') as output:
        process = subprocess.Popen(command, cwd=run, stdout=output, stderr=subprocess.STDOUT,
                                   env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        state['pid'] = process.pid
        (run / statefile).write_text(json.dumps(state, indent=2))
        print('STARTED', run.name, process.pid, flush=True)
        previous = ''
        while process.poll() is None:
            if progress is not None and progress.exists():
                lines = progress.read_text().splitlines()
                latest = lines[-1].split(',')[0] if len(lines) > 1 else ''
                if latest and latest != previous:
                    print('PROGRESS_CYCLE', latest, flush=True)
                    previous = latest
            time.sleep(10)
    state.update(status='TERMINAL', finished=now(), exit_code=process.returncode)
    (run / statefile).write_text(json.dumps(state, indent=2))
    print('TERMINAL', run.name, process.returncode, flush=True)
    assert process.returncode == 0, (run, process.returncode)
    return state


def check_sources(run, manifest):
    reverify(manifest['package_source_gate'])
    verify_list(manifest['compile_order'])
    assert sha(run / ('writer_probe.sv' if 'reference_helper_sha256' in manifest else 'system_tb.sv')) == manifest['generated_tb_sha256']
    paths = [Path(x['path']) for x in manifest['compile_order']]
    assert compile_gate(paths, manifest['package_source_gate']) == manifest['compile_order']


def writer(run, manifest):
    helper = legacy('run_writer_probe')
    assert sha(Path(helper.__file__)) == manifest['reference_helper_sha256']
    assert sha(helper.DDR) == manifest['ddr_sha256']
    assert not (run / 'comparison.json').exists()
    check_sources(run, manifest)
    execute(run, ['cmd', '/c', str(run / 'build.cmd')], 'build_console.log', 'build_exit_status.json')
    assert (run / 'xsim.dir/writer_probe/xsimk.exe').is_file()
    kernel = sha(run / 'xsim.dir/writer_probe/xsimk.exe')
    reference = json.loads((REFERENCE_PROBE / 'comparison.json').read_text())
    assert reference['complete'] is True and reference['ddr_sha256'] == manifest['ddr_sha256']
    comparison = {}
    for block, channels in [(1, 2), (7, 3)]:
        for residue in [0, 4090]:
            name = f'b{block}_r{residue}'
            scenario = run / name
            scenario.mkdir(exist_ok=False)
            mask = helper.memories(scenario, channels, residue)
            for filename in ['shared_ddr.hex', 'expected.hex']:
                shutil.copy2(scenario / filename, run / filename)
            plusargs = [f'BLOCK={block}', f'CHANNELS={channels}', f'RESIDUE={residue}',
                        'READ_OUTSTANDING=2', 'WRITE_OUTSTANDING=2', 'DDR_DELAY=16', 'SERVICE_PERIOD=1']
            command_file = run / f'run_{name}.cmd'
            command_file.write_text(batch_prefix(run) + 'call xsim writer_probe -tclbatch run.tcl -log xsim_run.log ' +
                                    ' '.join('-testplusarg "' + p + '"' for p in plusargs) + '\nexit /b %errorlevel%\n')
            execute(run, ['cmd', '/c', str(command_file)], f'{name}_console.log', f'{name}_exit_status.json')
            shutil.copy2(run / f'{name}_console.log', scenario / 'run.log')
            for filename in ['timeline.csv', 'actual.hex', 'xsim_run.log']:
                shutil.copy2(run / filename, scenario / filename)
            result = helper.analyze(scenario, mask)
            old = helper.analyze(REFERENCE_PROBE / 'new' / name, mask)
            assert result == old, ('packaged writer differs from verified overlay', name)
            assert result['row_credit_peak'] == 2 and result['final_credit'] == 0 and result['actual_data_overlap_rows'] > 0
            public = {k: v for k, v in result.items() if k != 'footprint'}
            (scenario / 'evidence.json').write_text(json.dumps(public, indent=2))
            reference_scenario = reference['scenarios'][name]
            assert result['total_writer_cycles'] == reference_scenario['new_cycles']
            comparison[name] = dict(new_cycles=result['total_writer_cycles'], reference_cycles=reference_scenario['new_cycles'],
                                    row_credit_peak=2, final_credit=0, numerical_and_protocol_pass=True,
                                    external_footprint_data_strobes_identical=True,
                                    actual_data_overlap_rows=result['actual_data_overlap_rows'],
                                    raw_mismatch=0, guard=0, physical_aw=result['physical_aw'],
                                    physical_wlast=result['physical_wlast'], physical_b=result['physical_b'],
                                    exact_phase4e_evidence_match=True,
                                    reference_evidence_sha256=sha(REFERENCE_PROBE / 'new' / name / 'evidence.json'),
                                    timeline_sha256=sha(scenario / 'timeline.csv'), evidence_sha256=sha(scenario / 'evidence.json'))
            print('PACKAGED_WRITER_SCENARIO_PASS', name, result['total_writer_cycles'], flush=True)
    check_sources(run, manifest)
    assert sha(run / 'xsim.dir/writer_probe/xsimk.exe') == kernel
    result = dict(status='PACKAGED_WRITER_LOCAL_PROBE_PASS', complete=True, simulator='xsim',
                  ddr_delay=16, write_outstanding=2, ddr_sha256=manifest['ddr_sha256'],
                  scenarios=comparison, source_manifest_reverified_after_runs=True,
                  package_source_gate=manifest['package_source_gate'],
                  kernel_sha256=kernel, run_manifest_sha256=sha(run / 'run_manifest.json'),
                  reference_comparison_sha256=sha(REFERENCE_PROBE / 'comparison.json'))
    (run / 'comparison.json').write_text(json.dumps(result, indent=2))
    public_gate = dict(status='PASS', kind='writer_local_rtl_probe',
                       evidence=(run / 'comparison.json').as_posix(), evidence_sha256=sha(run / 'comparison.json'),
                       packaged_ip_root=manifest['package_source_gate']['ip_root'],
                       package_source_gate=manifest['package_source_gate'],
                       compile_order=manifest['compile_order'], scenarios=comparison,
                       build_exit=json.loads((run / 'build_exit_status.json').read_text()),
                       scenario_exits={n: json.loads((run / (n + '_exit_status.json')).read_text()) for n in comparison},
                       guard=0, raw_mismatch=0, final_credit=0, exact_phase4e_evidence_match=True)
    (run / 'writer_probe_gate.json').write_text(json.dumps(public_gate, indent=2))
    print('PACKAGED_WRITER_LOCAL_PROBE_PASS', flush=True)


def cnn(run, manifest, local_evidence):
    assert manifest['config'] == CONFIG
    assert local_evidence is not None and local_evidence.is_file()
    local = json.loads(local_evidence.read_text())
    assert local['status'] == 'PACKAGED_WRITER_LOCAL_PROBE_PASS' and local['complete'] is True
    assert local['package_source_gate'] == manifest['package_source_gate']
    assert len(local['scenarios']) == 4
    for scenario in local['scenarios'].values():
        assert scenario['exact_phase4e_evidence_match'] and scenario['numerical_and_protocol_pass']
    search = manifest['source_search_audit']
    assert search['status'] == 'PASS' and search['no_old_cnn_include_dir'] and search['no_old_module_search_dir']
    assert sha(run / 'header_include_audit.json') == manifest['source_search_audit_sha256']
    assert sha(search['original_options_path']) == search['original_options_sha256']
    assert sha(run / 'xelab_options.txt') == search['generated_options_sha256']
    verify_list(search['header_sources'])
    check_sources(run, manifest)
    verify_list(manifest['original_source_manifest']['source_files'])
    for name, digest in manifest['protected_copies'].items():
        assert sha(run / name) == digest
    execute(run, ['cmd', '/c', str(run / 'elaborate.cmd')], 'elaborate_console.log', 'elaborate_exit_status.json')
    kernel = run / 'xsim.dir/phase4e_system/xsimk.exe'
    assert kernel.is_file() and 'Built simulation snapshot phase4e_system' in (run / 'elaborate.log').read_text()
    state = execute(run, ['cmd', '/c', str(run / 'simulate.cmd')], 'console.log', 'exit_status.json', run / 'results/write_stats.csv')
    state.update(local_gate_approved=True, local_evidence=local_evidence.resolve().as_posix(),
                 local_evidence_sha256=sha(local_evidence), kernel_sha256=sha(kernel),
                 packaged_ip_root=manifest['package_source_gate']['ip_root'])
    (run / 'exit_status.json').write_text(json.dumps(state, indent=2))
    check_sources(run, manifest)
    print('PACKAGED_SINGLE_CNN_NATURAL_EXIT', state['exit_code'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', required=True, choices=['writer', 'cnn'])
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--local-evidence', type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    manifest = json.loads((run / 'run_manifest.json').read_text())
    if args.kind == 'writer':
        writer(run, manifest)
    else:
        cnn(run, manifest, args.local_evidence)


if __name__ == '__main__':
    main()
