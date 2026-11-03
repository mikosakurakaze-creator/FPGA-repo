"""Freeze/verify the exact current-route inputs to a six-node replacement."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('mode',choices=('freeze','verify'))
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--prepared',type=Path)
    ap.add_argument('--synthesis',type=Path)
    ap.add_argument('--proof',type=Path,action='append',default=[])
    a=ap.parse_args()
    if a.mode=='verify':
        data=json.loads(a.manifest.read_text())
        if not data['pass']:raise ValueError('Inputs were not frozen successfully')
        for name,digest in data['files'].items():
            if sha(name)!=digest:raise ValueError('Input changed: '+name)
        print('TARGETED_NODE_INPUTS_VERIFIED='+str(len(data['files'])));return
    if a.manifest.exists():raise ValueError('Retain the earlier input receipt')
    result={'pass':False,'board_operations':0,'export_allowed':False,'files':{},'proofs':[]}
    def bind(path,digest=None):
        p=Path(path).resolve();actual=sha(p)
        if digest and actual!=digest:raise ValueError('Input identity changed: '+str(p))
        result['files'][p.as_posix()]=actual;return p
    def load(path):return json.loads(bind(path).read_text())
    try:
        prep=load(a.prepared/'result.json');synth=load(a.synthesis/'result.json')
        if not prep['pass'] or not synth['pass'] or synth['stage']!='inspect' or synth['exit_code']:
            raise ValueError('Node preparation/synthesis incomplete')
        for name,digest in prep['bound_files'].items():bind(name,digest)
        parent=bind(prep['parent_checkpoint'],prep['parent_checkpoint_sha256'])
        if synth['source_checkpoint_sha256']!=sha(parent):raise ValueError('Wrong routed parent')
        bind(a.synthesis/'console.log',synth['log_sha256'])
        bind(a.synthesis/'timing_margin.tcl',synth['script_sha256'])
        bind(a.synthesis/'optimize_timing_margin.py',synth['runner_sha256'])
        for name,digest in synth['reports'].items():bind(a.synthesis/name,digest)
        bind(a.synthesis/'node_specs.tcl',sha(a.prepared/'node_specs.tcl'))
        for row in prep['nodes']:
            bind(row['replacement'],row['replacement_sha256'])
            bind(a.synthesis/(row['key'].replace('/','__')+'.dcp'))
        for path in a.proof:
            proof=load(path)
            if not proof['pass'] or proof['changed_channel_nodes']!=3 or proof.get('fifo_mode')!='targeted':
                raise ValueError('Targeted AXI proof incomplete')
            for name,digest in proof['source_files'].items():bind(path.parent/name,digest)
            for name,digest in proof['verification_sources'].items():bind(path.parent/name,digest)
            for row in proof['steps']:
                text=bind(path.parent/(row['name']+'.log'),row['log_sha256']).read_text(errors='replace')
                if row['exit_code'] or re.search(r'(?m)^\s*(?:ERROR|Error|FATAL):',text) or \
                   'overwriting previous definition of module' in text:
                    raise ValueError('Non-independent or failed AXI proof')
            result['proofs'].append(proof['scope'])
        if len(a.proof)!=2 or not any('128-bit SI' in s for s in result['proofs']) or \
           not any('32-bit SI' in s for s in result['proofs']):raise ValueError('Both AXI widths required')
        vendor=Path('D:/vivado/2025.2/Vivado/data/ip/xilinx')
        for core in ('sc_node_v1_0','sc_util_v1_0'):
            for p in (vendor/core/'hdl').rglob('*'):
                if p.is_file() and p.suffix in ('.v','.sv','.vh','.svh'):bind(p)
        shutil.copy2(__file__,a.prepared/Path(__file__).name);bind(a.prepared/Path(__file__).name)
        result.update(parent_checkpoint=parent.as_posix(),parent_checkpoint_sha256=sha(parent),
                      node_count=len(prep['nodes']),pass_=True)
        result.pop('pass_');result['pass']=True
    except Exception as e:result['error']=str(e);raise
    finally:
        a.manifest.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))


if __name__=='__main__':main()
