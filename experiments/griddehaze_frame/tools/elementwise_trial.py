"""Verify every non-convolution Golden node; optionally run vendor C simulation/HLS."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from preflight import ROOT, audit, plan, save, sha


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stage',choices=['native','csim','synth'],default='synth')
    p.add_argument('--cxx',default='D:/m/mingw64/bin/g++.exe')
    p.add_argument('--vitis',type=Path,default=Path('D:/vivado/2025.2/Vitis'))
    a=p.parse_args()
    out=a.out.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+',str(out)): raise ValueError('new ASCII path without spaces required')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_result=False,stage=a.stage,steps={},scope='elementwise operator only; no RTL, full PL graph, PS integration or board claim')
    try:
        sources={}
        for folder,name in [('hls','elementwise_top.cpp'),('hls','elementwise_top.hpp'),
                            ('hls','tb_elementwise.cpp'),('src','fixed_math.hpp'),
                            ('tools','elementwise_trial.py'),('tools','preflight.py')]:
            shutil.copy2(ROOT/folder/name,out/name)
            sources[folder+'/'+name]=sha(out/name)
        report['executed_source_sha256']=sources
        m,g,params,_=audit(ROOT/'a_candidate/package')
        memory=plan(g,params,33,47)
        by_id={n['id']:n for n in memory['nodes']}
        gm=json.loads((ROOT/'a_candidate/golden/random/report.json').read_text())
        metas={n['id']:n for n in gm['nodes']}
        blob=(ROOT/'a_candidate/package/parameters.bin').read_bytes()
        op_ids=dict(relu=1,mulcoef=2,add=3,cat=4)
        records=[]; lines=[]
        for n in g['nodes']:
            if n['op'] not in op_ids: continue
            prefix='case'+str(len(records))
            r=by_id[n['id']]; left=by_id[n['inputs'][0]]
            binary=n['op'] in ('add','cat')
            right=by_id[n['inputs'][1]] if binary else None
            co,h,w=r['shape']
            fields=[(out/prefix).as_posix(),op_ids[n['op']],left['shape'][0],
                    right['shape'][0] if binary else 0,co,h,w,left['activation_frac'],
                    right['activation_frac'] if binary else 3,r['activation_frac']]
            lines.append(' '.join(map(str,fields)))
            for key,ident in [('a',n['inputs'][0]),('b',n['inputs'][1] if binary else None),('expected',n['id'])]:
                dest=out/(prefix+'_'+key+'.raw')
                if ident is None: dest.write_bytes(b''); continue
                meta=metas[ident]
                src=ROOT/'a_candidate/golden/random'/('' if ident=='input' else 'nodes')/meta['file']
                if sha(src)!=meta['sha256']: raise ValueError('Golden identity '+ident)
                shutil.copy2(src,dest)
            coefficient=b''
            if n['op']=='mulcoef':
                d=params[n['coefficient']][0]
                coefficient=blob[d['offset']:d['offset']+d['nbytes']]
                if n['coefficient_frac']!=14 or len(coefficient)!=co*2: raise ValueError('coefficient layout')
            (out/(prefix+'_coefficients.raw')).write_bytes(coefficient)
            records.append(dict(id=n['id'],op=n['op'],actual=prefix+'_actual.raw',expected=prefix+'_expected.raw'))
        if len(records)!=208: raise ValueError('expected all 208 elementwise nodes')
        (out/'cases.txt').write_text(str(len(lines))+'\n'+'\n'.join(lines)+'\n',encoding='ascii')
        report.update(bundle_id=m['identity']['bundle_id'],graph_sha256=m['graph_sha256'],
                      input_sha256=metas['input']['sha256'],fixture_sha256={f.name:sha(f) for f in out.glob('*.raw')},
                      cases_sha256=sha(out/'cases.txt'))

        def command(name,cmd):
            start=time.perf_counter()
            print('Running '+name+': '+str(out/(name+'.log')),flush=True)
            with (out/(name+'.log')).open('xb') as log:
                result=subprocess.run(list(map(str,cmd)),cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            log=(out/(name+'.log')).read_text(errors='replace')
            report['steps'][name]=dict(command=list(map(str,cmd)),exit_code=result.returncode,
                                      elapsed_seconds=time.perf_counter()-start,log_sha256=sha(out/(name+'.log')))
            if result.returncode or re.search(r'(?mi)^\s*(ERROR|FATAL)(:|\s)|fatal error:',log):
                raise RuntimeError(name+' failed; see '+str(out/(name+'.log')))
            return log

        def vendor(name,exe,args):
            values=[str(a.vitis/'settings64.bat'),str(exe),*[str(x) for x in args]]
            if any(re.search(r'[\r\n"&|<>^%!]',v) for v in values): raise ValueError('unsafe batch path')
            wrapper=out/(name+'.cmd')
            wrapper.write_text('@echo off\r\nsetlocal\r\nset "PROCESSOR_ARCHITECTURE=AMD64"\r\ncall "'+values[0]+
                               '"\r\nif errorlevel 1 exit /b %errorlevel%\r\ncall '+' '.join('"'+v+'"' for v in values[1:])+
                               '\r\nexit /b %errorlevel%\r\n',encoding='ascii',newline='')
            return command(name,['cmd.exe','/d','/c',wrapper])

        if a.stage=='native':
            exe=out/'test_elementwise.exe'
            command('compile',[a.cxx,'-std=c++11','-O3','-Wall','-Wextra','-Werror','-Wno-unknown-pragmas',
                               '-DGDN_NATIVE_HOST',out/'elementwise_top.cpp',out/'tb_elementwise.cpp','-o',exe])
            test_log=command('native',[exe,out/'cases.txt'])
        else:
            config='\n'.join(['part=xck26-sfvc784-2LV-c','','[hls]','flow_target=vivado','clock=10',
                'syn.top=griddehaze_elementwise_top','syn.file='+(out/'elementwise_top.cpp').as_posix(),
                'syn.file_cflags='+(out/'elementwise_top.cpp').as_posix()+',-std=c++11',
                'tb.file='+(out/'tb_elementwise.cpp').as_posix(),
                'tb.file_cflags='+(out/'tb_elementwise.cpp').as_posix()+',-std=c++11',
                'csim.argv='+(out/'cases.txt').as_posix(),'syn.interface.m_axi_max_widen_bitwidth=128',''])
            (out/'hls_config.cfg').write_text(config,encoding='ascii')
            report['config_sha256']=sha(out/'hls_config.cfg')
            vendor('version',a.vitis/'bin/vitis-run.bat',['--version'])
            test_log=vendor('csim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--csim','--config',out/'hls_config.cfg','--work_dir',out/'component'])
        marker='ALL_ELEMENTWISE_CASES_PASS nodes=208 boundaries=6921'
        if marker not in test_log: raise RuntimeError('missing complete arithmetic PASS marker')
        for r in records:
            r['sha256']=sha(out/r['actual'])
            if r['sha256']!=sha(out/r['expected']): raise RuntimeError('actual mismatch '+r['id'])
        report.update(operator_cases=records,compared_nodes=208,boundary_cases=6921)
        if a.stage=='synth':
            vendor('synth',a.vitis/'bin/v++.bat',['-c','--mode','hls','--config',out/'hls_config.cfg','--work_dir',out/'component'])
            xml=list((out/'component').rglob('griddehaze_elementwise_top_csynth.xml'))
            if len(xml)!=1: raise RuntimeError('missing/ambiguous csynth report')
            tree=ET.parse(xml[0])
            def fields(path):
                node=tree.find(path)
                return {c.tag:c.text for c in node} if node is not None else {}
            report['hls_estimate']=dict(resources=fields('.//AreaEstimates/Resources'),
                available=fields('.//AreaEstimates/AvailableResources'),
                timing=fields('.//PerformanceEstimates/SummaryOfTimingAnalysis'),
                latency=fields('.//PerformanceEstimates/SummaryOfOverallLatency'),report_sha256=sha(xml[0]))
        report['pass_result']=True
    except Exception as e:
        report['error']=repr(e)
        raise
    finally:
        save(out/'result.json',report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('fixture_sha256','operator_cases')},indent=2),flush=True)


if __name__=='__main__': main()
