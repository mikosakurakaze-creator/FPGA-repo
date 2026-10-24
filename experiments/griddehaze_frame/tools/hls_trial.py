"""Vendor C simulation and synthesis of the convolution tile only, in a new directory."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from preflight import ROOT, audit, plan, save, sha


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--vitis',type=Path,default=Path('D:/vivado/2025.2/Vitis'))
    p.add_argument('--stage',choices=['csim','synth'],default='synth')
    a=p.parse_args()
    out=a.out.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_:/\\.\-]+',str(out)): raise ValueError('new ASCII directory without spaces required')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_result=False,scope='single reusable conv/deconv tile only; no full-network HLS/RTL/implementation/board claim',steps={})
    try:
        sources={}
        for name in ('conv_tile_top.cpp','conv_tile_top.hpp','tb_conv_tile.cpp'):
            shutil.copy2(ROOT/'hls'/name,out/name)
            sources[name]=sha(out/name)
        report['executed_source_sha256']=sources
        m,g,params,_=audit(ROOT/'a_candidate/package')
        memory=plan(g,params,33,47)
        by_id={r['id']:r for r in memory['nodes']}
        nodes=g['nodes']
        chosen=[next(n for n in nodes if n['id']=='conv_in'),
                next(n for n in nodes if n['op']=='conv' and n['stride']==[2,2]),
                max((n for n in nodes if n['op']=='conv' and n['kernel_size']==[1,1]),key=lambda n:by_id[n['inputs'][0]]['shape'][0]),
                next(n for n in nodes if n['op']=='deconv'),
                next(n for n in nodes if n['op']=='deconv' and by_id[n['id']]['shape'][1:]==[33,47])]
        gm=json.loads((ROOT/'a_candidate/golden/random/report.json').read_text())
        metas={n['id']:n for n in gm['nodes']}
        blob=(ROOT/'a_candidate/package/parameters.bin').read_bytes()
        cases=[]; expected=[]
        for i,n in enumerate(chosen):
            prefix='case'+str(i)
            ci,ih,iw=by_id[n['inputs'][0]]['shape']; co,oh,ow=by_id[n['id']]['shape']
            cases.append(' '.join(str(v) for v in ((out/prefix).as_posix(),ci,co,ih,iw,oh,ow,n['kernel_size'][0],n['stride'][0],n['padding'][0],int(n['op']=='deconv'))))
            for key,ident in (('input',n['inputs'][0]),('expected',n['id'])):
                meta=metas[ident]
                src=ROOT/'a_candidate/golden/random'/('nodes' if ident!='input' else '')/meta['file']
                assert sha(src)==meta['sha256']
                shutil.copy2(src,out/(prefix+'_'+key+'.raw'))
            for key in ('weight','bias'):
                d=params[n[key]][0]
                (out/(prefix+('_weights.raw' if key=='weight' else '_bias.raw'))).write_bytes(blob[d['offset']:d['offset']+d['nbytes']])
            (out/(prefix+'_shifts.raw')).write_bytes(struct.pack('b'*co,*n['requantization_shift']))
            expected.append(dict(node=n['id'],actual=prefix+'_actual.raw',expected=prefix+'_expected.raw'))
        (out/'cases.txt').write_text(str(len(cases))+'\n'+'\n'.join(cases)+'\n',encoding='ascii')
        config='\n'.join(['part=xck26-sfvc784-2LV-c','','[hls]','flow_target=vivado','clock=10',
            'syn.top=griddehaze_conv_tile_top','syn.file='+ (out/'conv_tile_top.cpp').as_posix(),
            'syn.file_cflags='+(out/'conv_tile_top.cpp').as_posix()+',-std=c++11',
            'tb.file='+(out/'tb_conv_tile.cpp').as_posix(),
            'tb.file_cflags='+(out/'tb_conv_tile.cpp').as_posix()+',-std=c++11',
            'csim.argv='+(out/'cases.txt').as_posix(),'syn.interface.m_axi_max_widen_bitwidth=128',''])
        (out/'hls_config.cfg').write_text(config,encoding='ascii')
        report['config_sha256']=sha(out/'hls_config.cfg')
        report['fixture_sha256']={f.name:sha(f) for f in out.glob('*.raw')}
        def run(name,exe,args):
            values=[str(a.vitis/'settings64.bat'),str(exe),*[str(x) for x in args]]
            if any(re.search(r'[\r\n"&|<>^%!]',v) for v in values): raise ValueError('unsafe batch metacharacter')
            wrapper=out/(name+'.cmd')
            wrapper.write_text('@echo off\r\nsetlocal\r\nset "PROCESSOR_ARCHITECTURE=AMD64"\r\ncall "'+values[0]+'"\r\nif errorlevel 1 exit /b %errorlevel%\r\ncall '+' '.join('"'+v+'"' for v in values[1:])+'\r\nexit /b %errorlevel%\r\n',encoding='ascii',newline='')
            t=time.perf_counter()
            print('Running '+name+': '+str(out/(name+'.log')),flush=True)
            with (out/(name+'.log')).open('xb') as log:
                r=subprocess.run(['cmd.exe','/d','/c',str(wrapper)],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            report['steps'][name]=dict(exit_code=r.returncode,elapsed_seconds=time.perf_counter()-t,log_sha256=sha(out/(name+'.log')))
            if r.returncode: raise RuntimeError(name+' failed; see log')
            text=(out/(name+'.log')).read_text(errors='replace')
            if re.search(r'(?mi)^\s*(ERROR|FATAL)(:|\s)|fatal error:',text):
                raise RuntimeError(name+' contains vendor ERROR/FATAL despite launcher exit code')
        run('version',a.vitis/'bin/vitis-run.bat',['--version'])
        run('csim',a.vitis/'bin/vitis-run.bat',['--mode','hls','--csim','--config',out/'hls_config.cfg','--work_dir',out/'component'])
        for record in expected:
            assert sha(out/record['actual'])==sha(out/record['expected']),record
            record['sha256']=sha(out/record['actual'])
        assert 'ALL_TILE_CASES_PASS count=5' in (out/'csim.log').read_text(errors='replace')
        report['operator_cases']=expected
        if a.stage=='synth':
            run('synth',a.vitis/'bin/v++.bat',['-c','--mode','hls','--config',out/'hls_config.cfg','--work_dir',out/'component'])
            xml=list((out/'component').rglob('griddehaze_conv_tile_top_csynth.xml'))
            if len(xml)!=1: raise RuntimeError('missing/ambiguous csynth report')
            tree=ET.parse(xml[0])
            def fields(path):
                node=tree.find(path)
                return {c.tag:c.text for c in node} if node is not None else {}
            report['hls_estimate']=dict(resources=fields('.//AreaEstimates/Resources'),
                available=fields('.//AreaEstimates/AvailableResources'),
                timing=fields('.//PerformanceEstimates/SummaryOfTimingAnalysis'),
                latency=fields('.//PerformanceEstimates/SummaryOfOverallLatency'),report=str(xml[0]),report_sha256=sha(xml[0]))
        report['pass_result']=True
    except Exception as e:
        report['error']=repr(e)
        raise
    finally:
        save(out/'result.json',report)
        print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__': main()
