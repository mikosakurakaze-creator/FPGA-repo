"""Package/verify the exact frozen lowlight IPs, without Vivado repackaging."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('cnn', 'bilinear', 'curve')
ARCHIVE = ROOT/'delivery/lowlight_frozen_ip_20261028.zip'
MANIFEST = ROOT/'delivery/lowlight_frozen_ip_20261028.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(archive, manifest, extract_to=None):
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    if digest(archive.read_bytes()) != metadata['archive_sha256']:
        raise ValueError('Archive SHA256 mismatch')
    expected = metadata['files']
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected):
            raise ValueError('Archive file list mismatch')
        for name, spec in expected.items():
            parts = PurePosixPath(name).parts
            if len(parts) < 3 or parts[0] != 'ip' or parts[1] not in NAMES or '..' in parts:
                raise ValueError('Unsafe archive path')
            payload = z.read(name)
            if len(payload) != spec['bytes'] or digest(payload) != spec['sha256']:
                raise ValueError('File mismatch: '+name)
        if extract_to is not None:
            extract_to.mkdir(parents=True, exist_ok=False)
            z.extractall(extract_to)
            for name, spec in expected.items():
                if digest((extract_to/name).read_bytes()) != spec['sha256']:
                    raise ValueError('Extracted file mismatch: '+name)
    print('FROZEN_LOWLIGHT_PASS files='+str(len(expected)))


def pack(source, archive, manifest):
    frozen = ROOT/'reports/resource_frozen_inputs.json'
    original = json.loads(frozen.read_text(encoding='utf-8'))['frozen_input_files']
    locked = {k.replace('\\','/'):v for k,v in original.items()
              if k.replace('\\','/').split('/')[1] in NAMES}
    files = {p.relative_to(source.parent).as_posix():p
             for name in NAMES for p in (source/name).rglob('*') if p.is_file()}
    if set(files) != set(locked):
        raise ValueError('Source differs from the frozen file list')
    if archive.exists() or manifest.exists():
        raise ValueError('Refusing to overwrite release files')
    archive.parent.mkdir(parents=True, exist_ok=True)
    specs = {}
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name, p in sorted(files.items()):
            payload = p.read_bytes()
            if digest(payload) != locked[name]:
                raise ValueError('Frozen source SHA mismatch: '+name)
            info = zipfile.ZipInfo(name, date_time=(2026,10,28,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info,payload)
            specs[name] = dict(bytes=len(payload),sha256=locked[name])
    metadata = dict(format='frozen-lowlight-ip-v1', source_directory=str(source),
                    source_manifest='reports/resource_frozen_inputs.json',
                    source_manifest_sha256=digest(frozen.read_bytes()),
                    archive_sha256=digest(archive.read_bytes()),archive_bytes=archive.stat().st_size,
                    file_counts={name:sum(p.startswith('ip/'+name+'/') for p in specs) for name in NAMES},
                    scope='Exact original packages, including packaging audits; no save_core/export/revision change',
                    files=specs)
    manifest.write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8',newline='\n')
    verify(archive,manifest)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('stage',choices=['pack','verify'])
    parser.add_argument('--source',type=Path,default=Path('E:/HLS/joint_lowlight_compact_d_20261028/ip'))
    parser.add_argument('--archive',type=Path,default=ARCHIVE)
    parser.add_argument('--manifest',type=Path,default=MANIFEST)
    parser.add_argument('--extract-to',type=Path)
    a=parser.parse_args()
    if a.stage=='pack':
        pack(a.source,a.archive,a.manifest)
    else:
        verify(a.archive,a.manifest,a.extract_to)


if __name__=='__main__':
    main()
