"""Reuse verified synthesis in a fresh component and test task switches/seams."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--base',type=Path,required=True,help='passing run_hls output, both tasks')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--vitis',type=Path,required=True)
p.add_argument('--cxx',type=Path,required=True)
p.add_argument('--experiment',default='onchip_frame',choices=('onchip_frame','stream_frame'))
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
base=a.base.resolve(); out=a.output.resolve()
report={'pass':False,'scope':'HLS RTL repeated task/shape and tile seam verification'}
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
if json.loads((base/'run.json').read_text())['pass'] is not True:
    raise RuntimeError('Passing primary HLS run required')
out.mkdir(parents=True,exist_ok=False)
try:
    experiment=root/'experiments'/a.experiment
    for name in ('weather_frame.cpp','weather_frame.h','weather_kernel.h','params_derain.h','params_dehaze.h'):
        assert sha(base/'derain/src'/name)==sha(experiment/'src'/name), 'Synthesis source differs'
    report['source_sha256']={str(f):sha(f) for f in [root/'system/tb_weather_sequence.cpp',
        experiment/'src/weather_kernel_reference.cpp',experiment/'src/weather_frame.cpp']}
    tb=out/'tb_weather_sequence.cpp';shutil.copy2(root/'system/tb_weather_sequence.cpp',tb)
    ref=out/'weather_kernel_reference.cpp';shutil.copy2(experiment/'src/weather_kernel_reference.cpp',ref)
    exe=out/'sequence_host.exe'
    command=[str(a.cxx),'-std=c++11','-O2','-static','-Wno-unknown-pragmas',
        '-I'+str(experiment/'src'),str(experiment/'src/weather_frame.cpp'),str(ref),str(tb),'-o',str(exe)]
    result=subprocess.run(command,capture_output=True)
    (out/'host_build.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('sequence host compile')
    result=subprocess.run([str(exe)],capture_output=True)
    (out/'host.log').write_bytes(result.stdout+result.stderr)
    if result.returncode or b'WEATHER_SEQUENCE_PASS' not in result.stdout:raise RuntimeError('sequence host verification')
    print('SEQUENCE_HOST_PASS',flush=True)
    shutil.copytree(base/'derain/component',out/'component')
    cfg=(base/'derain/hls_config.cfg').read_text()
    cfg='\n'.join(line for line in cfg.splitlines() if not line.startswith(('tb.file','csim.argv','cosim.argv')))+'\n'
    cfg+='tb.file='+tb.as_posix()+'\ntb.file='+ref.as_posix()+'\n'
    for f in (tb,ref):cfg+='tb.file_cflags='+f.as_posix()+',-std=c++11 -I'+(experiment/'src').as_posix()+'\n'
    (out/'hls_config.cfg').write_text(cfg,encoding='utf-8')
    spec=importlib.util.spec_from_file_location('weather_hls',experiment/'scripts/run_hls.py')
    hls=importlib.util.module_from_spec(spec);spec.loader.exec_module(hls)
    log,step=hls.invoke('cosim',[a.vitis/'bin/vitis-run.bat','--mode','hls','--cosim',
        '--config',out/'hls_config.cfg','--work_dir',out/'component'],out,a.vitis/'settings64.bat',7200)
    text=log.read_text(errors='replace')
    report['step']=step
    report['pass']=step['exit_code']==0 and 'co-simulation finished: PASS' in text and 'WEATHER_SEQUENCE_PASS' in text
except Exception as exc:
    report['error']=repr(exc);print(str(exc),file=sys.stderr)
(out/'run.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
sys.exit(0 if report['pass'] else 1)
