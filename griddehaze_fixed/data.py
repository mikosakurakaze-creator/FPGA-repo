"""Audit user ZIPs, extract image bytes safely, and record deterministic splits."""
import argparse
from collections import Counter, defaultdict
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile
from PIL import Image
from .io import sha256, write_json

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}


def safe_member(name):
    normalized = name.replace('\\', '/')
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') or ':' in p for p in path.parts):
        raise ValueError('Unsafe ZIP member: ' + name)
    if any(p.endswith((' ', '.')) for p in path.parts):
        raise ValueError('Ambiguous Windows ZIP member: ' + name)
    return path


def inventory(path):
    path = Path(path).resolve()
    with zipfile.ZipFile(path) as archive:
        members = [{'member': i.filename, 'bytes': i.file_size, 'compressed_bytes': i.compress_size,
                    'directory': i.is_dir(), 'crc32': f'{i.CRC:08x}'} for i in archive.infolist()]
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path),
            'member_count': len(members), 'file_count': sum(not i['directory'] for i in members),
            'extensions': dict(Counter(PurePosixPath(i['member']).suffix.lower() for i in members if not i['directory'])),
            'members': members}


def extract_images(path, kind, output, source_sha):
    output = Path(output).resolve()
    entries, seen = [], set()
    with zipfile.ZipFile(path) as archive:
        candidates = [i for i in archive.infolist() if not i.is_dir() and PurePosixPath(i.filename).suffix.lower() in IMAGE_EXTENSIONS]
        if sum(i.file_size for i in candidates) > 2*1024**3:
            raise ValueError('Image extraction budget exceeded')
        for info in candidates:
            relative = safe_member(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('ZIP symlink refused: ' + info.filename)
            if info.file_size > 128*1024**2:
                raise ValueError('Image member size limit exceeded: ' + info.filename)
            destination = (output/'images'/kind/Path(*relative.parts)).resolve()
            if not destination.is_relative_to(output/'images'):
                raise ValueError('ZIP destination escapes output directory')
            # Windows filesystems can alias case-different names.
            key = str(destination).casefold()
            if key in seen or destination.exists():
                raise ValueError('Duplicate image destination: ' + info.filename)
            seen.add(key)
            raw = archive.read(info)  # zipfile checks CRC while reading.
            if len(raw) != info.file_size:
                raise ValueError('ZIP member length mismatch')
            with Image.open(BytesIO(raw)) as image:
                width, height = image.size
                mode = image.mode
                image.load()
            if min(width, height) < 1:
                raise ValueError('Empty decoded image: ' + info.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(raw)
            entries.append({'path': str(destination), 'member': info.filename, 'archive': kind,
                            'archive_sha256': source_sha, 'sha256': hashlib.sha256(raw).hexdigest(),
                            'bytes': len(raw), 'width': width, 'height': height, 'source_mode': mode,
                            'rank': hashlib.sha256((kind+':'+info.filename).encode('utf-8')).hexdigest()})
    return sorted(entries, key=lambda r: r['rank'])


def partition(entries, calibration_count, validation_count, approved_member=None):
    """Keep exact-byte duplicate groups together, including approved holdout."""
    groups = defaultdict(list)
    for entry in entries:
        groups[entry['sha256']].append(entry)
    ordered = sorted(groups.values(), key=lambda group: min(e['rank'] for e in group))
    held = [g for g in ordered if approved_member and any(PurePosixPath(e['member']).name.casefold() == approved_member.casefold() for e in g)]
    if approved_member and sum(PurePosixPath(e['member']).name.casefold() == approved_member.casefold() for e in entries) != 1:
        raise ValueError('Approved validation image must occur exactly once: ' + approved_member)
    remaining = [g for g in ordered if g not in held]
    def take(count):
        result = []
        while remaining and len(result) < count:
            result.extend(remaining.pop(0))
        if len(result) < count:
            raise ValueError('Not enough distinct image groups for requested split')
        return result
    calibration = take(calibration_count)
    validation = [entry for group in held for entry in group]
    validation += take(max(0, validation_count-len(validation)))
    reserved = [entry for group in remaining for entry in group]
    return calibration, validation, reserved


def prepare(fog_zip, rain_zip, output, inspect_zip=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        all_entries, sources = [], {}
        for kind, path in (('Fog', fog_zip), ('Rain', rain_zip)):
            source = inventory(path)
            sources[kind] = {k: v for k, v in source.items() if k != 'members'}
            write_json(output/(kind.lower()+'_archive_inventory.json'), source)
            all_entries += extract_images(path, kind, output, source['sha256'])
        if inspect_zip:
            source = inventory(inspect_zip)
            source['extracted'] = False
            write_json(output/'inspection_only_archive_inventory.json', source)
            sources['inspection_only'] = {k: v for k, v in source.items() if k != 'members'}
        result = {'format_version': 'griddehaze-userdata-split-v1', 'source_archives': sources,
                  'calibration': [], 'validation': [], 'independent_test': [],
                  'independence_established': False,
                  'split_rule': 'Rank SHA256(kind + colon + ZIP member UTF-8); keep exact byte duplicates together; Fog30 calibration/10 validation with foggy-001 held out; Rain20 calibration/5 validation; remainder reserved unexecuted.',
                  'duplicate_rule': 'Exact-byte duplicate groups remain together; group boundaries may increase requested counts.',
                  'limitations': ['No scene, camera, perceptual or near-duplicate independence audit.',
                                 'Fog/Rain labels are weather detection labels, not paired clear restoration ground truth.',
                                 'independent_test is a reserved file split; no benchmark or generalization claim is established.',
                                 'No image resize/crop/color conversion applied during extraction; calibration must record its own transforms.',
                                 'Inspection-only archive hashed/listed, never extracted or assumed to contain model handoff.']}
        for kind, calibration_count, validation_count, approved in (('Fog', 30, 10, 'foggy-001.jpg'), ('Rain', 20, 5, None)):
            entries = [e for e in all_entries if e['archive'] == kind]
            partitions = partition(entries, calibration_count, validation_count, approved)
            for name, entries in zip(('calibration', 'validation', 'independent_test'), partitions):
                result[name] += sorted(entries, key=lambda e: e['rank'])
        # Cross-source exact duplicate leakage is rejected, not ignored.
        source_splits = defaultdict(set)
        for name in ('calibration', 'validation', 'independent_test'):
            for e in result[name]:
                source_splits[e['sha256']].add(name)
        leakage = [key for key, splits in source_splits.items() if len(splits) > 1]
        if leakage:
            write_json(output/'cross_split_exact_duplicate_failure.json', {'sha256': leakage})
            raise ValueError('Exact duplicate images cross split boundaries; explicit grouping review required')
        duplicates = defaultdict(list)
        for e in all_entries:
            duplicates[e['sha256']].append({'archive': e['archive'], 'member': e['member']})
        result['exact_duplicate_groups'] = [{'sha256': key, 'members': value} for key, value in duplicates.items() if len(value) > 1]
        result['counts'] = {name: dict(Counter(e['archive'] for e in result[name])) for name in ('calibration', 'validation', 'independent_test')}
        result['dimension_counts'] = dict(Counter(f"{e['height']}x{e['width']}" for e in all_entries))
        write_json(output/'splits.json', result)
        return result
    except Exception as error:
        write_json(output/'failure.json', {'type': type(error).__name__, 'message': str(error), 'output_preserved': True})
        raise


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--fog-zip', required=True)
    parser.add_argument('--rain-zip', required=True)
    parser.add_argument('--inspect-zip')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = prepare(args.fog_zip, args.rain_zip, args.out, args.inspect_zip)
    print(json.dumps({'counts': result['counts'], 'dimension_counts': result['dimension_counts'],
                      'exact_duplicate_groups': len(result['exact_duplicate_groups']),
                      'splits_file': str(Path(args.out).resolve()/'splits.json')}, indent=2))


if __name__ == '__main__':
    main()
