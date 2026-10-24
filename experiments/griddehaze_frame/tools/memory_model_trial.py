"""Exercise the 128-bit PS-side test RAM lane and ID behavior independently."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from preflight import ROOT,sha,save
p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
for name in ['axi_bounded_memory.sv','axi_memory_selftest.sv']:shutil.copy2(ROOT/'system'/name,out/name)
(out/'selftest.prj').write_text('sv xil_defaultlib "axi_bounded_memory.sv"\nsv xil_defaultlib "axi_memory_selftest.sv"\n',encoding='ascii')
(out/'run.tcl').write_text('run all\nquit\n',encoding='ascii')
(out/'run.cmd').write_text('@echo off\nsetlocal\ncall "D:/vivado/2025.2/Vivado/settings64.bat"\ncall "D:/vivado/2025.2/Vivado/bin/xelab.bat" xil_defaultlib.gdn_memory_selftest -prj selftest.prj -s gdn_memory_selftest\nif errorlevel 1 exit /b 1\ncall "D:/vivado/2025.2/Vivado/bin/xsim.bat" gdn_memory_selftest -tclbatch run.tcl\nexit /b %errorlevel%\n',encoding='ascii')
with (out/'simulation.log').open('wb') as f:r=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(out/'run.cmd')],cwd=out,stdout=f,stderr=subprocess.STDOUT)
log=(out/'simulation.log').read_text(encoding='utf-8',errors='replace')
passed=r.returncode==0 and 'GDN_MEMORY_SELFTEST_PASS' in log and 'Fatal:' not in log and 'ERROR:' not in log
result=dict(pass_result=passed,kind='test_memory_lane_selftest_not_accelerator',exit_code=r.returncode,log_sha256=sha(out/'simulation.log'),source_sha256={f.name:sha(f) for f in out.glob('*.sv')})
save(out/'result.json',result);print(json.dumps(result,indent=2))
if not passed:raise RuntimeError('memory model self-test failed')
