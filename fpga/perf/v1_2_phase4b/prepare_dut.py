"""New TB build: unchanged PL, frozen oracle, only model and TB diagnostics change."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path('E:/HLS/kv260_three_module_v1_2_phase4')
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--build',required=True);parser.add_argument('--protocol',required=True)
args=parser.parse_args();assert args.build.replace('_','').isalnum()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol=ROOT/'phase4b_01'/args.protocol
gate=json.loads((protocol/'gate.json').read_text())
assert gate['gate']=='PASS' and gate['model_sha256']==sha(HERE/'shared_axi_ddr_v2.sv')
old=HERE.parent/'v1_2_system_tb'
subprocess.run([sys.executable,'-B',str(old/'build_system_tb.py'),'--name',args.build],check=True)
out=ROOT/args.build
shutil.copy2(HERE/'shared_axi_ddr_v2.sv',out/'shared_axi_ddr.sv')
tb=(out/'system_tb.sv').read_text()
tb=tb.replace('cycle%1000000==0','cycle%250000==0')
needle='    if(frames>=100) begin'
assert needle in tb
tb=tb.replace(needle,'''    if(frames==6 || frames==8) begin
      $display("SHORT_MULTI_STATE SAMPLES=%0d INTERVAL_MIN=%0d INTERVAL_MAX=%0d INTERVAL_SUM=%0d",frames-frames/2,interval_min,interval_max,interval_sum);
      if(interval_max<=3333333) $display("SHORT_MULTI_FRAME_30FPS_PASS"); else $display("SHORT_MULTI_FRAME_30FPS_FAIL");
    end
'''+needle)
# Expose diagnostic queue/counter snapshots without draining or declaring PASS.
tb=tb.replace('SYSTEM_PROGRESS CYCLE=%0d CNN_DONE=%0d BILINEAR_DONE=%0d CURVE_DONE=%0d',
              'SYSTEM_PROGRESS CYCLE=%0d CNN_DONE=%0d BILINEAR_DONE=%0d CURVE_DONE=%0d')
tb=tb.replace('$fdisplay(progress_file,"%0d,%0d,%0d,%0d",cycle,completed[0],completed[1],completed[2]);',
'''$fdisplay(progress_file,"%0d,%0d,%0d,%0d",cycle,completed[0],completed[1],completed[2]);
      $fflush(progress_file);$fflush(event_file);
      for(integer hp=0;hp<4;hp=hp+1)
        $display("PARTIAL_HP CYCLE=%0d HP=%0d AR=%0d AW=%0d R=%0d W=%0d READ_MAX=%0d WRITE_MAX=%0d AR_STALL=%0d AW_STALL=%0d",cycle,hp,ddr.arcs[hp],ddr.awcs[hp],ddr.rbeats[hp],ddr.wbeats[hp],ddr.rq_max[hp],ddr.wq_max[hp],ddr.ar_stalls[hp],ddr.aw_stalls[hp]);''')
(out/'system_tb.sv').write_text(tb)
manifest=json.loads((out/'source_manifest.json').read_text())
assert manifest['pl_wrapper_sha256']==sha(ROOT/'phase4_pl.v')
assert manifest['pl_wrapper_sha256']=='12c283e2b7dc8e0dc462c307497809f0277552898cecd5e2230f47253554bf39'
manifest.update(ddr_model_sha256=sha(out/'shared_axi_ddr.sv'),generated_tb_sha256=sha(out/'system_tb.sv'),
    phase='4B',protocol_gate=protocol.as_posix(),physical_model='one shared memory; one total service beat/cycle; queued R/W FIFO per HP')
(out/'source_manifest.json').write_text(json.dumps(manifest,indent=2))
print('Prepared v2 DUT build',out)
