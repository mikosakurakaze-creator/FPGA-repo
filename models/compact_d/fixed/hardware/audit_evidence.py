"""Audit retained source/report identities without a Vitis installation."""
import argparse
import hashlib
import json
from pathlib import Path
from run_proof import HERE, digest, hls_report


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--evidence',type=Path,default=HERE/'evidence')
    p.add_argument('--package',type=Path)
    a=p.parse_args()
    evidence=json.loads((a.evidence/'evidence.json').read_text())
    for name,sha in evidence['source_sha256'].items():
        if digest(HERE/name)!=sha: raise ValueError('Kernel source identity changed: '+name)
    for name,sha in evidence['files'].items():
        if digest(a.evidence/name)!=sha: raise ValueError('Raw report identity changed: '+name)
    for candidate in evidence['candidates']:
        saved=candidate['report'];parsed=hls_report(a.evidence/saved['path'])
        for field in ('sha256','tool','timing','latency','loops','resources','available'):
            if saved[field]!=parsed[field]: raise ValueError('Report summary mismatch: '+field)
        if 'mac_loop_report' in saved:
            child=saved['mac_loop_report'];parsed=hls_report(a.evidence/child['path'])
            for field in ('sha256','tool','timing','latency','loops','resources','available'):
                if child[field]!=parsed[field]: raise ValueError('Loop report summary mismatch: '+field)
    if len(evidence['actual']['vectors'])!=6 or any(run['status']!='D_MICRO_EXACT_PASS' for run in evidence['actual']['runs']):
        raise ValueError('Actual six-node verification incomplete')
    if a.package:
        manifest=json.loads((a.package/'manifest.json').read_text())
        identity={k:v for k,v in manifest.items() if k!='bundle_id'}
        canonical=(json.dumps(identity,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        if hashlib.sha256(canonical).hexdigest()!=manifest['bundle_id'] or manifest['bundle_id']!=evidence['actual']['bundle_id']:
            raise ValueError('Actual tested bundle identity mismatch')
        for name,sha in manifest['files'].items():
            if digest(a.package/name)!=sha: raise ValueError('Package file changed: '+name)
    print(json.dumps(dict(status='D_HARDWARE_EVIDENCE_AUDIT_PASS',
                          source_files=len(evidence['source_sha256']),
                          raw_reports=len(evidence['files']),actual_conv_nodes=6,
                          bundle_id=evidence['actual']['bundle_id'])))


if __name__=='__main__': main()
