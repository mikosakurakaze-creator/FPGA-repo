"""Simulate unchanged HLS RTL with bounded AXI memory and real AXI-Lite writes.

This independent test supplements vendor co-sim; it does not change IP RTL.
Run through run_windows_desktop.py, after memory-heavy synthesis has finished.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--base',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--vivado',type=Path,required=True)
p.add_argument('--cxx',type=Path,required=True)
p.add_argument('--experiment',default='onchip_frame',choices=('onchip_frame','stream_frame'))
p.add_argument('--full-frame',action='store_true',help='also test both models at 720x1280; enforce 30fps cycle budget without injected stalls')
a=p.parse_args();root=Path(__file__).resolve().parents[1];out=a.output.resolve()
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
report={'pass':False,'verification_kind':'independent_axi_rtl',
        'scope':'unchanged packaged RTL, AXI-Lite task/shape switches and independent stalled DDR memory'}
if not json.loads((a.base/'run.json').read_text())['pass']:raise RuntimeError('primary HLS not passed')
out.mkdir(parents=True,exist_ok=False)
def run(command,name):
    path=out/(name+'.log')
    with path.open('wb') as log_file:
        result=subprocess.run([str(x) for x in command],cwd=out,stdout=log_file,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(name+' failed; see log')
    return path.read_text(errors='replace')
try:
    src=root/'experiments'/a.experiment/'src'
    rtl=a.base/'derain/component/hls/impl/ip/hdl/verilog'
    report['rtl_sha256']={f.name:sha(f) for f in rtl.iterdir() if f.is_file()}
    report['test_source_sha256']={str(f.relative_to(root)):sha(f) for f in
        (root/'system/rtl_memory_test.sv',root/'system/make_rtl_vectors.cpp',src/'weather_kernel_reference.cpp',src/'params_derain.h',src/'params_dehaze.h')}
    for f in rtl.iterdir():
        if f.is_file():shutil.copy2(f,out/f.name)
    for name in ('rtl_memory_test.sv','make_rtl_vectors.cpp'):shutil.copy2(root/'system'/name,out/name)
    run([a.cxx,'-std=c++11','-O2','-static','-I'+str(src),src/'weather_kernel_reference.cpp',
         out/'make_rtl_vectors.cpp','-o',out/'make_rtl_vectors.exe'],'vector_build')
    run([out/'make_rtl_vectors.exe']+(['--full-frame'] if a.full_frame else []),'vectors')
    top=(out/'weather_frame_top.v').read_text()
    ports=[]
    for direction,width,name in re.findall(r'^(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',top,re.M):
        if width:
            if '_ADDR_WIDTH' in width:bits=7 if name.startswith('s_axi') else 64
            elif '_DATA_WIDTH' in width:bits=32
            elif '_WSTRB_WIDTH' in width:bits=4
            elif '_WIDTH' in width:bits=1
            else:bits=int(re.search(r'\d+',width).group())+1
            width='['+str(bits-1)+':0]' if bits>1 else ''
        ports.append((name,'logic '+width+' '+name+';'))
    if len(ports)!=110:raise RuntimeError('unexpected port inventory: '+str(len(ports)))
    tb=(out/'rtl_memory_test.sv').read_text().replace('@PORTS@','\n'.join(v for k,v in ports))
    tb=tb.replace('@CONNECTIONS@',',\n'.join('.'+k+'('+k+')' for k,v in ports))
    if a.full_frame:tb='`define WEATHER_FULL_FRAME\n'+tb
    (out/'weather_rtl_test.sv').write_text(tb)
    project=''.join('verilog xil_defaultlib "'+f.name+'"\n' for f in sorted(out.glob('*.v')))
    project+='sv xil_defaultlib "weather_rtl_test.sv"\n'
    (out/'rtl.prj').write_text(project)
    (out/'run.tcl').write_text('run all\nquit\n')
    cmd=out/'simulate.cmd'
    cmd.write_text('@echo off\nsetlocal\ncall "'+str(a.vivado/'settings64.bat')+'"\n'
        'call "'+str(a.vivado/'bin/xelab.bat')+'" xil_defaultlib.weather_rtl_test -prj rtl.prj -L unisims_ver -L xpm -relax -s weather_rtl_test\n'
        'if errorlevel 1 exit /b 1\ncall "'+str(a.vivado/'bin/xsim.bat')+'" weather_rtl_test -tclbatch run.tcl\nexit /b %errorlevel%\n')
    print('INDEPENDENT_RTL_START '+str(out),flush=True)
    log=run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',cmd],'simulation')
    report['frames']=re.findall(r'WEATHER_RTL_FRAME_PASS[^\r\n]*',log)
    expected_frames=9 if a.full_frame else 7
    report['pass']=('WEATHER_RTL_SEQUENCE_PASS frames='+str(expected_frames)) in log and len(report['frames'])==expected_frames and 'Fatal:' not in log
    report['full_frame_performance']=a.full_frame
    if a.full_frame:
        report['performance_frames']=[s for s in report['frames'] if 'shape=720x1280' in s]
        report['performance_budget_cycles']=3333333
        report['performance_scope']='core with independent DDR model without injected stalls; not board FPS'
    report['simulation_log_sha256']=sha(out/'simulation.log')
    if report['pass']:
        original=(out/'golden_0.hex').read_text()
        lines=original.splitlines();lines[0]=format(int(lines[0],16)^1,'04x')
        (out/'golden_0.hex').write_text('\n'.join(lines)+'\n')
        try:
            result=subprocess.run([str(a.vivado/'bin/xsim.bat'),'weather_rtl_test','-tclbatch','run.tcl'],
                cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            (out/'negative_control.log').write_bytes(result.stdout)
            negative=result.stdout.decode(errors='replace')
            report['negative_control']=('mismatch case=0 i=0' in negative and
                'WEATHER_RTL_SEQUENCE_PASS' not in negative)
        finally:
            (out/'golden_0.hex').write_text(original)
        report['pass']=report['pass'] and report['negative_control']
except Exception as exc:
    report['error']=repr(exc);print(exc,file=sys.stderr)
(out/'run.json').write_text(json.dumps(report,indent=2)+'\n')
print('INDEPENDENT_RTL_PASS='+str(report['pass']),flush=True)
sys.exit(0 if report['pass'] else 1)
