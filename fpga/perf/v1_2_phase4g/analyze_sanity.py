"""Require exact Phase 4E CNN behavior and released-package source identity."""
import argparse
import json
import sys
from pathlib import Path

from sanity_sources import BASE, CONFIG, REFERENCE_SYSTEM, REPO, compile_gate, legacy, reverify, sha, verify_list


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    assert not (run / 'analysis.json').exists()
    manifest = json.loads((run / 'run_manifest.json').read_text())
    assert manifest['config'] == CONFIG
    reverify(manifest['package_source_gate'])
    verify_list(manifest['compile_order'])
    assert compile_gate([x['path'] for x in manifest['compile_order']], manifest['package_source_gate']) == manifest['compile_order']
    search = manifest['source_search_audit']
    assert search['status'] == 'PASS' and search['no_old_cnn_include_dir'] and search['no_old_module_search_dir']
    assert sha(run / 'header_include_audit.json') == manifest['source_search_audit_sha256']
    assert sha(search['original_options_path']) == search['original_options_sha256']
    assert sha(run / 'xelab_options.txt') == search['generated_options_sha256']
    verify_list(search['header_sources'])
    # Invoke the unchanged independent Phase4E analyzer, preserving its report.
    sys.path.insert(0, str(REPO / 'fpga/perf/v1_2_phase4e'))
    helper = legacy('analyze_system')
    sys.argv = [str(helper.__file__), '--run', str(run)]
    helper.main()
    result = json.loads((run / 'analysis.json').read_text())
    (run / 'analysis.json').rename(run / 'phase4e_analysis.json')
    reference = json.loads((REFERENCE_SYSTEM / 'analysis.json').read_text())
    for key in ('new_cycles', 'numerical', 'runtime_config_verified', 'hp_stats', 'final', 'buses', 'blocks', 'functions', 'writer_barriers'):
        assert result[key] == reference[key], ('packaged CNN differs from Phase4E', key)
    assert result['new_cycles'] == 3301639
    assert result['numerical'] == dict(a_low_checked=19080, raw_mismatch=0, guard=0, hazard=0)
    text = (run / 'system.log').read_text()
    drained = helper.records(text, 'PHASE4G_ALL_RESPONSES_DRAIN')
    assert drained == [dict(HP=h, RC=0, WC=0, WP=0, RVALID=0, BVALID=0) for h in range(4)]
    # Recover the original TB body by removing only the CNN finish hook and the
    # independently saved passive observer. This checks the original BFM/math.
    tb = (run / 'system_tb.sv').read_text()
    append = (run / 'observer_append.sv').read_text()
    assert tb.endswith(append + 'endmodule\n')
    prefix = tb[:-len(append + 'endmodule\n')]
    prefix = prefix.replace('\n            if(m==0) phase4g_finish();', '') + 'endmodule\n'
    assert prefix == (BASE / 'system_tb.sv').read_text(), 'original BFM changed'
    result.update(conclusion='PACKAGED_CNN_IP_SANITY_PASS', packaged_ip_source_verified=True,
                  phase4e_exact_behavior_match=True, all_hp_responses_drained=drained,
                  original_bfm_body_unchanged=True,
                  cnn_compiled_sources=manifest['package_source_gate']['rtl_count'],
                  changed_rtl_count=len(manifest['substitutions']), writer_shadow_copies=0,
                  package_source_gate=manifest['package_source_gate'],
                  source_search_audit=search,
                  reference_analysis_sha256=sha(REFERENCE_SYSTEM / 'analysis.json'),
                  reused_analyzer_sha256=sha(Path(helper.__file__)),
                  phase4e_analysis_sha256=sha(run / 'phase4e_analysis.json'),
                  scope='Four writer scenarios plus one CNN-only frame; no Bilinear/Curve launches or multi-frame run.')
    (run / 'analysis.json').write_text(json.dumps(result, indent=2))
    public_gate = dict(status='PASS', kind='cnn_single_frame', evidence=(run / 'analysis.json').as_posix(),
                       evidence_sha256=sha(run / 'analysis.json'),
                       packaged_ip_root=manifest['package_source_gate']['ip_root'],
                       package_source_gate=manifest['package_source_gate'], compile_order=manifest['compile_order'],
                       source_search_audit=search,
                       runtime_config=manifest['config'], cnn_cycles=result['new_cycles'],
                       numerical=result['numerical'], exact_phase4e_behavior_match=True,
                       all_hp_responses_drained=drained, blocks=result['blocks'], final=result['final'], buses=result['buses'],
                       elaborate_exit=json.loads((run / 'elaborate_exit_status.json').read_text()),
                       simulation_exit=json.loads((run / 'exit_status.json').read_text()),
                       reference_analysis_sha256=result['reference_analysis_sha256'], original_bfm_body_unchanged=True)
    (run / 'cnn_single_gate.json').write_text(json.dumps(public_gate, indent=2))
    print(json.dumps({k: result[k] for k in ('conclusion', 'new_cycles', 'numerical', 'phase4e_exact_behavior_match', 'cnn_compiled_sources', 'writer_shadow_copies', 'all_hp_responses_drained')}))


if __name__ == '__main__':
    main()
