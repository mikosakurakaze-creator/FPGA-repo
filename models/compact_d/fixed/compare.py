"""Strict file-only FPGA/RTL dump comparator; does not attest origin of files."""
import argparse
import json
from pathlib import Path
import numpy as np
from .numeric import load_package,sha256,write_json

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--package',required=True);p.add_argument('--golden',required=True);p.add_argument('--actual',required=True);p.add_argument('--bundle-id',required=True);p.add_argument('--nodes');p.add_argument('--report',required=True);a=p.parse_args()
    manifest,_,_=load_package(a.package);golden=Path(a.golden);case=json.loads((golden/'report.json').read_text())
    if a.bundle_id != manifest['bundle_id'] or case['bundle_id'] != a.bundle_id:raise ValueError('Bundle ID mismatch')
    results=[]
    def check(node,path):
        path=Path(path);expected_bytes=node['bytes']
        if path.stat().st_size != expected_bytes:raise ValueError('Tensor byte length mismatch: '+str(path))
        digest=sha256(path)
        result=dict(node=node['id'],exact=digest==node['sha256'],bytes=expected_bytes,actual_sha256=digest,expected_sha256=node['sha256'])
        if not result['exact'] and node['file']:
            delta=np.fromfile(path,dtype='<i2').astype(np.int64)-np.fromfile(golden/node['file'],dtype='<i2').astype(np.int64)
            result.update(different_elements=int(np.count_nonzero(delta)),max_abs=int(np.max(np.abs(delta))))
        results.append(result)
    check(case['nodes'][-1],a.actual)
    if a.nodes:
        for node in case['nodes']:check(node,Path(a.nodes)/f'{node["index"]:02d}_{node["id"]}.i16')
    report=dict(scope='File bytes only, source hardware provenance must be supplied separately',bundle_id=a.bundle_id,exact=all(v['exact'] for v in results),results=results)
    write_json(a.report,report)
    print(json.dumps({'status':'D_COMPARE_PASS' if report['exact'] else 'D_COMPARE_FAIL','checked':len(results)}))
    if not report['exact']:raise SystemExit(1)
if __name__=='__main__':main()
