"""Publish an integration gate only after all packaged-IP evidence passes."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True, type=Path)
    parser.add_argument('--package-audit', required=True, type=Path)
    parser.add_argument('--rebuild', required=True, type=Path)
    parser.add_argument('--writer-probe', required=True, type=Path)
    parser.add_argument('--cnn-single', required=True, type=Path)
    parser.add_argument('--ooc', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'Refusing to overwrite release gate')
    ip = args.ip.resolve()
    audit = read(args.package_audit)
    require(audit['status'] == 'PASS', 'Independent package audit failed')
    require(Path(audit['primary']['ip']).resolve() == ip, 'Audited package differs')
    for name, expected in audit['primary']['files'].items():
        require(sha(ip / name) == expected, 'Audited package changed: ' + name)
    rebuild = read(args.rebuild)
    require(rebuild['status'] == 'PASS' and Path(rebuild['primary']).resolve() == ip,
            'Deterministic rebuild does not cover formal package')
    require(rebuild['component_xml_byte_equal'] and rebuild['source_manifest_byte_equal'] and
            rebuild['driver_byte_equal'] and rebuild['all_rtl_byte_equal'], 'Rebuild comparisons incomplete')
    manifest = read(ip / 'build_manifest.json')
    require(manifest['status'] == 'PACKAGED_IP_GATE_PASS', 'Build has not passed')
    require(manifest['identity_sha256'] == rebuild['identity_sha256'], 'Rebuild identity differs')
    for gate_path in (args.writer_probe, args.cnn_single):
        gate = read(gate_path)
        require(gate['status'] == 'PASS' and Path(gate['packaged_ip_root']).resolve() == ip,
                'Sanity gate does not cover formal package')
        require(gate['package_source_gate']['component_sha256'] == sha(ip / 'component.xml'),
                'Sanity component differs')
        for kind, entries in gate['package_source_gate']['filesets'].items():
            for item in entries:
                require(sha(Path(item['path'])) == item['sha256'], 'Sanity source changed')
        require(sha(Path(gate['evidence'])) == gate['evidence_sha256'], 'Sanity evidence changed')
    writer = read(args.writer_probe)
    require(writer['build_exit']['exit_code'] == 0 and len(writer['scenarios']) == 4, 'Local probe incomplete')
    require(set(writer['scenarios']) == {'b1_r0', 'b1_r4090', 'b7_r0', 'b7_r4090'}, 'Local probe scenarios differ')
    for name, result in writer['scenarios'].items():
        require(writer['scenario_exits'][name]['exit_code'] == 0 and
                result['numerical_and_protocol_pass'] and result['exact_phase4e_evidence_match'] and
                result['external_footprint_data_strobes_identical'] and result['raw_mismatch'] == 0 and
                result['guard'] == 0 and result['final_credit'] == 0 and result['row_credit_peak'] == 2 and
                result['physical_aw'] == result['physical_wlast'] == result['physical_b'] and
                result['actual_data_overlap_rows'] > 0, 'Writer scenario gate failed: ' + name)
    cnn_gate = read(args.cnn_single)
    cnn = read(Path(cnn_gate['evidence']))
    header_audit_path = args.cnn_single.parent / 'header_include_audit.json'
    headers = read(header_audit_path)
    require(headers['status'] == 'PASS' and headers['no_old_cnn_include_dir'] and
            headers['no_old_module_search_dir'] and headers['all_other_options_byte_identical'],
            'CNN include/module search audit failed')
    require(headers['shared_hdl_composition'] == dict(verilog=139, verilog_headers=2, memory_initialization=9),
            'Shared HDL source composition differs')
    require(sha(args.cnn_single.parent / 'xelab_options.txt') == headers['generated_options_sha256'] and
            sha(Path(headers['original_options_path'])) == headers['original_options_sha256'], 'XSIM options changed')
    require(len(headers['header_sources']) == 2, 'Formal header audit incomplete')
    for item in headers['header_sources']:
        require(Path(item['path']).resolve() == Path(item['resolved_include']).resolve() == (ip / item['relative']).resolve()
                and sha(Path(item['path'])) == item['sha256'], 'Header resolved outside the formal package')
    exit_state = read(args.cnn_single.parent / 'exit_status.json')
    require(exit_state['status'] == 'TERMINAL' and exit_state['exit_code'] == 0, 'CNN did not naturally finish')
    require(cnn['conclusion'] == 'PACKAGED_CNN_IP_SANITY_PASS' and cnn['new_cycles'] == 3301639,
            'CNN single-frame behavior differs')
    require(cnn['numerical'] == dict(a_low_checked=19080, raw_mismatch=0, guard=0, hazard=0), 'CNN numerical gate failed')
    require(cnn['runtime_config_verified'] == dict(FRAMES=1, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2,
            DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128), 'CNN runtime configuration differs')
    require(cnn['final']['GROUP_DRAINS'] == cnn['final']['WRITER_DRAINS'] == 7 and
            cnn['final']['CREDIT_FINAL_WS'] == cnn['final']['CREDIT_FINAL_OUT'] == 0, 'CNN block drain incomplete')
    require(cnn['all_hp_responses_drained'] == [dict(HP=h, RC=0, WC=0, WP=0, RVALID=0, BVALID=0) for h in range(4)],
            'CNN final response drain incomplete')
    ooc = read(args.ooc)
    require(ooc['status'] == 'PASS' and ooc['actual_exit'] == 0 and
            ooc['clock_mhz'] == 100 and ooc['top'] == 'zero_dce_cnn_top' and
            ooc['part'] == 'xck26-sfvc784-2LV-c' and ooc['implementation_run'] is False,
            'Actual OOC synthesis gate failed')
    require(ooc['metrics']['clock_period_ns'] == 10 and
            ooc['metrics']['setup_estimate_slack_ns'] >= 0, '100MHz OOC setup estimate failed')
    require(ooc['patched_rtl'] == manifest['identity']['patched_rtl'], 'OOC patched RTL differs')
    for item in ooc['source_inputs']:
        require(sha(ip / item['path']) == item['sha256'], 'OOC source differs from package')
    wanted = {(ip / item['path']).resolve() for item in ooc['source_inputs'] if item['path'].endswith('.v')}
    actual = {Path(line).resolve() for line in (args.ooc.parent / 'actual_compile_order.txt').read_text().splitlines()
              if Path(line).suffix == '.v'}
    require(wanted == actual, 'OOC actual compile list has missing or shadow RTL')
    for name in manifest['identity']['patched_rtl']:
        module = Path(name).stem
        require(any(cell['ref_name'] == module or cell['ref_name'].endswith('_' + module)
                    for cell in ooc['hierarchy']), 'OOC actual writer hierarchy missing: ' + module)
    require(ooc['credit_nets'] and any('credit_count' in name for name in ooc['credit_nets']),
            'OOC credit state missing')
    require(sha(args.ooc.parent / 'cnn_writecredit_ooc.dcp') == ooc['checkpoint_sha256'], 'OOC checkpoint changed')
    paths = dict(abi=args.package_audit, filesets=args.package_audit, rebuild=args.rebuild,
                 writer_probe=args.writer_probe, cnn_single=args.cnn_single, ooc_synthesis=args.ooc,
                 header_include_audit=header_audit_path)
    result = dict(status='PASS', checks={key: 'PASS' for key in paths},
                  formal_ip_path=ip.as_posix(), formal_manifest_path=(ip / 'build_manifest.json').as_posix(),
                  formal_manifest_sha256=sha(ip / 'build_manifest.json'),
                  evidence={key: value.resolve().as_posix() for key, value in paths.items()},
                  evidence_sha256={key: sha(value) for key, value in paths.items()},
                  issued_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  scope='Authorize only fresh V1.2 catalog/BD/output products/synthesis; implementation/route/export excluded.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS', gate=args.output.as_posix(), checks=result['checks'])))


if __name__ == '__main__':
    main()
