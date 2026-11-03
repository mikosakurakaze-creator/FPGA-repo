"""Validate the burst prepare candidate against the locked scalar implementation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from build_system import BASE, locked

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stage',choices=['native','synth','cosim'],required=True)
    p.add_argument('--vitis',type=Path,default=Path('D:/vivado/2025.2/Vitis'))
    p.add_argument('--compiler',type=Path,default=Path('D:/m/mingw64/bin/g++.exe'))
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'pass':False,'stage':a.stage,'board_operations':0,'steps':[],'baseline':BASE}
    def execute(name,command):
        command=[sys.executable,'-E',str(out/'run_windows_desktop.py'),'--',*map(str,command)]
        print('PREPARE_STAGE='+name+' LOG='+str(out/(name+'.log')),flush=True)
        start=time.perf_counter()
        with (out/(name+'.log')).open('xb') as log:
            proc=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        text=(out/(name+'.log')).read_text(errors='replace')
        result['steps'].append({'name':name,'command':command,'exit_code':proc.returncode,'seconds':time.perf_counter()-start,'log_sha256':sha(out/(name+'.log'))})
        if proc.returncode or re.search(r'(?mi)^\s*(ERROR|FATAL):|fatal error:',text):
            raise RuntimeError(name+' failed: '+text[-2500:])
        return text
    try:
        for name in ('joint_adapters.cpp','joint_adapters.hpp'):shutil.copy2(ROOT/'hls'/name,out/name)
        shutil.copy2(ROOT/'tests/tb_prepare.cpp',out/'tb_prepare.cpp')
        (out/'frozen').mkdir()
        for name in ('joint_adapters.cpp','joint_adapters.hpp'):
            (out/'frozen'/name).write_bytes(locked(BASE,'fpga/joint_lowlight_compact_d/hls/'+name))
        (out/'run_windows_desktop.py').write_bytes(locked('d8880cce7241628f5472a36802b1791e85935e27','tools/run_windows_desktop.py'))
        shutil.copy2(__file__,out/'check_prepare.py')
        result['source_sha256']={f.relative_to(out).as_posix():sha(f) for f in out.rglob('*') if f.is_file()}
        if a.stage=='native':
            execute('compile',[a.compiler,'-std=c++14','-O2','-Wno-unknown-pragmas','-I'+str(a.vitis/'include'),out/'joint_adapters.cpp',out/'tb_prepare.cpp','-o',out/'test_prepare.exe'])
            text=execute('native',[out/'test_prepare.exe'])
            if 'PREPARE_ALL_PASS frames=3 invalid=1' not in text:raise RuntimeError('Incomplete native validation')
            result['frames']=3;result['compared_scalars']=3*(2*2747520+19080)
        else:
            cfg=out/'hls_config.cfg'
            lines=['part=xck26-sfvc784-2LV-c','[hls]','flow_target=vivado','clock=10',
                'syn.top=joint_rgb8_prepare','syn.file='+(out/'joint_adapters.cpp').as_posix(),
                'tb.file='+(out/'tb_prepare.cpp').as_posix(),
                'cosim.argv=--rtl','cosim.tool=xsim','cosim.trace_level=none',
                'syn.interface.m_axi_max_widen_bitwidth=128','package.output.format=ip_catalog']
            cfg.write_text('\n'.join(lines)+'\n',encoding='ascii')
            def vendor(stage,exe,args):
                command=out/(stage+'.cmd')
                vals=[a.vitis/'settings64.bat',exe,*args]
                if any(re.search(r'[\r\n"&|<>^%!]',str(v)) for v in vals):raise ValueError('Unsafe vendor path')
                command.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\nset "PATH='+str(a.vitis.parent/'Vivado/gnuwin/bin')+';%PATH%"\ncall "'+str(vals[0])+'"\nif errorlevel 1 exit /b %errorlevel%\ncall '+' '.join('"'+str(v)+'"' for v in vals[1:])+'\nexit /b %errorlevel%\n',encoding='ascii')
                return execute(stage,[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',command])
            vendor('synth',a.vitis/'bin/v++.bat',['-c','--mode','hls','--config',cfg,'--work_dir',out/'prepare'])
            if a.stage=='cosim':
                text=vendor('cosim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--cosim','--config',cfg,'--work_dir',out/'prepare'])
                if 'PREPARE_ALL_PASS frames=2 invalid=1' not in text:raise RuntimeError('Incomplete RTL output comparison')
                reports=list((out/'prepare').rglob('*cosim.rpt'))
                if not reports or not any('Pass' in f.read_text(errors='replace') for f in reports):raise RuntimeError('Missing RTL pass report')
            result['reports']={f.relative_to(out).as_posix():sha(f) for f in (out/'prepare').rglob('*.rpt')}
        result['pass']=True
    except Exception as e:result['error']=str(e);raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
