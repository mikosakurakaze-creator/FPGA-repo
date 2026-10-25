"""Run the D candidate's necessary Host/HLS checks in a fresh build directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from emit_parameters import emit

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--package',type=Path,default=Path('D:/weather_builds/compact_d_numeric01/package'))
    p.add_argument('--golden',type=Path,default=Path('D:/weather_builds/compact_d_numeric01/golden'))
    p.add_argument('--stage',choices=['prepare','native','csim','synth','cosim'],required=True)
    p.add_argument('--cases',nargs='+',default=['random_8x8','random_8x8','random_33x47','random_1x1','random_1x7','random_7x1','random_2x3','black','white','red','green','blue'])
    p.add_argument('--vitis',type=Path,default=Path('D:/vivado/2025.2/Vitis'))
    p.add_argument('--compiler',type=Path,default=Path('D:/m/mingw64/bin/g++.exe'))
    p.add_argument('--clock-ns',type=float,default=5.0)
    a=p.parse_args()
    out=a.out.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+',str(out)):
        raise ValueError('Use a tool build path without spaces or non-ASCII characters')
    out.mkdir(parents=True,exist_ok=False)
    result=dict(pass_result=False,stage=a.stage,clock_ns=a.clock_ns,steps={},scope='D only; no board measurement')
    try:
        for name in ['compact_d.cpp','compact_d.hpp','test_compact_d.cpp']:
            shutil.copy2(ROOT/'hls'/name,out/name)
        result['parameters']=emit(a.package,out/'generated_parameters.hpp')
        result['source_sha256']={f.name:sha(f) for f in sorted(out.iterdir()) if f.is_file()}
        case_lines=[]; fixtures={}
        for i,name in enumerate(a.cases):
            folder=(a.golden/name).resolve()
            meta=json.loads((folder/'report.json').read_text())
            if meta['bundle_id']!=result['parameters']['bundle_id']:
                raise ValueError('Golden bundle mismatch')
            h,w=meta['shape'][-2:]
            if sha(folder/'input.i16')!=meta['input_i16_sha256']:
                raise ValueError('Golden input mismatch')
            for node in meta['nodes']:
                if node['file'] is None or sha(folder/node['file'])!=node['sha256']:
                    raise ValueError('Incomplete or changed node Golden')
            case_lines.append(f'{h} {w} {(folder/"input.i16").as_posix()} {folder.as_posix()} {(out/("actual_"+str(i))).as_posix()}')
            fixtures[name]=dict(report_sha256=sha(folder/'report.json'),input_sha256=meta['input_i16_sha256'],output_sha256=meta['nodes'][-1]['sha256'])
        (out/'cases.txt').write_text(str(len(case_lines))+'\n'+'\n'.join(case_lines)+'\n',encoding='ascii',newline='\n')
        result['fixtures']=fixtures
        if a.stage=='prepare':
            result['pass_result']=True
            return

        def execute(name,command):
            print('D_STAGE='+name+' LOG='+str(out/(name+'.log')),flush=True)
            start=time.perf_counter()
            with (out/(name+'.log')).open('xb') as log:
                completed=subprocess.run(list(map(str,command)),cwd=out,stdout=log,stderr=subprocess.STDOUT)
            result['steps'][name]=dict(command=list(map(str,command)),exit_code=completed.returncode,seconds=time.perf_counter()-start,log_sha256=sha(out/(name+'.log')))
            text=(out/(name+'.log')).read_text(encoding='utf-8',errors='replace')
            if completed.returncode or re.search(r'(?mi)^\s*(ERROR|FATAL):|fatal error:',text):
                raise RuntimeError(name+' failed; stop and review '+str(out/(name+'.log')))
            return text

        def vendor(name,exe,args):
            paths=[str(a.vitis/'settings64.bat'),str(exe),*map(str,args)]
            if any(re.search(r'[\r\n"&|<>^%!]',v) for v in paths):
                raise ValueError('Unsafe tool argument')
            command=out/(name+'.cmd')
            vivado_root = a.vitis.parent / 'Vivado'
            command.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\nset "PATH='+str(vivado_root/'gnuwin'/'bin')+';%PATH%"\ncall "'+paths[0]+'"\nif errorlevel 1 exit /b %errorlevel%\ncall '+' '.join('"'+v+'"' for v in paths[1:])+'\nexit /b %errorlevel%\n',encoding='ascii',newline='\n')
            return execute(name,[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',command])

        if a.stage=='native':
            exe=out/'test_compact_d.exe'
            execute('compile',[a.compiler,'-std=c++14','-O2','-Wno-unknown-pragmas','-I'+str(a.vitis/'include'),out/'compact_d.cpp',out/'test_compact_d.cpp','-o',exe])
            text=execute('native',[exe,out/'cases.txt'])
            if f'D_ALL_CASES_PASS frames={len(case_lines)} invalid=3' not in text:
                raise RuntimeError('Incomplete Host execution')
            result['verification']='all22_node_host_exact'
        else:
            tb_flags='-std=c++11'+(' -DCOMPACT_D_RTL_TEST' if a.stage=='cosim' else '')
            clock_text = str(int(a.clock_ns)) if float(a.clock_ns).is_integer() else str(a.clock_ns)
            lines=['part=xck26-sfvc784-2LV-c','[hls]','flow_target=vivado',f'clock={clock_text}',
                   'syn.top=compact_d_top','syn.file='+(out/'compact_d.cpp').as_posix(),
                   'syn.file_cflags='+(out/'compact_d.cpp').as_posix()+',-std=c++11',
                   'tb.file='+(out/'test_compact_d.cpp').as_posix(),
                   'tb.file_cflags='+(out/'test_compact_d.cpp').as_posix()+','+tb_flags,
                   'csim.argv='+(out/'cases.txt').as_posix(),
                   'syn.interface.m_axi_max_widen_bitwidth=128',
                   'package.output.format=ip_catalog']
            if a.stage=='cosim':
                lines+=['cosim.argv='+(out/'cases.txt').as_posix(),'cosim.tool=xsim','cosim.trace_level=none']
            (out/'hls_config.cfg').write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
            if a.stage=='csim':
                text=vendor('csim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--csim','--config',out/'hls_config.cfg','--work_dir',out/'component'])
                if f'D_ALL_CASES_PASS frames={len(case_lines)} invalid=3' not in text:
                    raise RuntimeError('Incomplete vendor C simulation')
                result['verification']='all22_node_csim_exact'
            else:
                vendor('synth',a.vitis/'bin/v++.bat',['-c','--mode','hls','--config',out/'hls_config.cfg','--work_dir',out/'component'])
                xml=out/'component/hls/syn/report/compact_d_top_csynth.xml'
                tree=ET.parse(xml)
                def fields(path):
                    node=tree.find(path)
                    return {c.tag:c.text for c in node} if node is not None else {}
                result['hls_estimate']=dict(resources=fields('.//AreaEstimates/Resources'),timing=fields('.//PerformanceEstimates/SummaryOfTimingAnalysis'),latency=fields('.//PerformanceEstimates/SummaryOfOverallLatency'),report_sha256=sha(xml))
                if a.stage=='cosim':
                    text=vendor('cosim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--cosim','--config',out/'hls_config.cfg','--work_dir',out/'component'])
                    if f'D_ALL_CASES_PASS frames={len(case_lines)} invalid=3' not in text:
                        raise RuntimeError('Incomplete RTL execution')
                    reports=list((out/'component').rglob('*cosim.rpt'))
                    if not reports or not any('Pass' in f.read_text(errors='replace') for f in reports):
                        raise RuntimeError('Missing vendor RTL pass report')
                    result['verification']='rtl_final_output_status_bounds'
                    result['rtl_reports']={f.relative_to(out).as_posix():sha(f) for f in reports}
        if a.stage in ('native','csim','cosim'):
            for i,name in enumerate(a.cases):
                actual=out/f'actual_{i}.i16'
                if sha(actual)!=fixtures[name]['output_sha256']:
                    raise RuntimeError('Actual file differs from A Golden')
            result['frames']=len(a.cases)
        result['pass_result']=True
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        save(out/'result.json',result)
        print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
