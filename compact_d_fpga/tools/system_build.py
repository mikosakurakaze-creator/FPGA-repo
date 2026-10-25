"""Build an isolated K26 D image using the known PS configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile
from vendor_runtime import run_vendor

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--stage', choices=['create', 'synth', 'impl', 'verify_impl', 'export'], required=True)
    p.add_argument('--hls', type=Path, default=Path('D:/weather_builds/compact_d_synth01'))
    p.add_argument('--seed', type=Path, default=Path('D:/weather_builds/stream_system01/project/weather_system.srcs/sources_1/bd/system/system.bd'))
    p.add_argument('--ps-config', type=Path, help='Use the saved K26 PS configuration instead of a legacy BD')
    p.add_argument('--vivado', type=Path, default=Path('D:/vivado/2025.2/Vivado'))
    p.add_argument('--runtime', type=Path)
    p.add_argument('--work-dir', type=Path, help='Separate Vivado working directory from the saved build artifacts')
    p.add_argument('--review-existing', action='store_true', help='Review an unchanged verify_impl/export log without rerunning Vivado')
    a = p.parse_args()
    out = a.out.resolve()
    work_dir = (a.work_dir or out).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+', str(out)):
        raise ValueError('Use an ASCII build path without spaces')
    if a.work_dir and work_dir != out:
        work_dir.mkdir(parents=True, exist_ok=True)
    if a.stage == 'create':
        out.mkdir(parents=True, exist_ok=False)
        hls = json.loads((a.hls/'result.json').read_text(encoding='utf-8'))
        if not hls['pass_result']:
            raise RuntimeError('HLS synthesis did not pass')
        shutil.copytree(a.hls/'component/hls/impl/ip', out/'ip/compact_d')
        if a.ps_config:
            shutil.copy2(a.ps_config, out/'ps_config.tcl')
            ps_source = a.ps_config
        else:
            design = json.loads(a.seed.read_text(encoding='utf-8'))
            design['design']['design_info']['gen_directory'] = '../../../../compact_d_system.gen/sources_1/bd/system'
            save(out/'system_seed.bd', design)
            params = design['design']['components']['zynq_ultra_ps_e_0']['parameters']
            def tcl_string(value):
                if isinstance(value, list):
                    value = ' '.join(value)
                return '"'+str(value).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('[', '\\[')+'"'
            ps_commands = ['# PS parameters copied from the actual legacy K26 block design.', 'set_property -dict [list \\']
            for key, entry in params.items():
                ps_commands.append('    CONFIG.'+key+' '+tcl_string(entry['value'])+' \\')
            ps_commands.append('] [get_bd_cells zynq_ultra_ps_e_0]')
            (out/'ps_config.tcl').write_text('\n'.join(ps_commands)+'\n', encoding='ascii', newline='\n')
            ps_source = a.seed
        record = dict(stages={}, parameters=hls['parameters'], hls_source_sha256=hls['source_sha256'],
                      ps_source=str(ps_source), ps_source_sha256=sha(ps_source), kind='independent_D_image',
                      old_projects='preserved unchanged; legacy cores are in their separate images')
        record['ip_files'] = {f.relative_to(out).as_posix(): sha(f) for f in (out/'ip').rglob('*') if f.is_file()}
        save(out/'build.json', record)
    record = json.loads((out/'build.json').read_text(encoding='utf-8'))
    previous = {'synth': 'create', 'impl': 'synth', 'verify_impl': 'synth',
                'export': 'verify_impl' if record['stages'].get('verify_impl', {}).get('pass_result') else 'impl'}.get(a.stage)
    if previous and not record['stages'].get(previous, {}).get('pass_result'):
        raise RuntimeError('Previous stage not passed: '+previous)
    for name, digest in record['ip_files'].items():
        if sha(out/name) != digest:
            raise RuntimeError('IP input changed: '+name)
    script = out/(a.stage+'.tcl')
    if a.review_existing:
        if a.stage not in ('verify_impl', 'export') or sha(script) != record['stages'][a.stage]['script_sha256'] or sha(out/(a.stage+'.log')) != record['stages'][a.stage]['log_sha256']:
            raise ValueError('Only unchanged checkpoint verification/export evidence can be reviewed')
    else:
        shutil.copy2(ROOT/'system/build.tcl', script)
    command = out/('run_'+a.stage+'.cmd')
    command.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\ncall "'+str(a.vivado/'settings64.bat')+'"\nif errorlevel 1 exit /b 1\ncall "'+str(a.vivado/'bin/vivado.bat')+'" -mode batch -notrace -source "'+str(script)+'" -log "'+str(out/(a.stage+'_vivado.log'))+'" -journal "'+str(out/(a.stage+'.jou'))+'" -tclargs "'+str(out)+'" '+a.stage+'\nexit /b %errorlevel%\n', encoding='ascii', newline='\n')
    print('D_SYSTEM_STAGE='+a.stage+' LOG='+str(out/(a.stage+'.log')), flush=True)
    start = time.perf_counter()
    if a.review_existing:
        exit_code = record['stages'][a.stage]['exit_code']
        seconds = record['stages'][a.stage]['seconds']
    else:
        with (out/(a.stage+'.log')).open('wb') as log:
            if a.runtime:
                result = run_vendor(a.vivado, a.runtime, 'vivado.exe', ['-mode', 'batch', '-notrace', '-source', script,
                    '-log', out/(a.stage+'_vivado.log'), '-journal', out/(a.stage+'.jou'), '-tclargs', out, a.stage], work_dir, log)
            else:
                result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(command)], cwd=work_dir, stdout=log, stderr=subprocess.STDOUT)
        exit_code, seconds = result.returncode, time.perf_counter()-start
    log_text = (out/(a.stage+'.log')).read_text(encoding='utf-8', errors='replace')
    marker = 'D_SYSTEM_'+a.stage.upper()+'_PASS'
    commands_completed = marker in log_text and not re.search(r'(?m)^ERROR:', log_text)
    shutdown_exception = exit_code == 3221225477 and bool(re.search(re.escape(marker)+r'\s+INFO: \[Common 17-206\] Exiting Vivado[^\n]*\nAbnormal program termination \(EXCEPTION_ACCESS_VIOLATION\)', log_text))
    # Preserve the real process failure. Only independently reopened checkpoint
    # verification or completed export may be accepted after a teardown fault.
    passed = commands_completed and (exit_code == 0 or (a.stage in ('verify_impl', 'export') and shutdown_exception))
    if a.stage == 'verify_impl' and passed:
        route = (out/'verified_route_status.rpt').read_text(errors='replace')
        counts = {key: int(re.search(r'# of '+key+r'\.+\s*:\s*(\d+)', route).group(1)) for key in ['routable nets', 'fully routed nets', 'nets with routing errors']}
        passed = counts['routable nets'] > 0 and counts['routable nets'] == counts['fully routed nets'] and counts['nets with routing errors'] == 0
    if a.stage == 'export' and passed:
        with zipfile.ZipFile(out/'compact_d_system.xsa') as platform:
            bits = [name for name in platform.namelist() if name.endswith('.bit')]
            if platform.testzip() or len(bits) != 1:
                raise ValueError('Invalid exported platform')
            canonical = platform.read(bits[0])
            if not platform.read('system.hwh'):
                raise ValueError('Missing full system HWH')
        target = out/'compact_d_system.bit'
        # XSA export regenerates the bit header. Keep its exact embedded bit as
        # the canonical board bit rather than mixing two timestamped headers.
        if target.is_file() and target.read_bytes() != canonical:
            shutil.copy2(target, out/'compact_d_standalone.bit')
        target.write_bytes(canonical)
        record['export_artifacts'] = dict(bit_source='XSA embedded bit', bit_sha256=sha(target),
                                          xsa_sha256=sha(out/'compact_d_system.xsa'))
    record['stages'][a.stage] = dict(pass_result=passed, exit_code=exit_code, seconds=seconds,
                                   clean_exit=exit_code == 0, commands_completed=commands_completed, shutdown_exception=shutdown_exception, work_dir=str(work_dir),
                                   script_sha256=sha(script), log_sha256=sha(out/(a.stage+'.log')))
    if a.stage == 'verify_impl':
        record['stages'][a.stage]['checkpoint_sha256'] = sha(out/'system_routed.dcp')
    save(out/'build.json', record)
    print(json.dumps(record['stages'][a.stage], indent=2), flush=True)
    if not passed:
        raise RuntimeError('Stage needs correction; see '+str(out/(a.stage+'.log')))


if __name__ == '__main__':
    main()
