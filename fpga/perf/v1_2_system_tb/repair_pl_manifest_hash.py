"""Correct a Windows newline hashing mistake in metadata only, retaining evidence."""
from pathlib import Path
import hashlib
import json
import shutil

root=Path('E:/HLS/kv260_three_module_v1_2_phase4')
file=root/'pl_wrapper_manifest.json'
wrapper=root/'phase4_pl.v'
manifest=json.loads(file.read_text())
old=manifest['pl_copy_sha256']
actual=hashlib.sha256(wrapper.read_bytes()).hexdigest()
assert old!=actual
assert old==hashlib.sha256(wrapper.read_text().encode()).hexdigest()
archive=root/'pl_wrapper_manifest_original_lf_hash.json'
assert not archive.exists()
shutil.copy2(file,archive)
manifest['original_in_memory_lf_sha256']=old
manifest['pl_copy_sha256']=actual
manifest['hash_correction']='Hash the actual saved bytes; Windows write_text uses CRLF. No wrapper or DUT bytes changed.'
file.write_text(json.dumps(manifest,indent=2))
assert hashlib.sha256(wrapper.read_bytes()).hexdigest()==actual
print('Corrected metadata SHA-256 only; wrapper and DUT untouched:',actual)
