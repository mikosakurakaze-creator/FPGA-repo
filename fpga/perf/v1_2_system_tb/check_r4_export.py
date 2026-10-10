"""Verify freshly exported r4 IP against the frozen V1.1 external ABI."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')
OLD = Path('E:/HLS/kv260_three_module_v1_1_ip_repo/cnn_72b2113_k26_10ns')
NS = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009',
      'x': 'http://www.xilinx.com'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def abi(path):
    r = ET.parse(path / 'component.xml').getroot()
    params = {p.findtext('s:name', namespaces=NS): p.findtext('s:value', namespaces=NS)
              for p in r.findall('s:model/s:modelParameters/s:modelParameter', NS)}
    ports = {}
    for p in r.findall('s:model/s:ports/s:port', NS):
        name = p.findtext('s:name', namespaces=NS)
        v = p.find('s:wire/s:vector', NS)
        ports[name] = dict(direction=p.findtext('s:wire/s:direction', namespaces=NS),
                           left=v.findtext('s:left', namespaces=NS) if v is not None else None,
                           right=v.findtext('s:right', namespaces=NS) if v is not None else None)
    bus = {}
    for b in r.findall('s:busInterfaces/s:busInterface', NS):
        name = b.findtext('s:name', namespaces=NS)
        bus[name] = dict(mode='master' if b.find('s:master', NS) is not None else
                             'slave' if b.find('s:slave', NS) is not None else 'other',
                         ports={p.findtext('s:logicalPort/s:name', namespaces=NS):
                                p.findtext('s:physicalPort/s:name', namespaces=NS)
                                for p in b.findall('s:portMaps/s:portMap', NS)})
    widths = {k: v for k, v in params.items() if k.endswith(('DATA_WIDTH', 'ADDR_WIDTH', 'ID_WIDTH'))}
    return dict(ports=ports, bus_interfaces=bus, width_parameters=widths)


def main():
    component = RUN / 'cnn_r4_export'
    fresh = component / 'hls/impl/ip'
    csim = (component / 'hls/csim/report/zero_dce_cnn_top_csim.log').read_text()
    assert '19080 scalars, mismatches=0' in csim and 'CSim done with 0 errors' in csim
    assert sha(RUN / 'data/cnn_csim_actual_a_low_q14.bin') == sha(RUN / 'data/expected_a_low_q14.bin')
    synth = ET.parse(component / 'hls/syn/report/zero_dce_cnn_top_csynth.xml').getroot()
    assert synth.findtext('UserAssignments/Part') == 'xck26-sfvc784-2LV-c'
    assert float(synth.findtext('UserAssignments/TargetClockPeriod')) == 10
    assert float(synth.findtext('.//EstimatedClockPeriod')) <= 10
    log = (RUN / 'r4_export.log').read_text(errors='replace')
    assert 'ERROR:' not in log
    assert 'Exporting RTL as a Vivado IP' in log and 'Generated output file' in log
    package = component / 'zero_dce_cnn_top.zip'
    assert package.is_file() and package.stat().st_size > 0
    old_abi, new_abi = abi(OLD), abi(fresh)
    if old_abi != new_abi:
        (RUN / 'abi_mismatch.json').write_text(json.dumps(dict(old=old_abi, fresh=new_abi), indent=2))
        raise RuntimeError('Frozen V1.1 external ABI differs: stop integration, do not adapt interfaces')
    headers = [next(d.glob('drivers/**/xzero_dce_cnn_top_hw.h')) for d in (OLD, fresh)]
    assert sha(headers[0]) == sha(headers[1]) == '3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362'
    expected_bundles = {'m_axi_' + n for n in ('gmem_input', 'gmem8', 'gmem32', 'gmem_lut', 'gmem_output', 'gmem_workspace')}
    assert {n for n in new_abi['bus_interfaces'] if n.startswith('m_axi_')} == expected_bundles
    assert all(n in new_abi['ports'] for n in ('ap_clk', 'ap_rst_n', 'interrupt'))
    rtl = (fresh / 'hdl/verilog/zero_dce_cnn_top.v').read_text()
    widths = re.findall(r'C_M_AXI_(\w+)_DATA_WIDTH\s*=\s*(\d+)', rtl)
    assert len(widths) == 6 and all(int(n) == 32 for _, n in widths)
    dest = RUN / 'ip_repo/cnn_r4'
    shutil.copytree(fresh, dest)
    root = ET.parse(fresh / 'component.xml').getroot()
    revision = root.findtext('s:vendorExtensions/x:coreExtensions/x:coreRevision', namespaces=NS)
    assert revision is not None
    seed = RUN / 'system_seed.bd'
    bd = json.loads(seed.read_text())
    # The only changed cell metadata is CNN's actual newly exported revision.
    bd['design']['components']['zero_dce_cnn_top_0']['ip_revision'] = revision
    seed.write_text(json.dumps(bd, indent=2))
    result = dict(csim='PASS', synthesis='PASS', ip_export='PASS', frozen_external_abi='PASS',
                  driver_sha256=sha(headers[1]), export_zip_sha256=sha(package),
                  ip_repository=str(dest), core_revision=revision, abi=new_abi,
                  resources={n.tag: int(n.text) for n in synth.findall('AreaEstimates/Resources/*')})
    (RUN / 'r4_export_evidence.json').write_text(json.dumps(result, indent=2))
    (RUN / 'r4_export_gate.txt').write_text('PASS\n')
    print('Fresh r4 CSim / synthesis / IP export and frozen external ABI PASS.')


if __name__ == '__main__':
    main()
