"""Launch the Vitis Python build with explicit local inputs and retained logs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--xsa',type=Path,required=True)
p.add_argument('--workspace',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--vitis',type=Path,required=True)
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
os.environ['WEATHER_XSA']=str(a.xsa.resolve())
os.environ['WEATHER_SW_WORKSPACE']=str(a.workspace.resolve())
os.environ['WEATHER_SOURCE_ROOT']=str(root)
spec=importlib.util.spec_from_file_location('weather_hls',root/'experiments/onchip_frame/scripts/run_hls.py')
hls=importlib.util.module_from_spec(spec);spec.loader.exec_module(hls)
# The vendor Python client decodes its server's cmd.exe output as UTF-8.
# A missing optional min_sdk emits a localized warning before the port banner.
# Select UTF-8 for this child console only; do not change Windows locale/install.
entry=out/'vitis_utf8.cmd'
entry.write_text('@echo off\nchcp 65001 >nul\ncall "'+str(a.vitis/'bin/vitis.bat')
                 +'" -s "'+str(root/'tools/build_standalone.py')+'"\nexit /b %errorlevel%\n',encoding='utf-8')
log,step=hls.invoke('standalone',[entry],
                    out,a.vitis/'settings64.bat',7200)
step['pass']=step['exit_code']==0 and 'WEATHER_STANDALONE_BUILD_PASS' in log.read_text(errors='replace')
(out/'run.json').write_text(json.dumps(step,indent=2)+'\n',encoding='utf-8')
sys.exit(0 if step['pass'] else 1)
