"""Independent byte/ABI/view audit of both freshly packaged release entries."""
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path('E:/HLS/kv260_three_module_v1_2_phase4/cnn_r4_export/hls/impl/ip')
NS = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
WRITERS = {'zero_dce_cnn_top_row_axi_writer.v', 'zero_dce_cnn_top_row_axi_writer_2.v',
           'zero_dce_cnn_top_p_anonymous_namespace_output_writer.v'}
BASE_BUILD_ARTIFACTS = {'pack.bat', 'run_ippack.tcl', 'vivado.jou', 'vivado.log',
                        'xilinx_com_hls_zero_dce_cnn_top_1_0.zip'}
POINTERS = {'INPUT_Q14': '0x10', 'WEIGHTS_INT8': '0x1c', 'BIAS_INT32': '0x28',
            'WEIGHT_FRAC': '0x34', 'TANH_LUT_Q15': '0x40', 'A_LOW_Q14': '0x4c',
            'WORKSPACE_INT16': '0x58'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def base_payload():
    # The old HLS packaging launcher/logs and old unpatched release ZIP are
    # execution artifacts, never sources in the released repository entry.
    return {n: digest for n, digest in tree(BASE).items() if n not in BASE_BUILD_ARTIFACTS}


def module_names(source):
    # HLS often puts an attribute on the same line as a declaration, and a
    # single arithmetic source may contain several named module definitions.
    # `always @ (*)` is an event list, not an attribute; never consume its
    # following process body while removing HLS `(* ... *)` attributes.
    clean = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\(\*(?!\s*\)).*?\*\)',
                   ' ', source, flags=re.S)
    return re.findall(r'\bmodule\s+(?:automatic\s+)?([A-Za-z_$][\w$]*)', clean)


def canonical_abi(root):
    keys = ['s:vendor', 's:library', 's:name', 's:version', 's:busInterfaces', 's:addressSpaces', 's:memoryMaps',
            's:model/s:ports', 's:model/s:modelParameters', 's:parameters']
    result = {}
    for key in keys:
        element = root.find(key, NS)
        if element is not None:
            # Whitespace indentation is metadata formatting, not ABI.
            for item in element.iter():
                if item.text is not None:
                    item.text = item.text.strip()
                item.tail = None
            result[key] = ET.tostring(element, encoding='unicode')
    return result


def audit(ip):
    original = base_payload()
    final = tree(ip)
    require(set(original) <= set(final), 'An original IP file was removed')
    changed = [n for n in original if original[n] != final[n]]
    expected = {'hdl/verilog/' + n for n in WRITERS} | {'component.xml'}
    require(set(changed) == expected, 'IP byte changes exceed component.xml and the three writers: ' + repr(changed))
    root = ET.parse(ip / 'component.xml').getroot()
    base = ET.parse(BASE / 'component.xml').getroot()
    abi = canonical_abi(root)
    require(abi == canonical_abi(base), 'External component ABI changed')
    header = next(ip.glob('drivers/**/xzero_dce_cnn_top_hw.h'))
    require(sha(header) == '3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362', 'Driver register header differs')
    registers = dict(re.findall(r'#define\s+XZERO_DCE_CNN_TOP_CONTROL_ADDR_(\w+)_DATA\s+(0x[0-9a-f]+)', header.read_text()))
    require(registers == POINTERS, 'Seven pointer register offsets changed')
    buses = [b.findtext('s:name', namespaces=NS) for b in root.findall('s:busInterfaces/s:busInterface', NS)]
    require(set(n for n in buses if n.startswith('m_axi_')) ==
            {'m_axi_' + n for n in ('gmem_input', 'gmem_output', 'gmem_workspace', 'gmem8', 'gmem32', 'gmem_lut')},
            'Six m_axi bundles changed')
    require('s_axi_control' in buses, 'AXI-Lite control interface missing')
    file_sets = {}
    for group in root.findall('s:fileSets/s:fileSet', NS):
        key = group.findtext('s:name', namespaces=NS)
        files = [item.findtext('s:name', namespaces=NS) for item in group.findall('s:file', NS)]
        require(len(files) == len(set(files)), 'Duplicate files in fileset ' + key)
        for name in files:
            candidate = (ip / name).resolve()
            require(candidate.is_relative_to(ip.resolve()) and candidate.is_file(), 'Missing/outside source: ' + name)
        file_sets[key] = files
    active = {}
    for view in root.findall('s:model/s:views/s:view', NS):
        env = view.findtext('s:envIdentifier', namespaces=NS) or ''
        if not (env.endswith(':synthesis') or env.endswith(':simulation')):
            continue
        kind = env.rsplit(':', 1)[-1]
        require(view.findtext('s:language', namespaces=NS).lower() == 'verilog', 'Old VHDL source view remains active')
        require(kind not in active, 'Ambiguous active ' + kind + ' view')
        files = []
        for reference in view.findall('s:fileSetRef', NS):
            name = reference.findtext('s:localName', namespaces=NS)
            require(name in file_sets, 'Undefined fileset reference ' + str(name))
            files.extend(file_sets[name])
        require(len(files) == len(set(files)), 'Duplicate active view files')
        rtl = [n for n in files if Path(n).suffix.lower() in ('.v', '.sv', '.vhd', '.vhdl')]
        require(all(Path(n).suffix.lower() in ('.v', '.sv') for n in rtl), 'VHDL is in active compile sources')
        for writer in WRITERS:
            require(rtl.count('hdl/verilog/' + writer) == 1, 'Writer source ambiguous or missing: ' + writer)
        # Top-level module names must resolve uniquely within each active view.
        modules = {}
        for name in rtl:
            for module in module_names((ip / name).read_text(errors='strict')):
                require(module not in modules, 'Shadow module: ' + module)
                modules[module] = name
        # Include headers and memory initialization data as well as modules:
        # different header/ROM bindings are also a synthesis/simulation split.
        active[kind] = {n: final[n] for n in files if n.startswith('hdl/')}
    require(set(active) == {'synthesis', 'simulation'}, 'Synthesis/simulation view missing')
    require(active['synthesis'] == active['simulation'], 'Synthesis/simulation RTL differ')
    require(not any('vhdl' in name.lower() for name in file_sets), 'Old VHDL fileset is still catalog-visible')
    require(root.findtext('s:model/s:views/s:view/s:modelName', namespaces=NS) == 'zero_dce_cnn_top', 'Top differs')
    return dict(status='PASS', ip=ip.as_posix(), base_ip=BASE.as_posix(),
                original_file_count=len(original), changed_original_files=changed,
                excluded_base_build_artifacts=sorted(BASE_BUILD_ARTIFACTS),
                unchanged_original_files=len(original) - len(changed), added_files=sorted(set(final) - set(original)),
                all_original_hdl_unchanged_except_three=True,
                abi_sha256=hashlib.sha256(json.dumps(abi, sort_keys=True).encode()).hexdigest(),
                driver_sha256=sha(header), seven_pointer_offsets=registers,
                synthesis_simulation_same_rtl_count=sum(Path(n).suffix in ('.v', '.sv') for n in active['synthesis']),
                synthesis_simulation_same_hdl_header_rom_count=len(active['synthesis']),
                unique_named_module_definitions=len(modules),
                writer_hashes={n: final['hdl/verilog/' + n] for n in sorted(WRITERS)},
                active_verilog_views_only=True, unique_module_resolution=True, files=final)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True, type=Path)
    parser.add_argument('--rebuild', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'Audit output already exists')
    first, second = audit(args.ip.resolve()), audit(args.rebuild.resolve())
    # Execution manifests may include their own time/output path. Compare every
    # payload file, including raw component.xml, with no metadata exclusions.
    base_names = set(base_payload())
    require({n: first['files'][n] for n in base_names} == {n: second['files'][n] for n in base_names},
            'Rebuilt packaged payload is not byte deterministic')
    result = dict(status='PASS', primary=first, rebuild=second,
                  deterministic_original_payload_files=len(base_names), component_metadata_byte_identical=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS', primary=first['ip'], active_rtl=first['synthesis_simulation_same_rtl_count'],
                          changed_original_files=first['changed_original_files'],
                          shared_hdl_header_rom=first['synthesis_simulation_same_hdl_header_rom_count'],
                          named_module_definitions=first['unique_named_module_definitions'],
                          deterministic_payload_files=len(base_names))))


if __name__ == '__main__':
    main()
