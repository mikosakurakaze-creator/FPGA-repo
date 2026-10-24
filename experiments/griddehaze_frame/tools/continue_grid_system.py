"""Continue this isolated hardware build and its release gates; never operate Git."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import ROOT,sha,save
from release_gates import validate_cross_tile

p=argparse.ArgumentParser(__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--rtl',type=Path,default=ROOT/'work/frame_rtl05')
p.add_argument('--routed-out',type=Path,required=True)
p.add_argument('--legacy-out',type=Path,required=True)
p.add_argument('--cross-tile-out',type=Path,required=True)
p.add_argument('--artifacts',type=Path,required=True)
p.add_argument('--reference',type=Path,default=Path('C:/Users/wzh16/Desktop/github clone/weather_fpga_integration'))
p.add_argument('--fixture',type=Path,default=Path('C:/Users/wzh16/Desktop/github clone/weather_board_mismatch_20261023'))
p.add_argument('--task1-vectors',type=Path,default=Path('C:/Users/wzh16/Desktop/github clone/weather_fpga_integration/work/stream_rtl01'))
p.add_argument('--vivado',type=Path,default=Path('D:/vivado/2025.2/Vivado'))
p.add_argument('--wait-for-synth',action='store_true')
p.add_argument('--wait-for-cross-tile',action='store_true',help='wait for and adopt an already running, independently validated cross-tile result')
p.add_argument('--cross-tile-timeout-seconds',type=int,default=172800)
p.add_argument('--resume',action='store_true',help='resume only the existing incomplete workflow record')
a=p.parse_args();b=a.build.resolve()
status=b/'workflow.json'
scope='local hardware build, offline regressions and bit/XSA collection; no Git or physical board actions'
if status.exists():
    if not a.resume:raise RuntimeError('Workflow record exists; use --resume only to continue this incomplete local workflow')
    report=json.loads(status.read_text(encoding='utf-8'))
    if report.get('pass_result') or report.get('scope')!=scope:
        raise RuntimeError('Existing workflow is complete or has a different scope')
else:
    if a.resume:raise RuntimeError('No existing workflow record to resume')
    report=dict(pass_result=False,steps=[],scope=scope)
def record():
    pending=b/'workflow.pending.json';save(pending,report);pending.replace(status)
def manifest():return json.loads((b/'build.json').read_text(encoding='utf-8'))
def run(name,script,*arguments):
    source=ROOT/'tools'/script
    dependencies={'build_grid_system.py':['preflight.py','release_gates.py','system/impl.tcl','system/export.tcl'],
                   'frame_rtl_trial.py':['preflight.py','emit_model.py','ddr_fixture.py','system/frame_axi_test.sv','system/axi_bounded_memory.sv'],
                   'audit_grid_sources.py':['preflight.py']}.get(script,[])
    source_files=[source]+[ROOT/item if '/' in item or '\\' in item else ROOT/'tools'/item for item in dependencies]
    source_hashes_start={str(path.relative_to(ROOT)):sha(path) for path in source_files}
    cmd=[sys.executable,'-B',str(source),*map(str,arguments)]
    print('WORKFLOW_STAGE='+name,flush=True);started=time.perf_counter()
    result=subprocess.run(cmd,cwd=ROOT)
    source_hashes_end={str(path.relative_to(ROOT)):sha(path) for path in source_files}
    stable=source_hashes_start==source_hashes_end
    step=dict(name=name,exit_code=result.returncode,seconds=time.perf_counter()-started,
              script_sha256_at_start=source_hashes_start[str(source.relative_to(ROOT))],
              script_sha256_at_end=source_hashes_end[str(source.relative_to(ROOT))],
              source_hashes_at_start=source_hashes_start,source_hashes_at_end=source_hashes_end,
              source_snapshot_stable=stable)
    report['steps'].append(step)
    record()
    if result.returncode:raise RuntimeError('Workflow stage failed '+name)
    if not stable:raise RuntimeError('A workflow source changed while stage ran: '+name)
try:
    prior={step['name']:step for step in report.get('steps',[])}
    output_steps=[('new_core_routed_regression',a.routed_out),('legacy_routed_regression',a.legacy_out),
                  ('cross_tile_regression',a.cross_tile_out),('collect_local_board_artifacts',a.artifacts)]
    cross_tile_done=prior.get('cross_tile_regression',{}).get('exit_code')==0
    if not cross_tile_done and a.cross_tile_out.exists():
        if not a.wait_for_cross_tile:
            raise RuntimeError('Refuse an unrecorded existing cross-tile directory without --wait-for-cross-tile')
        if not 60<=a.cross_tile_timeout_seconds<=259200:
            raise ValueError('Cross-tile wait timeout must be 60..259200 seconds')
        result_path=a.cross_tile_out/'result.json'
        deadline=time.monotonic()+a.cross_tile_timeout_seconds
        print('WORKFLOW_WAIT=existing_cross_tile_result',flush=True)
        while not result_path.is_file():
            if time.monotonic()>=deadline:
                raise RuntimeError('Timed out waiting for the existing cross-tile regression')
            time.sleep(5)
        evidence=validate_cross_tile(a.cross_tile_out,b,ROOT/'a_candidate/golden/random',
                                     ROOT/'a_candidate/package',ROOT)
        result=json.loads(result_path.read_text(encoding='utf-8'))
        elapsed=sum(step.get('seconds',0.0) for step in result.get('steps',{}).values())
        adopted=dict(name='cross_tile_regression',exit_code=0,seconds=elapsed,
                     adopted_existing_result=True,result_sha256=sha(result_path),
                     source_hashes_at_start=result.get('test_source_sha256',{}),
                     source_hashes_at_end=result.get('test_source_sha256',{}),
                     source_snapshot_stable=True,validated_evidence=evidence)
        report['steps'].append(adopted)
        record()
        prior['cross_tile_regression']=adopted
    for step_name,path in output_steps:
        done=prior.get(step_name,{}).get('exit_code')==0
        if path.exists() and not done:
            if step_name=='cross_tile_regression' and a.wait_for_cross_tile:
                continue
            raise RuntimeError('Refuse an unrecorded partial output; inspect before resuming '+str(path))
        if done and not path.exists():raise RuntimeError('Recorded completed output is missing '+str(path))
    if not manifest().get('legacy_baseline'):raise RuntimeError('Reviewed current legacy-core identity missing')
    record()
    if a.wait_for_synth:
        print('WORKFLOW_WAIT=existing_synthesis',flush=True);started=time.perf_counter()
        while 'synth' not in manifest()['stages']:
            if time.perf_counter()-started>10800:raise RuntimeError('Existing synthesis wait exceeded three hours')
            time.sleep(5)
    if not manifest()['stages'].get('synth',{}).get('pass'):raise RuntimeError('System synthesis is not passed')
    if 'compiled_sources' in prior:
        audit_path=b/'compiled_sources_audit.json'
        source_audit=json.loads(audit_path.read_text(encoding='utf-8'))
        if prior['compiled_sources'].get('exit_code')!=0 or not source_audit.get('pass_result') or not source_audit.get('require_synth'):
            raise RuntimeError('Cannot resume: previous compiled-source audit is not valid')
    else:
        run('compiled_sources','audit_grid_sources.py','--build',b,'--out',b/'compiled_sources_audit.json','--require-synth')
    if prior.get('cross_tile_regression',{}).get('exit_code')!=0:
        run('cross_tile_regression','frame_rtl_trial.py','--synth',ROOT/'work/frame_synth01','--case','random',
            '--max-frame-cycles','500000000','--out',a.cross_tile_out,'--vivado',a.vivado)
    elif not (a.cross_tile_out/'result.json').is_file():raise RuntimeError('Recorded cross-tile result is missing')
    if not manifest()['stages'].get('impl',{}).get('pass'):
        run('implementation','build_grid_system.py','--stage','impl','--out',b,'--rtl',a.rtl,'--vivado',a.vivado)
    if prior.get('new_core_routed_regression',{}).get('exit_code')!=0:
        run('new_core_routed_regression','frame_rtl_trial.py','--synth',ROOT/'work/frame_synth01',
            '--physical-system',b/'system_routed_funcsim.v','--netlist-kind','post_route_functional',
            '--out',a.routed_out,'--vivado',a.vivado)
    elif not (a.routed_out/'result.json').is_file():raise RuntimeError('Recorded new-core routed result is missing')
    if prior.get('legacy_routed_regression',{}).get('exit_code')!=0:
        run('legacy_routed_regression','legacy_path_trial.py','--reference',a.reference,'--fixture',a.fixture,
            '--rtl',b/'ip/weather/hdl/verilog','--physical-system',b/'system_routed_funcsim.v',
            '--physical-kind','post_route_functional','--output',a.legacy_out,'--vivado',a.vivado,
            '--continuous-reads','--task1-vectors',a.task1_vectors)
    elif not (a.legacy_out/'run.json').is_file():raise RuntimeError('Recorded legacy routed result is missing')
    if prior.get('export_bit_xsa',{}).get('exit_code')!=0:
        run('export_bit_xsa','build_grid_system.py','--stage','export','--out',b,'--rtl',a.rtl,
            '--cross-tile-test',a.cross_tile_out,'--routed-test',a.routed_out,
            '--legacy-test',a.legacy_out,'--vivado',a.vivado)
    elif not manifest().get('stages',{}).get('export',{}).get('pass'):raise RuntimeError('Recorded export did not pass')
    if prior.get('collect_local_board_artifacts',{}).get('exit_code')!=0:
        run('collect_local_board_artifacts','collect_board_artifacts.py','--build',b,'--out',a.artifacts)
    report.update(pass_result=True,artifacts=str(a.artifacts.resolve()),board_execution=False)
    print('WORKFLOW_COMPLETE local_hardware_candidate=true board_execution=false',flush=True)
except Exception as e:
    report['error']=repr(e);raise
finally:record()
