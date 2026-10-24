"""Retain small, portable raw HLS reports and their measured comparison.

Run after run_proof.py --hls and --package/--golden. Generated HLS projects,
executables, full tensor vectors and tool logs stay in ignored outputs/.
"""
import argparse
import json
from pathlib import Path
import shutil
from run_proof import HERE, ROOT, digest, hls_report


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--run-dir',type=Path,default=ROOT/'outputs/compact_d_hardware')
    p.add_argument('--actual-dir',type=Path,default=ROOT/'outputs/compact_d_hardware/actual')
    p.add_argument('--out',type=Path,default=HERE/'evidence')
    a=p.parse_args()
    runs=json.loads((a.run_dir/'report.json').read_text())
    actual=json.loads((a.actual_dir/'report.json').read_text())
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    sources={name:digest(HERE/name) for name in ('conv_micro.cpp','conv_micro.hpp','conv_micro_tb.cpp')}
    for name,sha in sources.items():
        if runs['source_sha256'][name]!=sha or actual['source_sha256'][name]!=sha:
            raise ValueError('Kernel source changed after testing: '+name)
    candidates=[];files={}
    for run in runs['hls']:
        tops=[item for item in run['reports'] if Path(item['path']).name==f'd_conv_{run["candidate"]}_csynth.xml']
        if run['csim']['exit_code'] or run['synthesis']['exit_code'] or len(tops)!=1:
            raise ValueError('Incomplete HLS candidate')
        original=Path(tops[0]['path'])
        for source in (original,original.with_suffix('.rpt')):
            target=out/source.name
            shutil.copyfile(source,target);files[target.name]=digest(target)
        result=hls_report(out/original.name);result['path']=original.name
        if run['candidate']=='row_oc8':
            child=next(Path(item['path']) for item in run['reports'] if Path(item['path']).name=='d_conv_row_oc8_Pipeline_ROW_MAC_csynth.xml')
            for source in (child,child.with_suffix('.rpt')):
                target=out/source.name;shutil.copyfile(source,target);files[target.name]=digest(target)
            result['mac_loop_report']=hls_report(out/child.name)
            result['mac_loop_report']['path']=child.name
        result['csim_status']='12 synthetic cases; 512 outputs each; CSim done with 0 errors'
        result['csim_log_sha256']=run['csim']['log_sha256']
        result['synthesis_log_sha256']=run['synthesis']['log_sha256']
        candidates.append(dict(candidate=run['candidate'],report=result))
    actual_runs=[]
    for run in actual['host'][1:]:
        if run['exit_code']: raise ValueError('Failed exactness run')
        lines=Path(run['log']).read_text().splitlines()
        result=json.loads(next(line for line in lines if line.startswith('{')))
        actual_runs.append(result)
    def portable_vector(v):
        return {k:(Path(value).name if k=='path' else value) for k,value in v.items()}
    evidence=dict(scope=runs['scope'],hls_target=runs['hls_target'],
                  boundaries='Measured HLS microkernel synthesis and host exactness only. No RTL cosim, complete D HLS, routed timing, DDR or board measurement.',
                  source_sha256=sources,files=files,candidates=candidates,
                  actual=dict(bundle_id=actual['actual_package']['bundle_id'],
                              vectors=[portable_vector(v) for v in actual['actual_package']['vectors']],
                              runs=actual_runs),theory=runs['theory'])
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='D_HARDWARE_EVIDENCE_FROZEN',path=str(out/'evidence.json'))))


if __name__=='__main__': main()
