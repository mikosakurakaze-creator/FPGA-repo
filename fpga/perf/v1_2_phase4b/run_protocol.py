"""Independent real simulator tests before exposing the v2 model to the DUT."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=Path('E:/HLS/kv260_three_module_v1_2_phase4/phase4b_01')
parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
assert args.name.replace('_','').isalnum()
out=ROOT/args.name;out.mkdir(exist_ok=False)
for source in ('shared_axi_ddr_v2.sv','ddr_v2_protocol_tb.sv'):shutil.copy2(HERE/source,out/source)
(out/'shared_ddr.hex').write_text('30393039303930393039303930393039\n'*2048)
(out/'model.prj').write_text('sv xil_defaultlib "shared_axi_ddr_v2.sv"\nsv xil_defaultlib "ddr_v2_protocol_tb.sv"\n')
prefix='@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\ncall "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n'+f'cd /d "{out}"\n'
(out/'build.cmd').write_text(prefix+'call xelab -prj model.prj xil_defaultlib.ddr_v2_protocol_tb -s ddr_v2_protocol -log compile.log\nexit /b %errorlevel%\n')
records=[]
def execute(command,log):
    with (out/log).open('w') as f:status=subprocess.run(['cmd','/c',str(command)],stdout=f,stderr=subprocess.STDOUT).returncode
    records.append(dict(command=str(command),exit_code=status))
    (out/'exit_codes.json').write_text(json.dumps(records,indent=2))
    return status
assert execute(out/'build.cmd','build_console.log')==0
for ro,wo in [(o,o) for o in (1,2,4,8,16)]+[(1,16),(16,1)]:
    name=f'ro{ro}_wo{wo}'
    (out/(name+'.cmd')).write_text(prefix+f'call xsim ddr_v2_protocol -tclbatch run.tcl -log {name}.log '
        f'-testplusarg "READ_OUTSTANDING={ro}" -testplusarg "WRITE_OUTSTANDING={wo}" -testplusarg "DDR_DELAY=16" -testplusarg "SERVICE_PERIOD=1"\nexit /b %errorlevel%\n')
    (out/'run.tcl').write_text('run all\nquit\n')
    code=execute(out/(name+'.cmd'),name+'_console.log')
    log=(out/(name+'.log')).read_text()
    assert code==0 and f'DDR_V2_PROTOCOL_PASS RO={ro} WO={wo}' in log and 'Fatal:' not in log,(name,code)
    print(name,'PASS',flush=True)
for case,reason in ((1,'illegal size/INCR/4KB'),(2,'WLAST mismatch'),(3,'WSTRB outside valid byte lanes')):
    name=f'negative_{case}'
    (out/(name+'.cmd')).write_text(prefix+f'call xsim ddr_v2_protocol -tclbatch run.tcl -log {name}.log '
        f'-testplusarg "CASE={case}" -testplusarg "READ_OUTSTANDING=4" -testplusarg "WRITE_OUTSTANDING=4"\nexit /b %errorlevel%\n')
    code=execute(out/(name+'.cmd'),name+'_console.log')
    log=(out/(name+'.log')).read_text()
    assert f'Fatal: DDR v2 {reason}' in log and 'DDR_V2_PROTOCOL_PASS' not in log,(name,code)
    print(name,'EXPECTED_REJECTION',code,flush=True)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
(out/'gate.json').write_text(json.dumps(dict(gate='PASS',positive_configurations=7,expected_negative_cases=3,
    model_sha256=sha(out/'shared_axi_ddr_v2.sv'),tb_sha256=sha(out/'ddr_v2_protocol_tb.sv'),exit_codes=records),indent=2))
print('DDR_V2_PROTOCOL_GATE_PASS',flush=True)
