"""Build/verify the complete PL-scheduled graph source in an immutable workspace."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from preflight import ROOT,audit,save,sha
from emit_model import emit,layout

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stage',choices=['audit','native','csim','synth-only','synth','cosim'],default='audit',
                   help='audit prepares metadata; synth-only skips C/RTL execution; native/csim/synth/cosim run test programs')
    p.add_argument('--cases',nargs='+',default=['random','black','white','channel','impulse','size_4x4','size_32x48','size_34x46'])
    p.add_argument('--cxx',default='D:/m/mingw64/bin/g++.exe')
    p.add_argument('--vitis',type=Path,default=Path('D:/vivado/2025.2/Vitis'))
    a=p.parse_args()
    if a.stage=='cosim':
        p.error('Vendor co-sim is disabled: fixed maximum pointer depths exceed the small testbench allocations. Use tools/frame_rtl_trial.py for bounded independent RTL verification.')
    out=a.out.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+',str(out)): raise ValueError('ASCII output directory without spaces required')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_result=False,stage=a.stage,inference_executed=False,
                scope='metadata_only' if a.stage=='audit' else 'full 320-node HLS graph; not a board or routed-system result',steps={})
    try:
        m,g,params,_=audit(ROOT/'a_candidate/package')
        names=['frame_top.cpp','frame_top.hpp','conv_tile_top.cpp','conv_tile_top.hpp','elementwise_top.cpp','elementwise_top.hpp','tb_frame.cpp']
        for name in names:shutil.copy2(ROOT/'hls'/name,out/name)
        emit(out/'generated_model.hpp')
        if sha(out/'generated_model.hpp')!=sha(ROOT/'hls/generated_model.hpp'):raise RuntimeError('stale frozen model header')
        for name in ['frame_trial.py','emit_model.py','preflight.py']:shutil.copy2(ROOT/'tools'/name,out/name)
        report['source_snapshot_sha256']={name:sha(out/name) for name in names+['generated_model.hpp','frame_trial.py','emit_model.py','preflight.py']}
        shutil.copy2(ROOT/'a_candidate/package/parameters.bin',out/'parameters.bin')
        report.update(bundle_id=m['identity']['bundle_id'],parameters_sha256=sha(out/'parameters.bin'))
        rows=[];comparisons=[];fixtures={}
        for index,name in enumerate(a.cases):
            golden=ROOT/'a_candidate/golden'/name
            meta=json.loads((golden/'report.json').read_text())
            h,w=meta['input_shape'][-2:];prefix=out/('case'+str(index))
            memory=layout(str(prefix)+'_layout.bin',h,w)
            save(Path(str(prefix)+'_memory.json'),memory)
            paths=[]
            for node in meta['nodes']:
                path=golden/('' if node['id']=='input' else 'nodes')/node['file']
                if sha(path)!=node['sha256']:raise RuntimeError('Golden hash '+name+'/'+node['id'])
                paths.append(path.as_posix())
                fixtures[str(path)]=node['sha256']
            Path(str(prefix)+'_paths.txt').write_text('\n'.join(paths)+'\n',encoding='ascii')
            rows.append(' '.join(map(str,[prefix.as_posix(),(golden/'input.raw').as_posix(),str(prefix)+'_layout.bin',str(prefix)+'_paths.txt',h,w,int(index==0)])))
            comparisons.append(dict(case=name,prefix=prefix,meta=meta,golden=golden))
        (out/'cases.txt').write_text((out/'parameters.bin').as_posix()+'\n'+str(len(rows))+'\n'+'\n'.join(rows)+'\n',encoding='ascii')
        report['fixture_sha256']=fixtures
        if a.stage=='audit':
            report.update(pass_result=True,metadata_validated=True,cases=[dict(case=c['case'],height=c['meta']['input_shape'][-2],width=c['meta']['input_shape'][-1]) for c in comparisons],
                          limitations=['No C++ compilation or executable launch.',
                                       'No inference, HLS, RTL or board verification.'])
            return
        def command(name,cmd):
            print('FRAME_STAGE='+name+' LOG='+str(out/(name+'.log')),flush=True)
            start=time.perf_counter()
            with (out/(name+'.log')).open('xb') as log:
                r=subprocess.run(list(map(str,cmd)),cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=7200)
            text=(out/(name+'.log')).read_text(errors='replace')
            report['steps'][name]=dict(command=list(map(str,cmd)),exit_code=r.returncode,seconds=time.perf_counter()-start,log_sha256=sha(out/(name+'.log')))
            if r.returncode or re.search(r'(?mi)^\s*(ERROR|FATAL)(:|\s)|fatal error:',text):raise RuntimeError('stage '+name+' failed')
            return text
        def vendor(name,exe,args):
            values=[str(a.vitis/'settings64.bat'),str(exe),*map(str,args)]
            if any(re.search(r'[\r\n"&|<>^%!]',v) for v in values):raise ValueError('unsafe batch path')
            cmd=out/(name+'.cmd')
            cmd.write_text('@echo off\r\nsetlocal\r\nset "PROCESSOR_ARCHITECTURE=AMD64"\r\ncall "'+values[0]+'"\r\nif errorlevel 1 exit /b %errorlevel%\r\ncall '+' '.join('"'+v+'"' for v in values[1:])+'\r\nexit /b %errorlevel%\r\n',encoding='ascii',newline='')
            return command(name,['cmd.exe','/d','/c',cmd])
        def synthesize():
            vendor('synth',a.vitis/'bin/v++.bat',['-c','--mode','hls','--config',out/'hls_config.cfg','--work_dir',out/'component'])
            xml=list((out/'component').rglob('griddehaze_frame_top_csynth.xml'))
            if len(xml)!=1:raise RuntimeError('synth report absent')
            tree=ET.parse(xml[0])
            def fields(path):
                node=tree.find(path)
                return {c.tag:c.text for c in node} if node is not None else {}
            report['hls_estimate']=dict(resources=fields('.//AreaEstimates/Resources'),timing=fields('.//PerformanceEstimates/SummaryOfTimingAnalysis'),latency=fields('.//PerformanceEstimates/SummaryOfOverallLatency'),report_sha256=sha(xml[0]))
        if a.stage=='native':
            exe=out/'test_frame.exe'
            command('compile',[a.cxx,'-std=c++11','-O3','-Wall','-Wextra','-Werror','-Wno-unknown-pragmas',
                '-DGDN_NATIVE_HOST','-DGDN_FRAME_INTEGRATION',*[out/name for name in ['frame_top.cpp','conv_tile_top.cpp','elementwise_top.cpp','tb_frame.cpp']],'-o',exe])
            log=command('native',[exe,out/'cases.txt'])
        else:
            lines=['part=xck26-sfvc784-2LV-c','','[hls]','flow_target=vivado','clock=10','syn.top=griddehaze_frame_top']
            for name in ['frame_top.cpp','conv_tile_top.cpp','elementwise_top.cpp']:
                lines+=['syn.file='+(out/name).as_posix(),'syn.file_cflags='+(out/name).as_posix()+',-std=c++11 -DGDN_FRAME_INTEGRATION']
            tb_flags='-std=c++11'+(' -DGDN_RTL_TESTBENCH' if a.stage=='cosim' else '')
            lines+=['tb.file='+(out/'tb_frame.cpp').as_posix(),'tb.file_cflags='+(out/'tb_frame.cpp').as_posix()+','+tb_flags,
                    'csim.argv='+(out/'cases.txt').as_posix(),'syn.interface.m_axi_max_widen_bitwidth=128']
            if a.stage=='cosim':lines+=['cosim.argv='+(out/'cases.txt').as_posix(),'cosim.trace_level=none','cosim.tool=xsim']
            (out/'hls_config.cfg').write_text('\n'.join(lines)+'\n',encoding='ascii')
            report['config_sha256']=sha(out/'hls_config.cfg')
            vendor('version',a.vitis/'bin/vitis-run.bat',['--version'])
            if a.stage=='synth-only':
                synthesize()
                report.update(pass_result=True,scope='HLS synthesis estimate without numerical execution',
                              limitations=['No C simulation or RTL co-simulation.',
                                           'No numerical verification of this source revision.',
                                           'No Vivado implementation or board verification.'])
                return
            log=vendor('csim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--csim','--config',out/'hls_config.cfg','--work_dir',out/'component'])
        if f'ALL_FRAME_CASES_PASS cases={len(rows)} negative_tests=11' not in log:raise RuntimeError('incomplete graph test')
        report['inference_executed']=True
        report['executed_source_sha256']=report['source_snapshot_sha256']
        result=[]
        for case in comparisons:
            prefix=case['prefix'];meta=case['meta']
            for i,node in enumerate(meta['nodes']):
                path=Path(str(prefix)+'_node'+str(i)+'.raw')
                if sha(path)!=node['sha256'] or path.stat().st_size!=node['bytes']:raise RuntimeError('node mismatch '+node['id'])
            expected=json.loads((case['golden']/'output.json').read_text())
            actual=Path(str(prefix)+'_output.raw')
            if sha(actual)!=expected['sha256']:raise RuntimeError('output mismatch')
            result.append(dict(case=case['case'],nodes=320,exact=True,output_sha256=sha(actual),memory_sha256=sha(Path(str(prefix)+'_memory.json'))))
        report.update(cases=result,negative_tests=11)
        if a.stage in ('synth','cosim'):
            synthesize()
        if a.stage=='cosim':
            # Keep C-only node snapshots separate from any RTL result files.
            # The RTL run must produce fresh outputs and its own PASS markers.
            for case in comparisons:
                actual=Path(str(case['prefix'])+'_output.raw')
                actual.rename(Path(str(case['prefix'])+'_csim_output.raw'))
            rtl_log=vendor('cosim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--cosim','--config',out/'hls_config.cfg','--work_dir',out/'component'])
            if f'ALL_FRAME_CASES_PASS cases={len(rows)} negative_tests=11' not in rtl_log or 'RTL_TESTBENCH_SCOPE=final_output_and_status_not_per_node' not in rtl_log:
                raise RuntimeError('incomplete RTL final-output test')
            rtl_results=[]
            for case in comparisons:
                actual=Path(str(case['prefix'])+'_output.raw')
                expected=json.loads((case['golden']/'output.json').read_text())
                if not actual.is_file() or actual.stat().st_size!=expected['bytes'] or sha(actual)!=expected['sha256']:
                    raise RuntimeError('RTL output mismatch or absent: '+case['case'])
                rtl_results.append(dict(case=case['case'],final_output_exact=True,output_sha256=sha(actual)))
            reports=list((out/'component').rglob('*cosim.rpt'))
            if not reports or not any('Pass' in p.read_text(errors='replace') for p in reports):raise RuntimeError('RTL co-simulation pass report absent')
            report['rtl_reports']={str(p.relative_to(out)):sha(p) for p in reports}
            report['rtl_results']=rtl_results
            report['rtl_verification_scope']='final output, return status and completion; no RTL per-node evidence'
        report['pass_result']=True
    except Exception as e:
        report['error']=repr(e)
        raise
    finally:
        save(out/'result.json',report)
        print(json.dumps({k:v for k,v in report.items() if k!='fixture_sha256'},indent=2),flush=True)

if __name__=='__main__':main()
