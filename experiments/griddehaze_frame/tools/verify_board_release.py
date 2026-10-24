"""Verify release bytes, Git conversion rules and matching XSA members."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root, refresh=False):
    root = Path(root).resolve()
    files = {p.relative_to(root).as_posix(): p for p in root.rglob('*')
             if p.is_file() and p.name != 'SHA256SUMS'}
    if not files:
        raise ValueError('Empty release')
    manifest = json.loads((root / 'release_manifest.json').read_text(encoding='utf-8'))
    # Preserve A's frozen source bytes. Its scale JSON contains CRLF and its
    # SHA is part of the model identity; converting it would change that identity.
    frozen_files = set()
    model = root / 'model_int16'
    if model.exists():
        model_manifest = json.loads((model / 'manifest.json').read_text(encoding='utf-8'))
        for file_key, hash_key in [('blob_file', 'blob_sha256'),
                                   ('graph_file', 'graph_sha256'),
                                   ('scale_config_file', 'scale_config_sha256')]:
            name = model_manifest[file_key]
            if PurePosixPath(name).name != name:
                raise ValueError('Unsafe model filename')
            if digest((model / name).read_bytes()) != model_manifest[hash_key]:
                raise ValueError('Frozen model identity differs: ' + name)
            frozen_files.add('model_int16/' + name)
        model_identity = manifest['model']
        if (digest((model / 'manifest.json').read_bytes()) != model_identity['manifest_sha256']
                or model_manifest['identity']['bundle_id'] != model_identity['bundle_id']
                or model_manifest['blob_sha256'] != model_identity['parameters_sha256']
                or model_manifest['blob_nbytes'] != model_identity['parameters_bytes']
                or (model / model_manifest['blob_file']).stat().st_size != model_identity['parameters_bytes']):
            raise ValueError('Release model manifest or bundle differs')
        sizes = json.loads((model / 'layout_sizes.json').read_text(encoding='utf-8'))
        if sizes['bundle_id'] != model_identity['bundle_id']:
            raise ValueError('Layout bundle differs')
        for row in sizes['layouts']:
            name = row['file']
            if PurePosixPath(name).name != name:
                raise ValueError('Unsafe layout filename')
            raw = (model / name).read_bytes()
            if len(raw) != 1344 or digest(raw) != row['sha256']:
                raise ValueError('Layout bytes differ: ' + name)
            words = struct.unpack('<336I', raw)
            if (words[:8] != (0x314c4447, 1, row['height'], row['width'], 320, 0,
                             row['scratch_bytes'], 0)
                    or raw[32:64].hex() != model_identity['bundle_id']
                    or words[16] != 0 or words[-1] != 0):
                raise ValueError('Layout header differs: ' + name)
    review_path = root / 'evidence/cross_tile_review.json'
    if review_path.exists():
        review = json.loads(review_path.read_text(encoding='utf-8'))
        artifacts = {
            'evidence/cross_tile_simulation.log': review['simulation_log_sha256'],
            'evidence/cross_tile_executed_test.sv': review['compiled_test_sha256']['frame_axi_test.sv'],
            'evidence/cross_tile_executed_memory.sv': review['compiled_test_sha256']['axi_bounded_memory.sv'],
            'validation_33x47/actual_cold.raw': review['output_sha256'],
            'validation_33x47/actual_warm.raw': review['output_sha256'],
            'validation_33x47/expected_output.raw': review['output_sha256'],
        }
        legacy = json.loads((root / 'evidence/legacy_review.json').read_text(encoding='utf-8'))
        artifacts['evidence/legacy_simulation.log'] = legacy['simulation_log_sha256']
        for index, frame in enumerate(legacy['frames']):
            artifacts[f'evidence/legacy_actual_{index}.bin'] = frame['sha256']
        for name, expected_hash in artifacts.items():
            if digest((root / name).read_bytes()) != expected_hash:
                raise ValueError('Original regression evidence differs: ' + name)
            frozen_files.add(name)
    sample_path = root / 'evidence/new_core_sample.json'
    if sample_path.exists():
        sample = json.loads(sample_path.read_text(encoding='utf-8'))
        if (sample['status'] != 'pass'
                or sample['kind'] != 'post_route_functional_numerical_samples'):
            raise ValueError('New-core sampled numerical result is not passing')
        artifacts = {
            'evidence/new_core_sample.log': sample['simulation_log_sha256'],
            'evidence/new_core_sample.tcl': sample['tcl_sha256'],
            'evidence/new_core_sample_words.txt': sample['capture_sha256'],
        }
        for node in sample['nodes']:
            artifacts[f'evidence/new_core_sample_node_{node["index"]}.raw'] = node['sha256']
        for name, expected_hash in artifacts.items():
            if digest((root / name).read_bytes()) != expected_hash:
                raise ValueError('Routed numerical sample evidence differs: ' + name)
            frozen_files.add(name)
    for directory in ['validation_33x47', 'validation_legacy_8x8']:
        vectors_path = root / directory / 'vectors.json'
        if vectors_path.exists():
            vectors = json.loads(vectors_path.read_text(encoding='utf-8'))
            for name, expected_hash in vectors['files'].items():
                if PurePosixPath(name).name != name:
                    raise ValueError('Unsafe vector filename')
                if digest((vectors_path.parent / name).read_bytes()) != expected_hash:
                    raise ValueError('Validation vector differs: ' + directory + '/' + name)
    for key, name in [('bit', 'griddehaze_system.bit'), ('xsa', 'griddehaze_system.xsa'),
                      ('hwh', 'griddehaze_system.hwh')]:
        if digest(files[name].read_bytes()) != manifest['files'][key]:
            raise ValueError('Hardware identity differs: ' + name)
    with zipfile.ZipFile(files['griddehaze_system.xsa']) as archive:
        if archive.testzip() is not None:
            raise ValueError('XSA CRC failure')
        members = archive.namelist()
        for suffix, name in [('.bit', 'griddehaze_system.bit'), ('.hwh', 'griddehaze_system.hwh')]:
            key = 'bit' if suffix == '.bit' else 'hwh'
            member = manifest['xsa_members'][key]
            if member not in members or not member.endswith(suffix) or archive.read(member) != files[name].read_bytes():
                raise ValueError('XSA embedded member differs: ' + name)
        if manifest['xsa_members']['hwh'] != 'system.hwh':
            raise ValueError('Release HWH must be the complete system, not a SmartConnect subdesign')
    repo = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                      cwd=root, text=True).strip())
    text_files = 0
    for name, path in files.items():
        data = path.read_bytes()
        if path.suffix.lower() in {'.md', '.rpt', '.json', '.h', '.txt', '.py', '.sv', '.log', '.tcl'}:
            data.decode('utf-8')
            if ((b'\r' in data and name not in frozen_files)
                    or data.startswith(b'\xef\xbb\xbf')):
                raise ValueError('Expected UTF-8 without BOM, LF newlines: ' + name)
            if b'\r' not in data:
                text_files += 1
        relative = path.relative_to(repo).as_posix()
        attribute = subprocess.check_output(['git', 'check-attr', 'text', '--', relative],
                                            cwd=repo, text=True).strip()
        if not attribute.endswith(': text: unset'):
            raise ValueError('Release bytes lack -text protection: ' + name)
        raw = subprocess.check_output(['git', 'hash-object', '--stdin'], cwd=repo, input=data)
        clean = subprocess.check_output(['git', 'hash-object', '--path=' + relative, '--stdin'],
                                        cwd=repo, input=data)
        if raw != clean:
            raise ValueError('Git clean conversion changes release bytes: ' + name)
    checksums = root / 'SHA256SUMS'
    if refresh:
        checksums.write_bytes(''.join(digest(files[n].read_bytes()) + '  ' + n + '\n'
                                      for n in sorted(files)).encode('ascii'))
    data = checksums.read_bytes()
    if b'\r' in data:
        raise ValueError('SHA256SUMS must use LF')
    expected = {}
    for line in data.decode('ascii').splitlines():
        matched = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not matched:
            raise ValueError('Malformed checksum entry')
        checksum, name = matched.groups()
        if name in expected or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
            raise ValueError('Duplicate or unsafe checksum path: ' + name)
        expected[name] = checksum
    if set(expected) != set(files):
        raise ValueError('Checksum payload file set differs')
    for name, checksum in expected.items():
        if digest(files[name].read_bytes()) != checksum:
            raise ValueError('Checksum differs: ' + name)
    return dict(pass_result=True, files_verified=len(files), lf_text_files=text_files,
                git_clean_bytes_equal=True, xsa_embedded_bit_equal=True,
                xsa_embedded_hwh_equal=True, hardware_sha256=manifest['files'],
                frozen_original_files_verified=len(frozen_files),
                checksums_sha256=digest(data), board_execution=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--refresh-checksums', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.release, args.refresh_checksums), indent=2))
