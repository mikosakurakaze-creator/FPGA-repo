"""Finish the already-started local prepare build; stop on any failed gate."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('build','host','fusion','golden','controller-tests','out'):
        p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();receipt=a.build/'finish_delivery_result.json'
    if receipt.exists():raise ValueError('Preserve the previous run')
    result={'pass':False,'board_operations':0,'steps':[]}
    def run(name,script,args):
        command=[sys.executable,'-X','utf8','-B',str(ROOT/'scripts'/script),*map(str,args)]
        log=a.build/('finish_'+name+'.log')
        print('DELIVERY_STAGE='+name+' LOG='+str(log),flush=True)
        started=time.perf_counter()
        with log.open('xb') as f:proc=subprocess.run(command,cwd=a.build,stdout=f,stderr=subprocess.STDOUT)
        result['steps'].append({'stage':name,'command':command,'exit_code':proc.returncode,
            'seconds':time.perf_counter()-started,'log_sha256':sha(log)})
        if proc.returncode:raise RuntimeError(name+' failed; inspect '+str(log))
    try:
        print('WAITING_FOR_SYNTH_RESULT',flush=True)
        deadline=time.monotonic()+5400
        while not (a.build/'synth_result.json').exists():
            if time.monotonic()>deadline:raise TimeoutError('Synthesis has no completion record')
            time.sleep(2)
        if not json.loads((a.build/'synth_result.json').read_text())['pass']:raise ValueError('Synthesis failed')
        for stage in ('implement','coverage'):
            args=['--out',a.build,'--stage',stage]
            if stage=='implement':args+=['--incremental-checkpoint',Path('D:/weather_builds/joint_pipeline01_20261101/joint_routed.dcp')]
            run(stage,'build_system.py',args)
        run('accept','accept_system.py',['--build',a.build,'--host',a.host,'--fusion',a.fusion,'--golden',a.golden])
        run('export','build_system.py',['--out',a.build,'--stage','export'])
        run('collect','collect_delivery.py',['--build',a.build,'--host',a.host,'--fusion',a.fusion,'--golden',a.golden,
            '--controller-tests',a.controller_tests,'--out',a.out])
        archive=a.out.with_suffix('.zip');verified=a.out.parent/(a.out.name+'_verified.json')
        run('verify','verify_delivery.py',['--zip',archive,'--out',verified])
        result.update(pass_=True,zip=str(archive),zip_sha256=sha(archive),verification=str(verified))
        result['pass']=True;result.pop('pass_')
    except Exception as e:result['error']=str(e);raise
    finally:
        receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
