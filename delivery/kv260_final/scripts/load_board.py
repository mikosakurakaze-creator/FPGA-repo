"""Known-stock cold-start loader. Default checks only; --execute loads PL."""
import argparse,fcntl,hashlib,importlib.util,os,sys,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ps/driver'))
import load_reference as ref
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    assert os.uname().machine=='aarch64'
    subprocess.run([sys.executable,str(ROOT/'scripts/verify_package.py')],check=True)
    module=ROOT/'ps/driver/kv260_joint_once.ko'
    assert subprocess.check_output(['modinfo','-F','vermagic',str(module)],text=True).split()[0]==os.uname().release
    for n in ['joint_image','joint_resources']:
        assert (ROOT/'ps/driver'/(n+'.dtbo')).is_file(),'Run scripts/build_driver.sh'
    if not args.execute:
        print('BOARD_PREFLIGHT_PASS firmware='+ref.loader.firmware()+'; hardware unchanged');return
    assert os.geteuid()==0,'sudo required'
    locks=[]
    for name in ['/run/kv260-image-app/owner.lock','/run/lock/kv260-weather.lock']:
        p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);f=p.open('a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
    ref.loader.stock();ref.loader.audit_owners()
    assert not (int(Path('/proc/sys/kernel/tainted').read_text())&128),'Kernel fault taint'
    free=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('CmaFree:')))*1024
    assert free>=400*1024**2,'Requires at least 400 MiB free CMA'
    ref.load_image()
    print('BOARD_LOAD_PASS build=c6496c6dc89aa54c4500; start hardware service next')
if __name__=='__main__':main()
