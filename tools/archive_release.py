"""Verify a collected release and create a new ZIP plus SHA-256 sidecar."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--release',type=Path,required=True)
a=p.parse_args();root=a.release.resolve()
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
manifest=json.loads((root/'manifest.json').read_text())
files={f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file()}-{'manifest.json'}
if files!=set(manifest['files']):raise RuntimeError('release payload set differs')
for rel,expected in manifest['files'].items():
    f=root/rel
    if f.stat().st_size!=expected['bytes'] or sha(f)!=expected['sha256']:
        raise RuntimeError('release payload differs: '+rel)
archive=root.with_suffix('.zip')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for f in sorted(root.rglob('*')):
        if f.is_file():z.write(f,root.name+'/'+f.relative_to(root).as_posix())
with zipfile.ZipFile(archive) as z:
    if z.testzip() is not None:raise RuntimeError('ZIP CRC failed')
digest=sha(archive)
with archive.with_suffix('.zip.sha256').open('x',encoding='ascii') as f:
    f.write(digest+'  '+archive.name+'\n')
result={'pass':True,'payload_files':len(files),'manifest_sha256':sha(root/'manifest.json'),
        'zip_bytes':archive.stat().st_size,'zip_sha256':digest,
        'scope':'local payload identity and archive integrity; no board claim'}
with (root.parent/(root.name+'_release_verification.json')).open('x',encoding='utf-8') as f:
    json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
