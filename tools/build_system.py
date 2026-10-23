"""Create/build an isolated low-light + weather K26 system from explicit IP inputs.

Call via run_windows_desktop.py. Stages are explicit and resumable; input hashes
are checked before each stage. No source checkout is modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tcl(value):
    s = str(value).replace('\\', '/')
    if any(c in s for c in '{}\n\r'):
        raise ValueError('unsupported Tcl path')
    return '{' + s + '}'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=Path)
    p.add_argument('--cnn', type=Path)
    p.add_argument('--bilinear', type=Path)
    p.add_argument('--curve', type=Path)
    p.add_argument('--weather', type=Path)
    p.add_argument('--vivado', type=Path, required=True)
    p.add_argument('--stage', choices=['create', 'synth', 'impl', 'package'], required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if a.stage == 'create':
        out.mkdir(parents=True, exist_ok=False)
        manifest = {'input_files': {}, 'stages': {}, 'scope': 'new combined candidate; board tests required'}
        for key in ['cnn', 'bilinear', 'curve', 'weather']:
            source = getattr(a, key).resolve()
            if not (source / 'component.xml').is_file():
                raise ValueError('missing IP: ' + str(source))
            dest = out / 'ip' / key
            shutil.copytree(source, dest)
            for f in dest.rglob('*'):
                if f.is_file():
                    manifest['input_files'][f.relative_to(out).as_posix()] = sha(f)
        original = a.seed.resolve()
        design = json.loads(original.read_text(encoding='utf-8'))
        manifest['seed_source'] = str(original)
        manifest['seed_sha256'] = sha(original)
        design['design']['design_info']['gen_directory'] = '../../../../weather_system.gen/sources_1/bd/system'
        (out / 'system_seed.bd').write_text(json.dumps(design, indent=2) + '\n', encoding='utf-8')
        manifest['input_files']['system_seed.bd'] = sha(out / 'system_seed.bd')
        (out / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    manifest = json.loads((out / 'build.json').read_text(encoding='utf-8'))
    for rel, expected in manifest['input_files'].items():
        if sha(out / rel) != expected:
            raise RuntimeError('build input changed: ' + rel)
    source = Path(__file__).resolve().parents[1] / 'system' / (a.stage + '.tcl')
    cmd = out / ('run_' + a.stage + '.cmd')
    script = out / (a.stage + '.tcl')
    shutil.copy2(source, script)
    support_hashes = {}
    if a.stage == 'impl':
        for name in ('protect_weather_signed_dsp.tcl', 'check_weather_signed_dsp.tcl'):
            dependency = source.parent / name
            shutil.copy2(dependency, out / name)
            support_hashes[name] = sha(out / name)
    cmd.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
        'call "' + str(a.vivado / 'settings64.bat') + '"\n'
        'call "' + str(a.vivado / 'bin/vivado.bat') + '" -mode batch -notrace -source "'
        + str(script) + '" -log "' + str(out / (a.stage + '_vivado.log'))
        + '" -journal "' + str(out / (a.stage + '.jou')) + '" -tclargs "'
        + str(out) + '"\nexit /b %errorlevel%\n', encoding='utf-8')
    print('SYSTEM_STAGE=' + a.stage + ' LOG=' + str(out / (a.stage + '_console.log')), flush=True)
    with (out / (a.stage + '_console.log')).open('wb') as log:
        result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(cmd)],
                                cwd=out, stdout=log, stderr=subprocess.STDOUT)
    marker = 'WEATHER_SYSTEM_' + a.stage.upper() + '_PASS'
    passed = result.returncode == 0 and marker in (out / (a.stage + '_console.log')).read_text(errors='replace')
    if a.stage == 'create':
        # Vivado refreshes checksums/default annotations on the copied package.
        # Record that derived metadata separately from its immutable input hash.
        rel = 'ip/cnn/component.xml'
        current = sha(out / rel)
        manifest['cnn_metadata_refresh'] = {'before_sha256': manifest['input_files'][rel],
                                           'after_sha256': current}
        manifest['input_files'][rel] = current
    manifest['stages'][a.stage] = {'pass': passed, 'exit_code': result.returncode,
        'script_sha256': sha(script), 'support_sha256': support_hashes,
        'console_sha256': sha(out / (a.stage + '_console.log'))}
    if a.stage == 'impl' and passed:
        manifest['stages'][a.stage]['output_sha256'] = {
            name: sha(out / name) for name in ('system_routed.dcp', 'system_routed_funcsim.v')}
    (out / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
