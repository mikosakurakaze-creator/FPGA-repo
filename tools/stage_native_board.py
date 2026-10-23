"""Stage native Vivado XSA/bit and compare fixed platform metadata, no repack."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from board_artifacts import bit_payload, verify, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('reference-release', 'native-xsa', 'native-log', 'bit-export', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    verify(a.reference_release.resolve())
    if 'WEATHER_CORRECTED_CHECKPOINT_PLATFORM_PASS' not in a.native_log.read_text(errors='replace'):
        raise RuntimeError('Native platform export did not complete')
    a.output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(a.reference_release / 'weather_system.xsa') as before, zipfile.ZipFile(a.native_xsa) as after:
        if after.testzip() is not None or len(set(after.namelist())) != len(after.namelist()):
            raise RuntimeError('Native XSA CRC/member identity failed')
        bits = [name for name in after.namelist() if name.endswith('.bit')]
        if len(bits) != 1:
            raise RuntimeError('Require exactly one native bit')
        bit = after.read(bits[0])
        standalone = (a.bit_export / 'weather_system.bit').read_bytes()
        if bit_payload(bit) != bit_payload(standalone):
            raise RuntimeError('Native/independent bit payloads disagree')
        fixed = [name for name in before.namelist() if name == 'system.hwh' or name.startswith(('psu_init', 'drivers/'))]
        if any(name not in after.namelist() or before.read(name) != after.read(name) for name in fixed):
            raise RuntimeError('Native platform changed HWH/PS initialization/drivers')
        common = set(before.namelist()) & set(after.namelist())
        changed = sorted(name for name in common if before.read(name) != after.read(name))
        if set(changed) - {'sysdef.xml', 'xsa.json', 'xsa.xml'}:
            raise RuntimeError('Unexpected native platform metadata change')
        members = {name: hashlib.sha256(after.read(name)).hexdigest() for name in after.namelist()}
        record = {'pass': True, 'method': 'Vivado write_hw_platform from corrected routed DCP, without archive edits',
                  'metadata_regenerated': True, 'native_xsa_sha256': sha(a.native_xsa),
                  'native_log_sha256': sha(a.native_log), 'embedded_bit_member': bits[0],
                  'embedded_bit_sha256': hashlib.sha256(bit).hexdigest(),
                  'independent_bit_sha256': sha(a.bit_export / 'weather_system.bit'),
                  'native_and_independent_bit_payload_equal': True,
                  'fixed_platform_members_byte_identical': fixed,
                  'changed_common_members': changed,
                  'removed_members': sorted(set(before.namelist()) - set(after.namelist())),
                  'added_members': sorted(set(after.namelist()) - set(before.namelist())),
                  'native_member_sha256': members}
    shutil.copy2(a.native_xsa, a.output / 'weather_system.xsa')
    (a.output / 'weather_system.bit').write_bytes(bit)
    (a.output / 'fpga.bif').write_text('all:\n{\n    weather_system.bit\n}\n', encoding='ascii')
    for name in ('routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt', 'routed_utilization_summary.rpt', 'native_xsa_status.txt'):
        shutil.copy2(a.bit_export / name, a.output / name)
    shutil.copy2(a.native_log, a.output / 'native_platform_console.txt')
    (a.output / 'native_platform_identity.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print('WEATHER_NATIVE_BOARD_STAGE_PASS', len(members), 'XSA members; platform unchanged')


if __name__ == '__main__':
    main()
