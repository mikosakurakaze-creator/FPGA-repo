"""Collect the reviewed implementation-only signed-DSP correction, never push.

Original release/build and board fixture remain read-only. A new board retest
is required even when the corrected routed functional replay passes.
"""
import argparse
import hashlib
from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
from board_artifacts import sha, check_identity, qualify, file_records, verify
from implementation_gate import validate_replay, copy_replay


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('original-build', 'original-release', 'corrected-build', 'linked-checkpoint',
                 'optimized-checkpoint', 'optimization-log', 'implementation-log', 'strict-check-log',
                 'export', 'export-log', 'implementation-repro', 'release'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out, export, build = a.release.resolve(), a.export.resolve(), a.corrected_build.resolve()
    if not (out / 'README.md').is_file() or (out / 'manifest.json').exists():
        raise RuntimeError('Require prepared README and an unpublished new release directory')
    verify(a.original_release.resolve())
    original = json.loads((a.original_build / 'build.json').read_text())
    for rel, expected in original['input_files'].items():
        if sha(a.original_build / rel) != expected:
            raise RuntimeError('Original frozen IP/BD changed: ' + rel)
    for path, marker in ((a.optimization_log, 'WEATHER_PROTECTED_OPTIMIZATION_COMPLETED'),
                         (a.implementation_log, 'WEATHER_SIGNED_FIX_IMPLEMENTATION_COMPLETED'),
                         (a.strict_check_log, 'WEATHER_SIGNED_BOUNDARY_VALIDATION_PASS'),
                         (a.export_log, 'WEATHER_CORRECTED_CHECKPOINT_BIT_PASS')):
        text = path.read_text(errors='replace')
        if marker not in text or '\nERROR:' in text:
            # Native XSA export may fail after the independent bit succeeded.
            if path != a.export_log or marker not in text:
                raise RuntimeError('Build/check/export log failed: ' + str(path))
    if 'actual_pass=1 expected_pass=1' not in a.strict_check_log.read_text(errors='replace'):
        raise RuntimeError('Strict boundary check did not accept corrected checkpoint')
    if str((build / 'system_routed.dcp').resolve()).replace('\\', '/') not in a.export_log.read_text(errors='replace').replace('\\', '/'):
        raise RuntimeError('Bit export did not open the corrected routed checkpoint')
    numerical = validate_replay(a.implementation_repro, sha(build / 'system_routed_funcsim.v'))
    native = json.loads((export / 'native_platform_identity.json').read_text())
    native_log = export / 'native_platform_console.txt'
    if (not native.get('pass') or native.get('metadata_regenerated') is not True
            or native['native_xsa_sha256'] != sha(export / 'weather_system.xsa')
            or native['native_log_sha256'] != sha(native_log)
            or native['embedded_bit_sha256'] != sha(export / 'weather_system.bit')
            or 'WEATHER_CORRECTED_CHECKPOINT_PLATFORM_PASS' not in native_log.read_text(errors='replace')):
        raise RuntimeError('Native-platform export provenance differs')
    with zipfile.ZipFile(a.original_release / 'weather_system.xsa') as before, zipfile.ZipFile(export / 'weather_system.xsa') as after:
        if after.testzip() is not None or set(after.namelist()) != set(native['native_member_sha256']):
            raise RuntimeError('Native XSA member inventory/CRC differs')
        for name, expected in native['native_member_sha256'].items():
            if hashlib.sha256(after.read(name)).hexdigest() != expected:
                raise RuntimeError('Native XSA member differs: ' + name)
        for name in native['fixed_platform_members_byte_identical']:
            if before.read(name) != after.read(name):
                raise RuntimeError('Native fixed-platform metadata differs: ' + name)
        if after.read(native['embedded_bit_member']) != (export / 'weather_system.bit').read_bytes():
            raise RuntimeError('Native embedded/external bit differs')
    reports = out / 'reports'
    reports.mkdir()
    for name in ('weather_system.bit', 'weather_system.bit.bin', 'weather_system.xsa', 'fpga.bif'):
        shutil.copy2(export / name, out / name)
    for name in ('routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt', 'routed_utilization_summary.rpt'):
        shutil.copy2(export / name, reports / name)
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
    audit_path = a.original_release / 'reports/interface_final_audit.json'
    audit = json.loads(audit_path.read_text())
    if not audit['pass'] or not all(audit['checks'].values()):
        raise RuntimeError('Original interface audit failed')
    audit['scope'] = 'Original generated BD/PS/ABI audit reused for byte-identical HWH/PS/drivers; platform wrapper metadata regenerated by Vivado; new bit identity checked separately; no board execution'
    audit['original_audit_sha256'] = sha(audit_path)
    audit['checks'].update({'xsa_hwh_ps_drivers_byte_identical_to_reference': True,
                            'corrected_embedded_bit_equals_external': True,
                            'corrected_bin_equals_bit_payload': True})
    audit['artifacts']['xsa_sha256'] = sha(out / 'weather_system.xsa')
    audit['artifacts']['bit_sha256'] = sha(out / 'weather_system.bit')
    (reports / 'interface_final_audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    qualification = qualify(reports)
    copy_replay(a.implementation_repro, reports / 'implementation_repro')
    for source, name in ((a.optimization_log, 'optimization_console.txt'),
                         (a.implementation_log, 'implementation_console.txt'),
                         (a.strict_check_log, 'strict_boundary_console.txt'),
                         (a.export_log, 'vivado_export_console.txt'),
                         (export / 'bootgen_console.txt', 'bootgen_console.txt'),
                         (export / 'native_platform_identity.json', 'native_platform_identity.json'),
                         (native_log, 'native_platform_console.txt'),
                         (export / 'native_xsa_status.txt', 'native_xsa_first_attempt_status.txt'),
                         (a.original_build / 'build.json', 'original_build.json')):
        shutil.copy2(source, reports / name)
    shutil.copytree(build / 'executed_sources', reports / 'implementation_executed_sources')
    recipe = out / 'recipe'
    for folder in ('system', 'tools', 'deployment'):
        shutil.copytree(root / folder, recipe / folder, ignore=shutil.ignore_patterns('__pycache__'))
    git = lambda *args: subprocess.check_output(['git', *args], cwd=root, text=True)
    status = git('status', '--short', '--branch')
    (reports / 'source_worktree_status.txt').write_text(status, encoding='utf-8')
    # HEAD alone is not the identity of an uncommitted corrected recipe.
    recipe_files = {path.relative_to(root).as_posix(): sha(path)
                    for folder in ('system', 'tools', 'deployment') for path in (root / folder).rglob('*')
                    if path.is_file() and '__pycache__' not in path.parts}
    provenance = {'original_build_json_sha256': sha(a.original_build / 'build.json'),
                  'linked_synthesis_checkpoint': {'path': str(a.linked_checkpoint), 'sha256': sha(a.linked_checkpoint)},
                  'protected_opt_checkpoint': {'path': str(a.optimized_checkpoint), 'sha256': sha(a.optimized_checkpoint)},
                  'routed_checkpoint': {'path': str(build / 'system_routed.dcp'), 'sha256': sha(build / 'system_routed.dcp')},
                  'routed_netlist': {'path': str(build / 'system_routed_funcsim.v'), 'sha256': sha(build / 'system_routed_funcsim.v')},
                  'source_head': git('rev-parse', 'HEAD').strip(), 'branch': git('branch', '--show-current').strip(),
                  'source_worktree_dirty': True, 'current_recipe_sha256': recipe_files,
                  'note': 'Implementation executed with the earlier guard snapshot archived here; strict source/OPMODE check and numerical replay were then run on the completed design. Current hooks improve future rebuild validation without changing this checkpoint.'}
    (reports / 'corrected_build_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    for name in ('board_mismatch_20261023.md', 'implementation_assumptions_audit_20261023.md', 'change_review_20261023.md'):
        shutil.copy2(root / 'docs' / name, reports / name)
    evidence = reports / 'analysis_evidence'
    evidence.mkdir()
    for path in (root / 'evidence').glob('*20261023*.json'):
        shutil.copy2(path, evidence / path.name)
    manifest = {'schema_version': 2, 'release': out.name, 'export_date': date.today().isoformat(),
                'tool': 'Vivado/Bootgen 2025.2', 'part': 'xck26-sfvc784-2LV-c', 'clock_mhz': 100,
                'method': 'Disable DSP cascade fixing from unchanged linked synthesis; new placement and routing; native Vivado XSA/bit; Bootgen BIN',
                'board_tested': False, 'board_retest_required': True, 'elf_built': False,
                'boot_bin_built': False, 'ltx_required': False, 'linux_device_tree_built': False,
                'source_provenance': provenance, 'qualification': qualification,
                'implementation_numerical': numerical, 'xsa_metadata_regenerated': True,
                'reference_release': a.original_release.name,
                'reference_release_manifest_sha256': sha(a.original_release / 'manifest.json'),
                'identity_checks': {'xsa_crc': True, 'embedded_bit_matches': True,
                                    'hwh_and_drivers_match_xsa': True, 'bin_matches_bit_payload': True,
                                    'native_platform_export': True,
                                    'unchanged_fixed_platform_members': len(native['fixed_platform_members_byte_identical'])},
                'files': file_records(out)}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    sums = {name: item['sha256'] for name, item in manifest['files'].items()}
    sums['manifest.json'] = sha(out / 'manifest.json')
    (out / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(sums.items())), encoding='ascii')
    verify(out)


if __name__ == '__main__':
    main()
