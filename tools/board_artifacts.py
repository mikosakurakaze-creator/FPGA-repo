"""Collect or verify the byte-identical K26 board artifacts; never program a board."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from datetime import date
from implementation_gate import validate_replay, copy_replay


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bit_payload(data):
    pos = 2 + int.from_bytes(data[:2], 'big')
    if data[pos:pos + 2] != b'\x00\x01':
        raise RuntimeError('Unexpected bitstream header')
    pos += 2
    for expected in b'abcde':
        if data[pos] != expected:
            raise RuntimeError('Unexpected bitstream field')
        pos += 1
        size = 4 if expected == ord('e') else 2
        length = int.from_bytes(data[pos:pos + size], 'big')
        pos += size
        if expected == ord('e'):
            if pos + length != len(data) or length % 4:
                raise RuntimeError('Invalid bitstream payload length')
            return data[pos:]
        pos += length


def check_identity(folder):
    bit = (folder / 'weather_system.bit').read_bytes()
    with zipfile.ZipFile(folder / 'weather_system.xsa') as archive:
        if archive.testzip() is not None:
            raise RuntimeError('XSA CRC failure')
        bits = [name for name in archive.namelist() if name.endswith('.bit')]
        if len(bits) != 1 or archive.read(bits[0]) != bit:
            raise RuntimeError('External bit and XSA embedded bit differ')
        if archive.read('system.hwh') != (folder / 'weather_system.hwh').read_bytes():
            raise RuntimeError('External HWH and XSA HWH differ')
        metadata = json.loads(archive.read('xsa.json'))
        if metadata['board']['part'] != 'xck26-sfvc784-2LV-c':
            raise RuntimeError('Unexpected FPGA part')
        for name in archive.namelist():
            if name.startswith('drivers/') and not name.endswith('/'):
                if archive.read(name) != (folder / name).read_bytes():
                    raise RuntimeError('Extracted driver differs: ' + name)
            if name.startswith('psu_init'):
                if archive.read(name) != (folder / 'ps_init' / name).read_bytes():
                    raise RuntimeError('Extracted PS initialization differs: ' + name)
    payload = bit_payload(bit)
    # Bootgen zynqmp process_bitstream removes the header and reverses each word.
    converted = bytearray(len(payload))
    for i in range(4):
        converted[i::4] = payload[3 - i::4]
    if bytes(converted) != (folder / 'weather_system.bit.bin').read_bytes():
        raise RuntimeError('Bootgen BIN differs from the bitstream payload')


def qualify(folder):
    timing = (folder / 'routed_timing.rpt').read_text()
    match = re.search(r'WNS\(ns\).*?WPWS\(ns\).*?\n\s*-[-\s]+\n\s*([^\n]+)', timing, re.S)
    if not match:
        raise RuntimeError('Timing summary absent')
    fields = match.group(1).split()
    if len(fields) != 12 or any(float(fields[i]) < 0 for i in (0, 1, 4, 5, 8, 9)):
        raise RuntimeError('Timing slack failed')
    if any(int(fields[i]) for i in (2, 6, 10)):
        raise RuntimeError('Timing endpoints failed')
    checks = dict(re.findall(r'^\d+\.\s+checking\s+(\w+)\s+\((\d+)\)', timing, re.M))
    if len(checks) != 12 or any(int(count) for count in checks.values()):
        raise RuntimeError('Timing coverage failed')
    route = (folder / 'route_status.rpt').read_text()
    counts = {name: int(re.search(r'# of ' + name + r'\.+\s*:\s*(\d+)', route).group(1))
              for name in ('routable nets', 'fully routed nets', 'nets with routing errors')}
    if (counts['routable nets'] <= 0 or counts['routable nets'] != counts['fully routed nets']
            or counts['nets with routing errors']):
        raise RuntimeError('Routing incomplete')
    drc = (folder / 'routed_drc.rpt').read_text()
    rows = re.findall(r'^\|\s*([A-Z][A-Z0-9]+-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|$', drc, re.M)
    if not rows or sum(int(row[3]) for row in rows) != int(re.search(r'Checks found:\s*(\d+)', drc).group(1)):
        raise RuntimeError('DRC summary incomplete')
    if any(row[1] in ('Error', 'Critical Warning') for row in rows):
        raise RuntimeError('Blocking DRC violation')
    audit = json.loads((folder / 'interface_final_audit.json').read_text())
    if not audit['pass'] or not all(audit['checks'].values()):
        raise RuntimeError('Interface audit failed')
    return {'pass': True, 'setup_wns_ns': float(fields[0]), 'hold_whs_ns': float(fields[4]),
            'pulse_width_wpws_ns': float(fields[8]), 'check_timing': checks, 'route': counts,
            'drc': [{'rule': rule, 'severity': severity, 'description': desc, 'count': int(n)}
                    for rule, severity, desc, n in rows], 'interface_checks': len(audit['checks'])}


def file_records(folder):
    return {p.relative_to(folder).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(folder.rglob('*')) if p.is_file()
            and p.name not in ('manifest.json', 'SHA256SUMS')}


def collect(args):
    root = Path(__file__).resolve().parents[1]
    out = args.release.resolve()
    if not (out / 'README.md').is_file() or (out / 'manifest.json').exists():
        raise RuntimeError('Require a prepared README and an unpublished release directory')
    build = args.build.resolve()
    export = args.export.resolve()
    record = json.loads((build / 'build.json').read_text())
    for rel, expected in record['input_files'].items():
        if sha(build / rel) != expected:
            raise RuntimeError('Frozen build input differs: ' + rel)
    for stage in ('create', 'synth', 'impl', 'package'):
        if not record['stages'][stage]['pass']:
            raise RuntimeError('Original implementation stage failed: ' + stage)
    if sha(export / 'weather_system.bit') != sha(build / 'project/weather_system.runs/impl_1/system_wrapper.bit'):
        raise RuntimeError('Export differs from implemented bit')
    if 'WEATHER_BOARD_EXPORT_PASS' not in args.vivado_log.read_text(errors='replace'):
        raise RuntimeError('Vivado export completion marker absent')
    numerical = validate_replay(args.implementation_repro, sha(build / 'system_routed_funcsim.v'))
    for name in ('system_routed.dcp', 'system_routed_funcsim.v'):
        if sha(build / name) != record['stages']['impl'].get('output_sha256', {}).get(name):
            raise RuntimeError('Routed replay is not the recorded implementation output: ' + name)
    for name in ('protect_weather_signed_dsp.tcl', 'check_weather_signed_dsp.tcl'):
        if sha(build / name) != record['stages']['impl'].get('support_sha256', {}).get(name):
            raise RuntimeError('Recorded DSP protection hook absent/differs: ' + name)
    qualification = qualify(export)
    for name in ('weather_system.bit', 'weather_system.bit.bin', 'weather_system.xsa', 'fpga.bif'):
        shutil.copy2(export / name, out / name)
    reports = out / 'reports'
    reports.mkdir()
    for name in ('routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt',
                 'routed_utilization_summary.rpt', 'interface_final_audit.json'):
        shutil.copy2(export / name, reports / name)
    shutil.copy2(build / 'build.json', reports / 'build.json')
    shutil.copy2(args.vivado_log, reports / 'vivado_export_console.txt')
    shutil.copy2(export / 'bootgen_console.txt', reports / 'bootgen_console.txt')
    copy_replay(args.implementation_repro, reports / 'implementation_repro')
    with zipfile.ZipFile(out / 'weather_system.xsa') as archive:
        for name in archive.namelist():
            if name.endswith('/'):
                continue
            if name == 'system.hwh':
                dest = out / 'weather_system.hwh'
            elif name.startswith('psu_init'):
                dest = out / 'ps_init' / name
            elif name.startswith('drivers/'):
                dest = out / name
            else:
                continue
            if not dest.resolve().is_relative_to(out):
                raise RuntimeError('Unsafe archive member')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(name))
    check_identity(out)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    hls = json.loads((root / 'work/stream02/run.json').read_text())
    for rel, expected in hls['source_sha256'].items():
        if sha(root / 'experiments/stream_frame' / rel) != expected:
            raise RuntimeError('Current weather source differs from HLS input: ' + rel)
    manifest = {'schema_version': 2, 'release': out.name, 'export_date': date.today().isoformat(),
                'hardware_source_commit': commit, 'tool': 'Vivado/Bootgen 2025.2',
                'part': 'xck26-sfvc784-2LV-c', 'clock_mhz': 100,
                'method': 'Reuse completed implementation bit; reopen routed run, regenerate reports and XSA; Bootgen BIN conversion',
                'board_tested': False, 'elf_built': False, 'boot_bin_built': False,
                'ltx_required': False, 'linux_device_tree_built': False,
                'qualification': qualification, 'implementation_numerical': numerical,
                'weather_source_sha256': hls['source_sha256'],
                'identity_checks': {'xsa_crc': True, 'embedded_bit_matches': True,
                                    'hwh_and_drivers_match_xsa': True, 'bin_matches_bit_payload': True},
                'files': file_records(out)}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    all_files = dict(manifest['files'])
    all_files['manifest.json'] = {'sha256': sha(out / 'manifest.json')}
    (out / 'SHA256SUMS').write_text(''.join(f"{info['sha256']}  {rel}\n"
                                          for rel, info in sorted(all_files.items())), encoding='ascii')


def verify(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    if file_records(folder) != manifest['files']:
        raise RuntimeError('Release inventory/size/SHA-256 mismatch')
    sums = {line.split('  ', 1)[1]: line.split('  ', 1)[0]
            for line in (folder / 'SHA256SUMS').read_text().splitlines()}
    expected = {rel: info['sha256'] for rel, info in manifest['files'].items()}
    expected['manifest.json'] = sha(folder / 'manifest.json')
    if sums != expected:
        raise RuntimeError('SHA256SUMS mismatch')
    if qualify(folder / 'reports') != manifest['qualification']:
        raise RuntimeError('Manifest/report qualification mismatch')
    if manifest.get('schema_version', 1) >= 2:
        numerical = manifest['implementation_numerical']
        if validate_replay(folder / 'reports/implementation_repro/run.json', numerical['full_system_netlist_sha256']) != numerical:
            raise RuntimeError('Manifest/routed numerical replay mismatch')
    check_identity(folder)
    print(f"WEATHER_BOARD_RELEASE_PASS files={len(manifest['files'])} part={manifest['part']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    gather = sub.add_parser('collect')
    gather.add_argument('--build', type=Path, required=True)
    gather.add_argument('--export', type=Path, required=True)
    gather.add_argument('--vivado-log', type=Path, required=True)
    gather.add_argument('--release', type=Path, required=True)
    gather.add_argument('--implementation-repro', type=Path, required=True)
    check = sub.add_parser('verify')
    check.add_argument('--release', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'collect':
        collect(args)
    verify(args.release.resolve())
