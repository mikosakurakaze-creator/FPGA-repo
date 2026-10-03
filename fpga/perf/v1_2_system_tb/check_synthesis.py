"""Validate the independent whole-system synthesis gate before any RTL TB."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')


def main():
    base = ROOT / 'fpga/vivado'
    def design(version):
        name = 'three_module_integration_' + version
        return json.loads((base / name / (name + '.srcs/sources_1/bd/system/system.bd')).read_text())['design']
    old, new = design('v1_1'), design('v1_2')
    assert old['nets'] == new['nets'] and old['interface_nets'] == new['interface_nets']
    assert old['addressing'] == new['addressing']
    assert old['design_tree'] == new['design_tree']
    for name, cell in old['components'].items():
        fresh = new['components'][name]
        assert cell['vlnv'] == fresh['vlnv']
        for key, value in cell.get('parameters', {}).items():
            assert fresh.get('parameters', {}).get(key) == value, (name, key)
        if name not in ('zero_dce_cnn_top_0', 'zynq_ultra_ps_e_0'):
            assert cell == fresh, ('Stable component differs', name)
    log = (RUN / 'synth_console.log').read_text(errors='replace')
    for marker in ('PREFLIGHT_TOPOLOGY=PASS', 'VALIDATE=PASS', 'OUTPUT_PRODUCTS=PASS',
                   'WRAPPER=PASS', 'SYNTH=PASS', 'POST_SYNTHESIS_REPORTS=PASS'):
        assert marker in log, marker
    assert 'ERROR:' not in log
    report_dir = RUN / 'synthesis'
    utilization = (report_dir / 'system_utilization.rpt').read_text()
    def used(name):
        return int(re.search(r'\|\s*' + re.escape(name) + r'\s*\|\s*(\d+)', utilization)[1])
    resources = dict(LUT=used('CLB LUTs*'), FF=used('CLB Registers'),
                     RAMB36=used('RAMB36/FIFO*'), RAMB18=used('RAMB18'),
                     URAM=used('URAM'), DSP=used('DSPs'))
    resources['BRAM18_equivalent'] = 2 * resources['RAMB36'] + resources['RAMB18']
    limits = dict(LUT=117120, FF=234240, BRAM18_equivalent=288, URAM=64, DSP=1248)
    assert all(resources[name] <= n for name, n in limits.items())
    timing = (report_dir / 'system_timing_summary.rpt').read_text()
    row = re.search(r'\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s*\n', timing)
    assert row
    timing_result = dict(WNS_ns=float(row[1]), TNS_ns=float(row[2]), setup_failing_endpoints=int(row[3]),
                         WHS_ns=float(row[5]), THS_ns=float(row[6]), hold_failing_endpoints=int(row[7]),
                         WPWS_ns=float(row[9]), TPWS_ns=float(row[10]))
    assert timing_result['WNS_ns'] >= 0 and timing_result['TNS_ns'] == 0
    # Pre-placement short-path hold estimates are recorded, not called clean.
    assert timing_result['WHS_ns'] >= -.1
    drc = (report_dir / 'system_drc.rpt').read_text()
    assert '| Error ' not in drc and '| Critical Warning ' not in drc
    checkpoint = base / 'three_module_integration_v1_2/three_module_integration_v1_2.runs/synth_1/system_wrapper.dcp'
    assert checkpoint.is_file()
    result = dict(synthesis_gate='PASS', bd_validate='PASS', topology_and_address_map_unchanged=True,
                  resources=resources, limits=limits, timing=timing_result,
                  hold_note='Unplaced netlist hold is not clean; implementation must repair and recheck after system TB passes.',
                  checkpoint=str(checkpoint), checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  ps_existing_parameters_unchanged=True,
                  new_automatic_ps_parameter_keys=sorted(set(new['components']['zynq_ultra_ps_e_0']['parameters']) -
                                                         set(old['components']['zynq_ultra_ps_e_0']['parameters'])))
    (RUN / 'synthesis_evidence.json').write_text(json.dumps(result, indent=2))
    (RUN / 'synthesis_gate.txt').write_text('PASS\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
