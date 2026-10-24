"""Build an independent B executor and compare its actual outputs against A Golden."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import struct
import subprocess
import sys
import time
from preflight import ROOT, audit, plan, save, sha


def emit_plan(path, m, g, params, memory):
    lookup={n['id']:i for i,n in enumerate(g['nodes'])}
    lines=[f'GDN_B_PLAN_1 {m["identity"]["bundle_id"]} {len(g["nodes"])} {memory["scratch_bytes"]} {memory["input_bytes"]} {memory["output_bytes"]}']
    for n,r in zip(g['nodes'],memory['nodes']):
        args=n['inputs']
        if n['op'] in ('conv','deconv'):
            assert n['dilation']==[1,1] and n['kernel_size'] in ([1,1],[3,3])
            assert n['stride'] in ([1,1],[2,2]) and len(set(n['padding']))==1
        if n['op']=='mulcoef': assert n['coefficient_frac']==14
        shifts=n.get('requantization_shift',[])
        fields=[n['id'],n['op'],{'scratch':0,'input':1,'output':2}[r['region']],r['offset'],*r['shape'],r['activation_frac'],
                lookup[args[0]] if args else -1,lookup[args[1]] if len(args)>1 else -1,
                n.get('kernel_size',[0])[0],n.get('stride',[1])[0],n.get('padding',[0])[0],m['quantization']['weight_bits'],
                params[n['weight']][0]['offset'] if 'weight' in n else 0,
                params[n['bias']][0]['offset'] if 'bias' in n else 0,
                params[n['coefficient']][0]['offset'] if 'coefficient' in n else 0,len(shifts),*shifts]
        lines.append(' '.join(str(x) for x in fields))
    with path.open('x',encoding='ascii',newline='\n') as f: f.write('\n'.join(lines)+'\n')


def compare(golden, result, g, dump):
    report=json.loads((golden/'report.json').read_text(encoding='utf-8'))
    assert [n['id'] for n in report['nodes']]==[n['id'] for n in g['nodes']]
    records=[]
    hashes={}
    for line in (result/'node_hashes.txt').read_text(encoding='ascii').splitlines():
        node,size,digest=line.split()
        assert node not in hashes
        hashes[node]=(int(size),digest)
    assert list(hashes)==[n['id'] for n in g['nodes']]
    expected=report['nodes']
    expected=[*expected,dict(json.loads((golden/'output.json').read_text(encoding='utf-8')),id='output')]
    for meta in expected:
        if not dump and meta['id']!='output':
            size,digest=hashes[meta['id']]
            records.append(dict(id=meta['id'],exact=size==meta['bytes'] and digest==meta['sha256'],
                                bytes=size,sha256=digest,expected_sha256=meta['sha256'],comparison='sha256_and_length'))
            continue
        path=result/'output.raw' if meta['id']=='output' else result/'nodes'/meta['file']
        actual=path.read_bytes()
        record=dict(id=meta['id'],exact=len(actual)==meta['bytes'] and hashlib.sha256(actual).hexdigest()==meta['sha256'],
                    bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),expected_sha256=meta['sha256'])
        if not record['exact']:
            ep=golden/'output.raw' if meta['id']=='output' else golden/'nodes'/meta['file']
            if ep.is_file() and len(actual)==meta['bytes']:
                ev=struct.unpack('<'+'h'*(len(actual)//2),ep.read_bytes())
                av=struct.unpack('<'+'h'*(len(actual)//2),actual)
                index=next(i for i,(e,a) in enumerate(zip(ev,av)) if e!=a)
                record.update(first_flat_index=index,expected=ev[index],actual=av[index])
        records.append(record)
    return dict(exact=all(r['exact'] for r in records),compared_nodes=len(records)-1,comparisons=records,
                backend='independent_B_C++_CPU_not_HLS_or_FPGA',golden_report_sha256=sha(golden/'report.json'))


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--candidate',type=Path,default=ROOT/'a_candidate')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cxx',default='g++')
    p.add_argument('--cases',nargs='+',default=['random','black','white','channel','impulse','size_4x4','size_32x48','size_34x46'])
    p.add_argument('--no-node-dumps',action='store_true')
    p.add_argument('--tile',action='store_true',help='execute cached HLS tile source with native INT64 arithmetic, not vendor simulation')
    p.add_argument('--elementwise',action='store_true',help='execute HLS elementwise source with native INT64 arithmetic, not vendor simulation')
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    snapshot=a.out/'executed_sources'
    source_hashes={}
    for folder in ('src','tools','hls'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and path.suffix in ('.cpp','.hpp','.py'):
                relative=path.relative_to(ROOT)
                target=snapshot/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,target)
                source_hashes[relative.as_posix()]=sha(path)
    commands=[]
    def run(cmd,name,cwd=None):
        t=time.perf_counter()
        r=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,cwd=cwd)
        log=dict(command=[str(x) for x in cmd],cwd=str(cwd or Path.cwd()),exit_code=r.returncode,
                 elapsed_seconds=time.perf_counter()-t,stdout=r.stdout,stderr=r.stderr)
        save(a.out/(name+'.json'),log); commands.append(log)
        if r.returncode: raise RuntimeError(f'{name}: {r.stderr[-2500:]}')
        if r.stdout: print(r.stdout.strip(),flush=True)
    flags=['-std=c++17','-O3','-Wall','-Wextra','-Werror']
    exe=a.out/'host_graph.exe'
    extra=['-DGDN_TILE_BACKEND','-DGDN_NATIVE_HOST','-Wno-unknown-pragmas',snapshot/'hls/conv_tile_top.cpp'] if a.tile else []
    if a.elementwise:
        if not a.tile: extra+=['-DGDN_NATIVE_HOST','-Wno-unknown-pragmas']
        extra+=['-DGDN_ELEMENTWISE_BACKEND',snapshot/'hls/elementwise_top.cpp']
    run([a.cxx,*flags,snapshot/'src/host_graph.cpp',*extra,'-lbcrypt','-o',exe],'compile_graph')
    run([a.cxx,*flags,snapshot/'src/test_fixed_math.cpp','-o',a.out/'test_fixed_math.exe'],'compile_math')
    run([a.out/'test_fixed_math.exe'],'test_math')
    m,g,params,audit_report=audit(a.candidate/'package')
    cases=[]
    for name in a.cases:
        golden=a.candidate/'golden'/name
        meta=json.loads((golden/'input.json').read_text(encoding='utf-8'))
        h,w=meta['shape'][-2:]
        assert sha(golden/'input.raw')==meta['sha256']
        result=a.out/name
        result.mkdir()
        if not a.no_node_dumps: (result/'nodes').mkdir()
        memory=plan(g,params,h,w)
        save(result/'memory.json',memory)
        emit_plan(result/'plan.txt',m,g,params,memory)
        run([exe,result/'plan.txt',a.candidate/'package/parameters.bin',golden/'input.raw',result,int(not a.no_node_dumps)],'execute_'+name)
        comparison=compare(golden,result,g,not a.no_node_dumps)
        comparison.update(case=name,input_sha256=meta['sha256'],bundle_id=m['identity']['bundle_id'])
        save(result/'comparison.json',comparison)
        if not comparison['exact']: raise RuntimeError('Golden mismatch: '+name)
        cases.append({k:v for k,v in comparison.items() if k!='comparisons'})
        print(f'B_CPP_EXACT {name} nodes={comparison["compared_nodes"]}',flush=True)
    save(a.out/'summary.json',dict(exact=True,hardware_test=False,hls_test=False,rtl_test=False,
        source_hashes=source_hashes,tile_backend_native=a.tile,elementwise_backend_native=a.elementwise,
        package_audit=audit_report,cases=cases,executable_sha256=sha(exe),
        scope='Independent C++ graph, exact same aligned DDR allocation plan, all arithmetic integer; no FPGA timing claim'))


if __name__=='__main__': main()
