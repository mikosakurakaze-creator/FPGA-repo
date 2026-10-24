"""Build a new isolated legacy+GridDehazeNet system; never edit the seed checkout."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from preflight import ROOT,sha,save
from release_gates import parse_routed_timing,validate_cross_tile


def validate_captured_frames(directory,result):
    """Recheck numerical evidence at release time, not just a saved PASS flag."""
    if not result.get('cold_warm_exact') or len(result.get('frames',[]))!=2:
        raise RuntimeError('New-core cold/warm capture evidence incomplete')
    final=result['expected_nodes'][-1]
    for i in [0,1]:
        actual=directory/f'output_{i}.raw'
        if actual.stat().st_size!=final['bytes'] or sha(actual)!=final['sha256']:
            raise RuntimeError('New-core actual output changed '+str(i))
    simulation=result['steps']['simulation']
    if simulation['exit_code']!=0 or sha(directory/'simulation.log')!=simulation['log_sha256']:
        raise RuntimeError('New-core simulation log changed or failed')
    if result.get('kind')=='post_route_functional':
        negative=directory/'negative_capture_compare.json'
        if sha(negative)!=result.get('negative_capture_sha256'):
            raise RuntimeError('New-core negative comparison record changed')
        if not json.loads(negative.read_text(encoding='utf-8')).get('detected'):
            raise RuntimeError('New-core negative comparison did not detect an error')


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed',type=Path,default=Path('D:/weather_builds/stream_system01'))
    p.add_argument('--legacy-baseline',type=Path,default=Path('D:/weather_builds/board_diag_20261023_signedfix_route_repro01/run.json'),help='actual legacy post-route regression identifying the preserved weather RTL')
    p.add_argument('--frame-synth',type=Path,default=ROOT/'work/frame_synth01')
    p.add_argument('--csim',type=Path,default=ROOT/'work/frame_csim01')
    p.add_argument('--rtl',type=Path)
    p.add_argument('--routed-test',type=Path,help='passed actual post-route physical-system regression; required before bit/XSA export')
    p.add_argument('--legacy-test',type=Path,help='passed post-route legacy board-fixture regression through this same system; required before export')
    p.add_argument('--cross-tile-test',type=Path,help='same-IP 33x47 cold/warm all-node RTL regression; required before export')
    p.add_argument('--cross-tile-golden',type=Path,default=ROOT/'a_candidate/golden/random',help='frozen 33x47 Golden paired with --cross-tile-test')
    p.add_argument('--reference',type=Path,default=Path('C:/Users/wzh16/Desktop/github clone/weather_fpga_integration'))
    p.add_argument('--vivado',type=Path,default=Path('D:/vivado/2025.2/Vivado'))
    p.add_argument('--stage',choices=['create','synth','impl','export'],required=True)
    p.add_argument('--recover-stage-record',action='store_true',help='record an already completed stage after a recorder failure; does not rerun Vivado')
    a=p.parse_args();out=a.out.resolve()
    python_source=Path(__file__).resolve()
    python_source_sha256_at_start=sha(python_source)
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+',str(out)):raise ValueError('Build path must be ASCII without spaces')
    if a.stage=='create' and not a.recover_stage_record:
        # system02 is a historical tile implementation with a different ABI.
        # A familiar VLNV/name is insufficient evidence of the deployed core.
        baseline=json.loads(a.legacy_baseline.read_text(encoding='utf-8'))
        if not baseline.get('pass') or not baseline.get('completed') or baseline.get('kind')!='post_route_functional' or not baseline.get('physical_boundary'):
            raise RuntimeError('Reviewed legacy physical-system baseline absent')
        legacy_rtl=a.seed/'ip/weather/hdl/verilog'
        legacy_hashes={f.name:sha(f) for f in legacy_rtl.iterdir() if f.suffix in ['.v','.dat']}
        if legacy_hashes!=baseline['rtl_sha256']:
            raise RuntimeError('Seed weather IP differs from the reviewed signed-fix baseline; refuse historical tile-core substitution')
        seed_manifest=json.loads((a.seed/'build.json').read_text(encoding='utf-8'))
        for name,expected in seed_manifest['input_files'].items():
            if name.startswith('ip/') and sha(a.seed/name)!=expected:
                raise RuntimeError('Seed input differs from its frozen manifest '+name)
        hls=json.loads((a.frame_synth/'result.json').read_text(encoding='utf-8'))
        csim=json.loads((a.csim/'result.json').read_text(encoding='utf-8'))
        if not hls['pass_result'] or not csim['pass_result'] or not csim['inference_executed']:raise RuntimeError('Missing full graph synthesis/Csim evidence')
        for name in ['frame_top.cpp','frame_top.hpp','conv_tile_top.cpp','conv_tile_top.hpp','elementwise_top.cpp','elementwise_top.hpp','generated_model.hpp']:
            if hls['source_snapshot_sha256'][name]!=csim['executed_source_sha256'][name]:raise RuntimeError('Csim/synthesis revision mismatch '+name)
        out.mkdir(parents=True,exist_ok=False)
        manifest=dict(scope='additive five-core K26 candidate; board acceptance remains external',stages={},input_files={},
                      hls_result_sha256=sha(a.frame_synth/'result.json'),csim_result_sha256=sha(a.csim/'result.json'))
        manifest['legacy_baseline']=dict(report_source=str(a.legacy_baseline.resolve()),report_sha256=sha(a.legacy_baseline),
                                        seed_manifest_sha256=sha(a.seed/'build.json'),weather_rtl_sha256=legacy_hashes,
                                        scope='exact exported RTL identity of reviewed signed-fix system; newly built implementation must be independently regressed')
        def copy_ip(name,source):
            if not (source/'component.xml').is_file():raise RuntimeError('Missing IP '+str(source))
            target=out/'ip'/name;shutil.copytree(source,target)
            for f in target.rglob('*'):
                if f.is_file():manifest['input_files'][f.relative_to(out).as_posix()]=sha(f)
        for name in ['cnn','bilinear','curve','weather']:copy_ip(name,a.seed/'ip'/name)
        copy_ip('griddehaze',a.frame_synth/'component/hls/impl/ip')
        seed=a.seed/'project/weather_system.srcs/sources_1/bd/system/system.bd'
        design=json.loads(seed.read_text(encoding='utf-8'))
        manifest.update(seed_source=str(seed),seed_sha256=sha(seed))
        design['design']['design_info']['gen_directory']='../../../../weather_system.gen/sources_1/bd/system'
        save(out/'system_seed.bd',design)
        manifest['input_files']['system_seed.bd']=sha(out/'system_seed.bd')
        for name in ['protect_weather_signed_dsp.tcl','check_weather_signed_dsp.tcl']:
            shutil.copy2(a.reference/'system'/name,out/name)
            manifest['input_files'][name]=sha(out/name)
        save(out/'build.json',manifest)
    manifest=json.loads((out/'build.json').read_text(encoding='utf-8'))
    for name,expected in manifest['input_files'].items():
        if sha(out/name)!=expected:raise RuntimeError('Build input changed '+name)
    previous={'synth':'create','impl':'synth','export':'impl'}.get(a.stage)
    if previous and not manifest['stages'].get(previous,{}).get('pass'):raise RuntimeError('Previous stage not passed '+previous)
    if a.stage in ['impl','export']:
        if not a.rtl:raise RuntimeError('Explicit independent RTL result required')
        result=json.loads((a.rtl/'result.json').read_text(encoding='utf-8'))
        if not result['pass_result'] or not result['negative_control']:raise RuntimeError('Independent RTL not passed')
        for name,expected in result['rtl_sha256'].items():
            if sha(out/'ip/griddehaze/hdl/verilog'/name)!=expected:raise RuntimeError('Tested RTL differs '+name)
        manifest['rtl_result_sha256']=sha(a.rtl/'result.json')
    if a.stage=='export':
        if not a.cross_tile_test:
            raise RuntimeError('Explicit 33x47 cross-tile RTL evidence required before bit/XSA export')
        cross_tile=validate_cross_tile(a.cross_tile_test,out,a.cross_tile_golden,
                                      ROOT/'a_candidate/package',ROOT)
        manifest['cross_tile_test_result_sha256']=cross_tile['result_sha256']
        manifest['cross_tile_test']=cross_tile
        timing=parse_routed_timing((out/'routed_timing.rpt').read_text(encoding='utf-8',errors='replace'),
                                   (out/'route_status.rpt').read_text(encoding='utf-8',errors='replace'),
                                   (out/'routed_drc.rpt').read_text(encoding='utf-8',errors='replace'))
        timing['timing_report_sha256']=sha(out/'routed_timing.rpt')
        timing['route_status_report_sha256']=sha(out/'route_status.rpt')
        timing['drc_report_sha256']=sha(out/'routed_drc.rpt')
        timing['implementation_tcl_sha256']=sha(out/'impl.tcl')
        impl_stage=manifest.get('stages',{}).get('impl',{})
        if impl_stage.get('python_source_stable') is not True:
            manifest['implementation_provenance_note']='Historical implementation wrapper hash was not recorded; the executed Tcl, routed checkpoint, netlist, and reports are hashed.'
        signoff_path=out/'routed_signoff.json'
        if signoff_path.exists():
            if json.loads(signoff_path.read_text(encoding='utf-8'))!=timing:
                raise RuntimeError('Existing routed timing signoff record differs from current reports')
        else:
            save(signoff_path,timing)
        marker=out/'routed_signoff.pass'
        marker_text='GRID_ROUTED_SIGNOFF_PASS '+sha(signoff_path)+'\n'
        if marker.exists() and marker.read_text(encoding='ascii')!=marker_text:
            raise RuntimeError('Existing routed timing signoff marker is stale')
        if not marker.exists():marker.write_text(marker_text,encoding='ascii',newline='\n')
        manifest['routed_signoff_sha256']=sha(signoff_path)
        source_audit=json.loads((out/'compiled_sources_audit.json').read_text(encoding='utf-8'))
        if not source_audit.get('pass_result') or not source_audit.get('require_synth'):
            raise RuntimeError('Five-core actual synthesis source/ROM audit required before export')
        if set(source_audit['cores'])!={'cnn','bilinear','curve','weather','griddehaze'}:
            raise RuntimeError('Compiled source audit lacks preserved cores')
        for entries in source_audit['cores'].values():
            for entry in entries:
                for field in ['source','generated']:
                    if sha(out/entry[field])!=entry['sha256']:raise RuntimeError('Audited compiled source changed '+entry[field])
        manifest['compiled_sources_audit_sha256']=sha(out/'compiled_sources_audit.json')
        if not a.routed_test:raise RuntimeError('Post-route physical-system regression required before bit/XSA export')
        routed=json.loads((a.routed_test/'result.json').read_text(encoding='utf-8'))
        if not routed['pass_result'] or not routed['negative_control'] or routed['kind']!='post_route_functional' or not routed.get('physical_replay'):
            raise RuntimeError('Routed regression scope or completion insufficient')
        if routed['netlist_sha256']!=sha(out/'system_routed_funcsim.v'):raise RuntimeError('Routed numerical test does not match this implementation')
        validate_captured_frames(a.routed_test,routed)
        manifest['routed_test_result_sha256']=sha(a.routed_test/'result.json')
        if not a.legacy_test:raise RuntimeError('Legacy post-route physical-system regression required before bit/XSA export')
        legacy=json.loads((a.legacy_test/'run.json').read_text(encoding='utf-8'))
        if not legacy.get('pass') or not legacy.get('completed') or legacy.get('kind')!='post_route_functional' or not legacy.get('physical_boundary') or not legacy.get('stalls'):
            raise RuntimeError('Legacy routed regression scope or completion insufficient')
        if legacy.get('full_system_netlist_sha256')!=sha(out/'system_routed_funcsim.v'):
            raise RuntimeError('Legacy regression does not match this implementation')
        frames=legacy.get('frames',[])
        if len(frames)<2 or any(f.get('golden_mismatch')!=0 for f in frames) or any(f.get('task')!=0 for f in frames[:2]):
            raise RuntimeError('Legacy cold/warm board-fixture outputs incomplete')
        for name,expected in legacy['rtl_sha256'].items():
            if sha(out/'ip/weather/hdl/verilog'/name)!=expected:raise RuntimeError('Legacy tested IP differs '+name)
        if sha(a.legacy_test/'simulation.log')!=legacy['simulation_log_sha256']:
            raise RuntimeError('Legacy simulation log changed')
        for frame in frames:
            if sha(a.legacy_test/f"actual_{frame['seq']}.bin")!=frame['sha256']:
                raise RuntimeError('Legacy actual output changed')
        manifest['legacy_test_result_sha256']=sha(a.legacy_test/'run.json')
        for source,name in [(a.routed_test/'result.json','new_core_routed_test.json'),
                            (a.legacy_test/'run.json','legacy_routed_test.json')]:
            target=out/name
            if target.exists() and sha(target)!=sha(source):raise RuntimeError('Release regression record already differs '+name)
            if not target.exists():shutil.copy2(source,target)
    script=out/(a.stage+'.tcl')
    if not a.recover_stage_record:shutil.copy2(ROOT/'system'/(a.stage+'.tcl'),script)
    tcl_sha256_at_start=sha(script)
    cmd=out/('run_'+a.stage+'.cmd')
    cmd.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\ncall "'+str(a.vivado/'settings64.bat')+'"\nif errorlevel 1 exit /b 1\ncall "'+str(a.vivado/'bin/vivado.bat')+'" -mode batch -notrace -source "'+str(script)+'" -log "'+str(out/(a.stage+'_vivado.log'))+'" -journal "'+str(out/(a.stage+'.jou'))+'" -tclargs "'+str(out)+'"\nexit /b %errorlevel%\n',encoding='ascii')
    start=time.perf_counter();print('GRID_SYSTEM_STAGE='+a.stage+' LOG='+str(out/(a.stage+'_console.log')),flush=True)
    if a.recover_stage_record:
        if a.stage!='create' or not (out/'project/weather_system.xpr').is_file() or not (out/'griddehaze_system_preimpl.xsa').is_file():
            raise RuntimeError('Recovery only supports completed create outputs')
        exit_code=None
    else:
        with (out/(a.stage+'_console.log')).open('wb') as f:
            result=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(cmd)],cwd=out,stdout=f,stderr=subprocess.STDOUT)
        exit_code=result.returncode
    log=(out/(a.stage+'_console.log')).read_text(encoding='utf-8',errors='replace')
    passed=(exit_code in [0,None]) and ('GRID_SYSTEM_'+a.stage.upper()+'_PASS') in log and not re.search(r'(?m)^ERROR:',log)
    stage_checks={}
    if passed and a.stage in ['impl','export']:
        try:
            timing=parse_routed_timing((out/'routed_timing.rpt').read_text(encoding='utf-8',errors='replace'),
                                       (out/'route_status.rpt').read_text(encoding='utf-8',errors='replace'),
                                       (out/'routed_drc.rpt').read_text(encoding='utf-8',errors='replace'))
            timing['timing_report_sha256']=sha(out/'routed_timing.rpt')
            timing['route_status_report_sha256']=sha(out/'route_status.rpt')
            timing['drc_report_sha256']=sha(out/'routed_drc.rpt')
            timing['implementation_tcl_sha256']=sha(out/'impl.tcl')
            signoff_path=out/'routed_signoff.json'
            if signoff_path.exists():
                if json.loads(signoff_path.read_text(encoding='utf-8'))!=timing:
                    raise RuntimeError('Existing routed signoff record does not match implementation reports')
            else:
                save(signoff_path,timing)
            marker=out/'routed_signoff.pass'
            marker_text='GRID_ROUTED_SIGNOFF_PASS '+sha(signoff_path)+'\n'
            if marker.exists() and marker.read_text(encoding='ascii')!=marker_text:
                raise RuntimeError('Existing routed timing signoff marker is stale')
            if not marker.exists():marker.write_text(marker_text,encoding='ascii',newline='\n')
            stage_checks['routed_signoff_sha256']=sha(signoff_path)
        except Exception as e:
            passed=False
            stage_checks['routed_signoff_error']=repr(e)
    python_source_sha256_at_end=sha(python_source)
    python_source_stable=python_source_sha256_at_start==python_source_sha256_at_end
    if not python_source_stable:
        passed=False
        stage_checks['python_source_error']='build_grid_system.py changed during this stage'
    tcl_sha256_at_end=sha(script)
    tcl_source_stable=tcl_sha256_at_start==tcl_sha256_at_end
    if not tcl_source_stable:
        passed=False
        stage_checks['tcl_source_error']='Stage Tcl changed while Vivado was running'
    manifest['stages'][a.stage]=dict(pass_result=passed,**{'pass':passed},exit_code=exit_code,seconds=None if a.recover_stage_record else time.perf_counter()-start,
        script_sha256=tcl_sha256_at_end,script_sha256_at_start=tcl_sha256_at_start,script_sha256_at_end=tcl_sha256_at_end,
        python_source_sha256_at_start=python_source_sha256_at_start,python_source_sha256_at_end=python_source_sha256_at_end,
        python_source_stable=python_source_stable,tcl_source_stable=tcl_source_stable,log_sha256=sha(out/(a.stage+'_console.log')),
        recovered_record=a.recover_stage_record,**stage_checks)
    if passed and a.stage in ['synth','impl','export']:
        outputs={'synth':['system_synth.dcp','system_synth_funcsim.v'],'impl':['system_routed.dcp','system_routed_funcsim.v'],'export':['griddehaze_system.bit','griddehaze_system.xsa']}[a.stage]
        manifest['stages'][a.stage]['outputs_sha256']={name:sha(out/name) for name in outputs}
    pending=out/'build.pending.json'
    save(pending,manifest)
    pending.replace(out/'build.json')
    print(json.dumps(manifest['stages'][a.stage],indent=2),flush=True)
    if not passed:raise RuntimeError('System stage failed; see actual log')

if __name__=='__main__':main()
