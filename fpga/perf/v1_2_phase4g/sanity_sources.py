"""Read-only gates for using the released package as the Phase 4G DUT."""
import hashlib
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[3]
ROOT = Path('E:/HLS/kv260_three_module_v1_2_phase4')
BASE = ROOT / 'phase4b_build_02'
REFERENCE_PROBE = ROOT / 'phase4e_writer_probe_03'
REFERENCE_SYSTEM = ROOT / 'phase4e_system_02'
NAMES = ('zero_dce_cnn_top_row_axi_writer.v',
         'zero_dce_cnn_top_row_axi_writer_2.v',
         'zero_dce_cnn_top_p_anonymous_namespace_output_writer.v')
CONFIG = dict(FRAMES=1, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2,
              DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128)
NS = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def legacy(name):
    path = REPO / 'fpga/perf/v1_2_phase4e' / (name + '.py')
    spec = importlib.util.spec_from_file_location('phase4e_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_gate(ip_root):
    """Resolve both filesets and reject ambiguous or stale CNN source copies."""
    root = Path(ip_root).resolve()
    component = root / 'component.xml'
    assert (root / 'build_manifest.json').is_file() and (root / 'source_manifest.json').is_file(), 'formal package manifests missing'
    build = json.loads((root / 'build_manifest.json').read_text())
    declared = json.loads((root / 'source_manifest.json').read_text())
    assert build['status'] == 'PACKAGED_IP_GATE_PASS'
    assert build['identity']['component_xml_sha256'] == sha(component)
    tree = ET.parse(component).getroot()
    identity = ':'.join(tree.find('s:' + n, NS).text for n in ('vendor', 'library', 'name', 'version'))
    assert identity == 'xilinx.com:hls:zero_dce_cnn_top:1.0', identity
    groups = {g.find('s:name', NS).text: g for g in tree.findall('s:fileSets/s:fileSet', NS)}
    assert not any('vhdl' in name.lower() for name in groups), 'active legacy VHDL fileset'
    for view in tree.findall('s:model/s:views/s:view', NS):
        assert 'vhdl' not in view.find('s:name', NS).text.lower(), 'active legacy VHDL view'
    resolved = {}
    for kind, group in [('synthesis', 'xilinx_verilogsynthesis_view_fileset'),
                        ('simulation', 'xilinx_verilogbehavioralsimulation_view_fileset')]:
        assert group in groups
        files = []
        for item in groups[group].findall('s:file', NS):
            relative = item.find('s:name', NS).text
            path = (root / relative).resolve()
            assert path.is_relative_to(root) and path.is_file(), relative
            if path.suffix.lower() in ('.v', '.sv', '.dat'):
                files.append(dict(relative=relative, path=path.as_posix(), sha256=sha(path)))
        assert len({x['path'] for x in files}) == len(files)
        declared_hdl = {x['path']: x['sha256'] for x in declared['filesets'][group]
                        if Path(x['path']).suffix.lower() in ('.v', '.sv', '.dat')}
        assert declared_hdl == {x['relative']: x['sha256'] for x in files}, 'formal source manifest does not match component'
        resolved[kind] = files
    synth = {x['relative']: x for x in resolved['synthesis']}
    sim = {x['relative']: x for x in resolved['simulation']}
    assert synth == sim, 'Verilog synthesis/simulation source mismatch'
    rtl = [Path(x['path']) for x in resolved['simulation'] if Path(x['path']).suffix in ('.v', '.sv')]
    assert set(rtl) == set((root / 'hdl/verilog').glob('*.v')), 'unreferenced RTL shadow in package directory'
    by_name = {p.name: p for p in rtl}
    assert len(by_name) == len(rtl)
    historical = json.loads((REFERENCE_SYSTEM / 'run_manifest.json').read_text())
    expected = {Path(x['candidate']).name: x['candidate_sha256'] for x in historical['substitutions']}
    assert set(expected) == set(NAMES)
    for name in NAMES:
        assert name in by_name and sha(by_name[name]) == expected[name], name
        assert len(list(root.rglob(name))) == 1, ('writer shadow copy', name)
    assert build['identity']['patched_rtl'] == {'hdl/verilog/' + n: expected[n] for n in NAMES}
    modules = {}
    for path in rtl:
        for name in re.findall(r'^\s*module\s+(\w+)\b', path.read_text(), re.M):
            assert name not in modules, ('duplicate compiled module', name)
            modules[name] = path.as_posix()
    assert 'zero_dce_cnn_top' in modules
    return dict(status='PACKAGED_SOURCE_GATE_PASS', ip_root=root.as_posix(),
                vlnv=identity, component_sha256=sha(component), filesets=resolved,
                build_manifest_sha256=sha(root / 'build_manifest.json'),
                build_identity_sha256=build['identity_sha256'],
                source_manifest_sha256=sha(root / 'source_manifest.json'),
                rtl_count=len(rtl), patched_rtl={n: dict(path=by_name[n].as_posix(), sha256=sha(by_name[n])) for n in NAMES},
                module_sources=modules, writer_shadow_copies=0,
                historical_run_manifest_sha256=sha(REFERENCE_SYSTEM / 'run_manifest.json'))


def reverify(gate):
    current = source_gate(gate['ip_root'])
    assert current == gate, 'Released package changed during sanity'


def compile_gate(files, gate):
    """The actual XSIM list must contain each packaged RTL exactly once."""
    paths = [Path(p).resolve() for p in files]
    assert len(paths) == len(set(paths)), 'duplicate compiled source path'
    expected = {Path(x['path']).resolve() for x in gate['filesets']['simulation']
                if Path(x['path']).suffix in ('.v', '.sv')}
    actual = {p for p in paths if p.name.startswith('zero_dce_cnn_top')}
    assert actual == expected, 'CNN compile list is not the complete packaged fileset'
    modules = {}
    for p in paths:
        if p.suffix not in ('.v', '.sv'):
            continue
        for name in re.findall(r'^\s*module\s+(\w+)\b', p.read_text(), re.M):
            if name.startswith('zero_dce_cnn_top'):
                assert name not in modules, ('compiled old writer/module shadow', name)
                modules[name] = p.as_posix()
    assert modules == gate['module_sources']
    return [dict(order=i, path=p.as_posix(), sha256=sha(p)) for i, p in enumerate(paths)]


def verify_list(entries):
    for item in entries:
        assert sha(item['path']) == item['sha256'], item['path']
