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
    p.add_argument('--reuse-synth',type=Path,help='Reuse an unchanged completed synthesis; prior failed cosim remains failed')
    p.add_argument('--isolate-null-artifact',action='store_true',help='Temporarily preserve a regular D:/dev/null log file which breaks vendor make')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'pass':False,'stage':a.stage,'board_operations':0,'steps':[],'baseline':BASE}
    def execute(name,command):
        command=[sys.executable,'-E',str(out/'run_windows_desktop.py'),'--',*map(str,command)]
        print('PREPARE_STAGE='+name+' LOG='+str(out/(name+'.log')),flush=True)
        start=time.perf_counter()
        with (out/(name+'.log')).open('xb') as log:
            env=os.environ.copy();env.pop('SHELL',None)
            proc=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
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
                command.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\nset "PATH='+str(a.vitis.parent/'Vivado/gnuwin/bin')+';%PATH%"\ncall "'+str(vals[0])+'"\nif errorlevel 1 exit /b %errorlevel%\ncall '+subprocess.list2cmdline(list(map(str,vals[1:])))+'\nexit /b %errorlevel%\n',encoding='ascii')
                return execute(stage,[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',command])
            if a.reuse_synth:
                old=json.loads((a.reuse_synth/'result.json').read_text())
                step=next(s for s in old['steps'] if s['name']=='synth')
                if step['exit_code'] or sha(a.reuse_synth/'synth.log')!=step['log_sha256']:raise ValueError('Synthesis reuse gate failed')
                for name in ('joint_adapters.cpp','joint_adapters.hpp'):
                    if sha(out/name)!=old['source_sha256'][name] or sha(a.reuse_synth/name)!=sha(out/name):raise ValueError('Changed synthesis input')
                shutil.copytree(a.reuse_synth/'prepare',out/'prepare')
                result['reused_synthesis']={'result':str(a.reuse_synth/'result.json'),'result_sha256':sha(a.reuse_synth/'result.json'),'log_sha256':sha(a.reuse_synth/'synth.log')}
            else:
                vendor('synth',a.vitis/'bin/v++.bat',['-c','--mode','hls','--config',cfg,'--work_dir',out/'prepare'])
            ip=out/'prepare/hls/impl/ip'
            result['component_sha256']=sha(ip/'component.xml')
            result['ip_zips']={f.name:sha(f) for f in ip.glob('*.zip')}
            if a.stage=='cosim':
                null_artifact=Path('D:/dev/null');preserved=out/'preexisting_dev_null.log'
                if a.isolate_null_artifact:
                    if not null_artifact.is_file() or null_artifact.is_symlink() or null_artifact.stat().st_size>4096:
                        raise ValueError('Unexpected /dev/null object; refusing to move it')
                    result['null_artifact_sha256']=sha(null_artifact)
                    shutil.move(str(null_artifact),str(preserved))
                try:
                    text=vendor('cosim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--cosim','--config',cfg,'--work_dir',out/'prepare'])
                finally:
                    if a.isolate_null_artifact and preserved.exists():
                        if null_artifact.exists():shutil.move(str(null_artifact),str(out/'generated_dev_null.log'))
                        shutil.copy2(preserved,null_artifact)
                if 'PREPARE_ALL_PASS frames=1 invalid=1' not in text:raise RuntimeError('Incomplete RTL output comparison')
                reports=list((out/'prepare').rglob('*cosim.rpt'))
                if not reports or not any('Pass' in f.read_text(errors='replace') for f in reports):raise RuntimeError('Missing RTL pass report')
            result['reports']={f.relative_to(out).as_posix():sha(f) for f in (out/'prepare').rglob('*.rpt')}
        result['pass']=True
    except Exception as e:result['error']=str(e);raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
