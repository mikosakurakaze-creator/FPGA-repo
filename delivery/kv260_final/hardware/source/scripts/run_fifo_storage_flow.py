"""Prepare, verify and synthesize a FIFO structure variant with immutable receipts.

No Git, board access, bitstream, XSA, packaging or automatic acceptance.
"""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--baseline',type=Path,required=True)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--node-equivalence',type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve();build=a.build.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'pass':False,'stage':'through_synthesis','started_at':now(),'board_operations':0,'export_allowed':False,'steps':[]}
    def save(): (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    def run(name,script,args):
        cmd=[sys.executable,'-X','utf8','-B',str(ROOT/'scripts'/script),*map(str,args)]
        print(f'FIFO_FLOW_STAGE={name} START={now()} LOG={out/(name+".log")}',flush=True)
        start=time.perf_counter()
        with (out/(name+'.log')).open('xb') as f: p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=out)
        row={'stage':name,'exit_code':p.returncode,'seconds':time.perf_counter()-start,'finished_at':now(),
             'log_sha256':sha(out/(name+'.log')),'command':cmd}
        result['steps'].append(row);save()
        if p.returncode:raise RuntimeError(name+' failed; retain its log and receipt')
        print(f'FIFO_FLOW_STAGE={name} COMPLETE={row["finished_at"]}',flush=True)
    try:
        node=a.node_equivalence.resolve(); proof=json.loads((node/'result.json').read_text())
        if not proof['pass'] or proof.get('changed_channel_nodes')!=5: raise ValueError('AXI node proof incomplete')
        for name,digest in proof['source_files'].items():
            if sha(node/name)!=digest: raise ValueError('AXI node proof source changed')
        for row in proof['steps']:
            if row['exit_code'] or sha(node/(row['name']+'.log'))!=row['log_sha256']:
                raise ValueError('AXI node tool receipt changed')
        result['node_proof']={'path':(node/'result.json').as_posix(),'sha256':sha(node/'result.json'),
                              'scope':proof['scope']}
        run('prepare','prepare_fifo_storage_variant.py',['--baseline',a.baseline,'--out',build])
        run('memory_equivalence','verify_fifo_storage_variant.py',['--build',build,'--out',out/'memory_equivalence'])
        gate=json.loads((out/'memory_equivalence/result.json').read_text())
        if not gate['pass']:raise ValueError('Memory equivalence gate failed')
        result['memory_proof']={'path':(out/'memory_equivalence/result.json').as_posix(),
                                'sha256':sha(out/'memory_equivalence/result.json')}
        run('create','build_system.py',['--out',build,'--stage','create'])
        # Bind every generated derivative as well as its untouched original.
        records=build/'fifo_output_override_records.list'
        if not records.is_file():raise ValueError('Generated FIFO override records missing')
        # The records are Tcl lists (not safely shell-parsed). The backup tree
        # gives a portable relative enumeration of every derivative source.
        generated={}
        for original in (build/'fifo_generated_before').rglob('*.sv'):
            rel=original.relative_to(build/'fifo_generated_before')
            derived=build/rel
            text=original.read_text()
            expected=text.replace('.C_FIFO_OUTPUT_REG(1)','.C_FIFO_OUTPUT_REG(0)').replace('C_FIFO_OUTPUT_REG=1,','C_FIFO_OUTPUT_REG=0,')
            if derived.read_text()!=expected: raise ValueError('Undeclared generated source changes: '+str(rel))
            generated[rel.as_posix()]={'before':sha(original),'after':sha(derived)}
        if not 100<=len(generated)<=160:raise ValueError('Incomplete generated FIFO policy coverage')
        (out/'generated_source_identity.json').write_text(json.dumps(generated,indent=2)+'\n')
        result['generated_fifo_sources']=len(generated)
        result['generated_source_manifest_sha256']=sha(out/'generated_source_identity.json')
        run('synth','build_system.py',['--out',build,'--stage','synth'])
        for rel,row in generated.items():
            if sha(build/rel)!=row['after']:raise ValueError('Synthesis regenerated an unreviewed FIFO wrapper: '+rel)
        result['joint_synthesis_completed_at']=result['steps'][-1]['finished_at']
        result['checkpoint_sha256']=sha(build/'joint_synth.dcp')
        result['pass']=True
    except Exception as e:result['error']=str(e);raise
    finally:
        result['finished_at']=now();save();shutil.copy2(__file__,out/Path(__file__).name)
        print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
