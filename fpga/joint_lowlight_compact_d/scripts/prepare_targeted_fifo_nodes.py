"""Freeze six replacement nodes selected only from the latest routed candidate.

This prepares standalone node synthesis, not a whole-design regeneration.
The parent routed checkpoint and all unselected logic remain immutable.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from targeted_fifo_mapping import bram_output, buffered_payload, parameter


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(__doc__)
    for name in ('parent','audit','inspect','out'):
        ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'pass':False,'board_operations':0,'export_allowed':False,'bound_files':{},'nodes':[]}
    def bind(path):
        p=Path(path).resolve();result['bound_files'][p.as_posix()]=sha(p);return p
    def load(path): return json.loads(bind(path).read_text())
    try:
        audit=load(a.audit);inspect=load(a.inspect/'result.json')
        if not audit['pass'] or not inspect['pass']:
            raise ValueError('Current physical audit/inspection incomplete')
        checkpoint=bind(Path(audit['experiment'])/'optimized_routed.dcp')
        if sha(checkpoint)!=audit['checkpoint_sha256'] or inspect['source_checkpoint_sha256']!=sha(checkpoint):
            raise ValueError('Targets were not selected from CURRENT routed candidate')
        result['parent_checkpoint']=checkpoint.as_posix()
        result['parent_checkpoint_sha256']=sha(checkpoint)
        for name,digest in inspect['reports'].items():
            if sha(bind(a.inspect/name))!=digest: raise ValueError('Current target report changed')
        parent=a.parent.resolve();manifest=load(parent/'inputs.json')
        for name,digest in manifest['source_files'].items():
            if sha(bind(parent/name))!=digest:raise ValueError('Current parent source changed')
        rows=list(csv.DictReader(bind(a.inspect/'current_hold_targets.tsv').open(),delimiter='\t'))
        groups=Counter(r['node'] for r in rows if r['node']!='OTHER')
        result['diagnostic_cutoff_ns']=0.100
        result['tight_endpoints']=len(rows)
        result['other_endpoints']=[r for r in rows if r['node']=='OTHER']
        for key,count in sorted(groups.items()):
            sc,node=key.split('/')
            folder=parent/f'project/joint_system.gen/sources_1/bd/system/ip/system_{sc}_0/bd_0/ip'
            matches=[p for p in folder.rglob('*.xci') if json.loads(p.read_text())['ip_inst']['cell_name']==node]
            if len(matches)!=1:raise ValueError('Ambiguous node wrapper: '+key)
            xci=bind(matches[0]);source=bind(xci.parent/'synth'/(xci.stem+'.sv'))
            text=source.read_text();channel=parameter(text,'C_CHANNEL')
            if parameter(text,'C_FIFO_OUTPUT_REG')!=0:
                raise ValueError('Expected just-routed unregistered node')
            if channel==0:
                method='bram';changed=bram_output(text)
            elif channel in (2,4):
                method='buffer';changed=buffered_payload(text)
            else:raise ValueError('Unexpected tight node channel')
            dest=out/(sc+'__'+node+'.sv');dest.write_text(changed,encoding='utf-8',newline='\n')
            module=re.search(r'(?m)^module\s+(\w+)',text).group(1)
            hierarchy=f'system_i/{sc}/inst/{node.split("_")[0]}_nodes/{node}'
            result['nodes'].append({'key':key,'endpoints':count,'method':method,'module':module,
                'cell':hierarchy,'source':source.as_posix(),'source_sha256':sha(source),
                'replacement':dest.as_posix(),'replacement_sha256':sha(dest),
                'payload_width':parameter(text,'C_PAYLD_WIDTH')})
        if len(result['nodes'])!=6 or sum(r['endpoints'] for r in result['nodes'])!=510:
            raise ValueError('CURRENT target coverage changed; review before replacing nodes')
        for script in ('targeted_fifo_mapping.py','prepare_targeted_fifo_nodes.py'):
            source=Path(__file__).parent/script;shutil.copy2(source,out/script);bind(out/script)
        constants=bind('D:/vivado/2025.2/Vivado/data/ip/xilinx/sc_util_v1_0/xgui/sc_util_v1_0_constants.tcl')
        result['vendor_parameter_constants']=constants.as_posix()
        tcl=['set node_specs {']
        for row in result['nodes']:
            tcl.append('  {'+' '.join('{'+str(row[k])+'}' for k in ('key','module','replacement','method','payload_width'))+'}')
        tcl.append('}')
        (out/'node_specs.tcl').write_text('\n'.join(tcl)+'\n');bind(out/'node_specs.tcl')
        result['pass']=True
    except Exception as e:result['error']=str(e);raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='bound_files'},indent=2,ensure_ascii=False))


if __name__=='__main__':main()
