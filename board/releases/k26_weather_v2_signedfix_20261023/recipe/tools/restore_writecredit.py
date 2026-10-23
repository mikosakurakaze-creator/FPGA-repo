"""Apply the historical writer overlay only to byte-identical rebuilt inputs.

Metadata switches both synthesis/simulation to Verilog. This creates a fresh
candidate identity; it does not recreate the historical full-package hash.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--reference', type=Path, required=True)
p.add_argument('--base', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
ref, base, out = a.reference.resolve(), a.base.resolve(), a.output.resolve()
folder = ref / 'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4_writecredit'
manifest = json.loads((folder / 'candidate_manifest.json').read_text(encoding='utf-8'))
sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
for record in manifest['overlays']:
    assert sha(base / 'hdl/verilog' / record['name']) == record['frozen_sha256'], 'Rebuilt writer differs'
    assert sha(folder / 'rtl' / record['name']) == record['candidate_sha256'], 'Historical overlay differs'
if out.exists():
    raise RuntimeError('Refuse to overwrite output')
shutil.copytree(base, out)
for record in manifest['overlays']:
    shutil.copy2(folder / 'rtl' / record['name'], out / 'hdl/verilog' / record['name'])
ns = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009', 'x': 'http://www.xilinx.com'}
ET.register_namespace('spirit', ns['s'])
ET.register_namespace('xilinx', ns['x'])
ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
tree = ET.parse(out / 'component.xml')
root = tree.getroot()
for parent in (root.find('s:model/s:views', ns), root.find('s:fileSets', ns)):
    for entry in list(parent):
        if 'vhdl' in entry.findtext('s:name', namespaces=ns).lower():
            parent.remove(entry)
root.find('s:vendorExtensions/x:coreExtensions/x:coreRevision', ns).text = '2114810450'
tree.write(out / 'component.xml', encoding='utf-8', xml_declaration=True)
audit = {'pass': True, 'base': str(base), 'overlay_manifest_sha256': sha(folder / 'candidate_manifest.json'),
         'writers': manifest['overlays'], 'metadata_requires_checksum_refresh': True,
         'scope': 'exact historical writer RTL restored over matching regenerated writer inputs'}
lock=json.loads((ref/'fpga/ip/cnn_v1_2_writecredit/input_lock.json').read_text(encoding='utf-8'))
different=[name for name,expected in lock['base_payload'].items()
           if not (base/name).is_file() or sha(base/name)!=expected]
if different != ['component.xml','dfx_runtime.txt']:
    raise RuntimeError('Unexpected rebuilt payload differences: '+str(different))
audit['original_payload_compared']=len(lock['base_payload'])
audit['original_payload_equal']=len(lock['base_payload'])-len(different)
audit['original_payload_differences']=different
(out / 'overlay_audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
print('WRITECREDIT_RESTORE_PASS', out)
