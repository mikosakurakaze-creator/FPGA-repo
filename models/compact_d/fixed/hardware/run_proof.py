"""Reproduce isolated D convolution proof; optionally run bounded Vitis HLS.

Outputs are generated under outputs/, never inside B's project. This is a
numerical/performance microbenchmark, not a deployable D accelerator or ABI.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(command, output, timeout=900):
    start = time.perf_counter()
    environment = os.environ.copy()
    environment.setdefault('PROCESSOR_ARCHITECTURE', 'AMD64')
    # The compiler's DLLs live beside it (needed for g++ on Windows).
    environment['PATH'] = str(Path(command[0]).parent)+os.pathsep+environment.get('PATH','')
    with output.open('w', encoding='utf-8') as stream:
        try:
            completed = subprocess.run(list(map(str,command)), cwd=ROOT, env=environment,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       timeout=timeout, check=False)
            code, status = completed.returncode, 'finished'
        except subprocess.TimeoutExpired:
            # subprocess kills its direct child. Windows HLS may create a process
            # tree, so the runner must not be used with an arbitrarily short timeout.
            raise RuntimeError('Tool timeout; inspect and stop remaining tool children before retrying')
    return dict(command=list(map(str,command)), exit_code=code, status=status,
                elapsed_seconds=time.perf_counter()-start, log=str(output), log_sha256=digest(output))


def hls_report(path):
    tree=ET.parse(path).getroot()
    def fields(xpath):
        value=tree.find(xpath)
        return {child.tag:child.text for child in value} if value is not None else {}
    loops=tree.find('PerformanceEstimates/SummaryOfLoopLatency')
    return dict(path=str(path),sha256=digest(path),
                tool=fields('ReportVersion'),
                timing=fields('PerformanceEstimates/SummaryOfTimingAnalysis'),
                latency=fields('PerformanceEstimates/SummaryOfOverallLatency'),
                loops={loop.tag:{item.tag:item.text for item in loop if len(item)==0} for loop in loops} if loops is not None else {},
                resources=fields('AreaEstimates/Resources'),
                available=fields('AreaEstimates/AvailableResources'))


def theory():
    h,w=720,1280
    layers=[('stem.conv',3,8)]+[(f'block{b}.conv{c}',8,8) for b in range(3) for c in range(2)]+[('head.conv',8,3)]
    result=[]
    for name,ci,co in layers:
        result.append(dict(node=name,cin=ci,cout=co,mac_per_pixel=9*ci*co,
                           mac_720p=h*w*9*ci*co,
                           input_feature_bytes=h*w*ci*2,
                           output_feature_bytes=h*w*co*2,
                           three_row_buffer_bytes=3*w*ci*2,
                           two_row_delay_bytes=2*w*ci*2,
                           weights_i16_bytes=9*ci*co*2))
    # A materialized graph writes then reads every convolution boundary. Residual
    # source read adds 3*8, and normalized input bypass adds 3 channels/pixel.
    conv_boundary=sum(item['input_feature_bytes']+item['output_feature_bytes'] for item in result)
    return dict(kind='software_theory_not_hls_or_board',height=h,width=w,layers=result,
                mac_per_pixel=sum(i['mac_per_pixel'] for i in result),
                total_conv_mac=sum(i['mac_720p'] for i in result),
                parameter_weights_bytes=sum(i['weights_i16_bytes'] for i in result),
                bias_i64_bytes=(8*7+3)*8,
                raw_parameter_bytes=sum(i['weights_i16_bytes'] for i in result)+(8*7+3)*8,
                materialized_conv_feature_bytes=conv_boundary,
                materialized_with_skip_source_reads_bytes=conv_boundary+3*8*h*w*2+3*h*w*2,
                ideal_fused_boundary_i16_bytes=3*h*w*2*2,
                full_fused_eight_stage_two_row_bytes=sum(i['two_row_delay_bytes'] for i in result),
                caution='Traffic assumes every conv input read/output write exactly once; additional elementwise writes, DMA staging, cache inefficiency and weights excluded. Fully fused minimum assumes legal buffering of both residual and input bypass, which is not yet designed.')


def actual_vector(package, output, golden=None):
    if golden:
        # Consume A's existing layer Golden verbatim. This path needs only the
        # Python standard library and tests the frozen package, not a reexport.
        manifest=json.loads((package/'manifest.json').read_text())
        canonical=(json.dumps({k:v for k,v in manifest.items() if k!='bundle_id'},sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        if hashlib.sha256(canonical).hexdigest()!=manifest['bundle_id']:
            raise ValueError('Invalid bundle identity')
        graph=json.loads((package/'graph.json').read_text())
        for name,sha in manifest['files'].items():
            if digest(package/name)!=sha: raise ValueError('Package hash mismatch: '+name)
        blob=(package/'parameters.bin').read_bytes()
        params={p['name']:p for p in manifest['parameters']}
        by_node={node['id']:golden/f'{index:02d}_{node["id"]}.i16' for index,node in enumerate(graph)}
        files=[]
        for node in graph:
            if node['op']=='conv' and params[node['weight']]['shape'][:2]==[8,8]:
                def payload(name):
                    p=params[name];raw=blob[p['offset']:p['offset']+p['bytes']]
                    if hashlib.sha256(raw).hexdigest()!=p['sha256']: raise ValueError('Tensor hash mismatch')
                    return raw
                source,expected=by_node[node['inputs'][0]],by_node[node['id']]
                if source.stat().st_size!=1024 or expected.stat().st_size!=1024:
                    raise ValueError('Microkernel requires exactly 8x8 INT16 C8 Golden')
                path=output/(node['id']+'.vector')
                path.write_bytes(source.read_bytes()+payload(node['weight'])+payload(node['bias'])+
                                 bytes(node['requantization_shift'])+expected.read_bytes())
                files.append(dict(node=node['id'],path=str(path),sha256=digest(path),
                                  golden_source_sha256=digest(source),golden_output_sha256=digest(expected)))
        return dict(bundle_id=manifest['bundle_id'],input_description=str(golden),vectors=files)
    sys.path.insert(0,str(ROOT))
    import numpy as np
    from models.compact_d.fixed.numeric import load_package,run
    from griddehaze_fixed.io import input_rgb8
    manifest,graph,tensors=load_package(package)
    rgb=np.random.default_rng(20261025).integers(0,256,(8,8,3),dtype=np.uint8)
    q=input_rgb8(rgb,frac=14)
    values={}
    run(package,q,observer=lambda index,node,value,stats: values.update({node['id']:value.copy()}))
    files=[]
    for node in graph:
        if node['op']=='conv' and tensors[node['weight']].shape[:2]==(8,8):
            path=output/(node['id']+'.vector')
            path.write_bytes(values[node['inputs'][0]].astype('<i2').tobytes()+
                             tensors[node['weight']].astype('<i2').tobytes()+
                             tensors[node['bias']].astype('<i8').tobytes()+
                             np.asarray(node['requantization_shift'],dtype='u1').tobytes()+
                             values[node['id']].astype('<i2').tobytes())
            files.append(dict(node=node['id'],path=str(path),sha256=digest(path)))
    return dict(bundle_id=manifest['bundle_id'],input_description='seed20261025 RGB8 8x8',vectors=files)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/compact_d_hardware')
    parser.add_argument('--gxx',default=shutil.which('g++') or 'g++')
    parser.add_argument('--package',type=Path)
    parser.add_argument('--golden',type=Path,help='Optional frozen random_8x8 Golden folder; avoids numpy dependency')
    parser.add_argument('--hls',action='store_true')
    parser.add_argument('--vitis-bin',type=Path,default=Path('E:/Xilinx/2025.2/Vitis/bin'))
    parser.add_argument('--part',default='xck26-sfvc784-2LV-c')
    parser.add_argument('--clock-ns',type=float,default=10.0)
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    report=dict(scope='isolated_8x8_8to8_conv_microbenchmark',
                hardware_status='No D accelerator, RTL cosim, routed timing or physical board result',
                theory=theory(),source_sha256={p.name:digest(p) for p in sorted(HERE.glob('*')) if p.is_file()},
                host=[],hls=[])
    executable=out/('conv_micro.exe' if os.name=='nt' else 'conv_micro')
    report['host'].append(execute([args.gxx,'-O2','-std=c++17','-Wno-unknown-pragmas',HERE/'conv_micro.cpp',HERE/'conv_micro_tb.cpp','-o',executable],out/'host_build.log'))
    if report['host'][-1]['exit_code']: raise RuntimeError('Host build failed; inspect host_build.log')
    report['host'].append(execute([executable],out/'host_synthetic.log'))
    if args.package:
        report['actual_package']=actual_vector(args.package,out,args.golden)
        for vector in report['actual_package']['vectors']:
            report['host'].append(execute([executable,vector['path']],out/(vector['node']+'.host.log')))
    if args.hls:
        report['hls_target']=dict(part=args.part,clock_ns=args.clock_ns,
                                 status='Illustrative inherited local target; B must confirm final D part/clock')
        for name in ('direct','row_oc8'):
            cfg=out/(name+'.cfg')
            cfg.write_text(f'part={args.part}\n[hls]\nflow_target=vivado\nclock={args.clock_ns}\nsyn.file={HERE.as_posix()}/conv_micro.cpp\nsyn.top=d_conv_{name}\ntb.file={HERE.as_posix()}/conv_micro_tb.cpp\n',encoding='utf-8')
            component=out/(name+'_hls')
            extension='.bat' if os.name=='nt' else ''
            csim=execute([args.vitis_bin/('vitis-run'+extension),'--mode','hls','--csim','--config',cfg,'--work_dir',component],out/(name+'.csim.log'))
            synth=execute([args.vitis_bin/('v++'+extension),'-c','--mode','hls','--config',cfg,'--work_dir',component],out/(name+'.synth.log'))
            records=list(component.rglob('*_csynth.xml'))
            report['hls'].append(dict(candidate=name,csim=csim,synthesis=synth,reports=[hls_report(p) for p in records]))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if any(run['exit_code'] for run in report['host']): raise RuntimeError('Host exactness check failed')
    if any(item['csim']['exit_code'] or item['synthesis']['exit_code'] or not item['reports'] for item in report['hls']):
        raise RuntimeError('HLS evidence incomplete; inspect report.json')
    print(json.dumps(dict(status='D_HARDWARE_PROOF_PASS',report=str(out/'report.json'),hls_candidates=len(report['hls']))))


if __name__=='__main__': main()
