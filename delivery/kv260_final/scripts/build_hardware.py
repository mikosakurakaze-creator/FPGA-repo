"""Recreate the design from frozen implemented inputs; no historical Git/path dependency."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--stage',required=True,choices=['prepare','create','synth','implement','coverage','export']);p.add_argument('--vivado',default='vivado');a=p.parse_args();out=a.out.resolve()
    if a.stage=='prepare':
        assert not out.exists(),'Use a fresh build directory'
        shutil.copytree(ROOT/'hardware/source/implemented_inputs',out)
        shutil.copytree(ROOT/'hardware/source/generated_smartconnect',out/'frozen_smartconnect')
        (out/'reports').mkdir(exist_ok=True)
        shutil.copy2(ROOT/'scripts/restore_fifo_sources.py',out/'restore_fifo_sources.py')
        policy='''proc apply_fifo_output_policy {root} {
    puts [exec $::env(KV260_PYTHON) [file join $root restore_fifo_sources.py] apply $root]
}
proc verify_fifo_output_policy {root} {
    puts [exec $::env(KV260_PYTHON) [file join $root restore_fifo_sources.py] verify $root]
}
'''
        (out/'fifo_output_policy.tcl').write_text(policy)
        print('BUILD_PREPARE_PASS',out);return
    assert out.is_dir(),'Run --stage prepare first'
    env=os.environ.copy();env['KV260_PYTHON']=sys.executable
    cmd=[a.vivado,'-mode','batch','-source',str(out/'system_build.tcl'),'-tclargs',str(out),a.stage,str(out/'project/joint_system.xpr')]
    log=out/(a.stage+'_portable.log');receipt=out/(a.stage+'_portable.json')
    assert not log.exists() and not receipt.exists(),'Preserve prior attempt; use a fresh build'
    with log.open('wb') as f:process=subprocess.run(cmd,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT)
    receipt.write_text(json.dumps(dict(command=cmd,exit_code=process.returncode,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),board_operations=0),indent=2))
    if process.returncode:raise SystemExit(process.returncode)
    print('BUILD_STAGE_PASS',a.stage)
if __name__=='__main__':main()
