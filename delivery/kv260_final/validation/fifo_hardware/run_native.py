"""One explicitly invoked joint frame, using coherent kernel DMA and old loader checks."""
import ctypes as C
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
PACKAGE=Path.home()/'fifo_hold_release_20261102'
OLD=Path('/home/ubuntu/compact_d_once_v1')
sys.path.insert(0,str(OLD))
spec=importlib.util.spec_from_file_location('old_loader',OLD/'run.py')
loader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)
class Status(C.LittleEndianStructure):
    _fields_=[('abi',C.c_uint32),('attempted',C.c_uint32),('pending',C.c_uint32),('completed',C.c_uint32),
              ('error',C.c_int32),('ctrl',C.c_uint32),('core_return',C.c_uint32),('completed_nodes',C.c_uint32),
              ('hardware_model',C.c_uint32),('hardware_abi',C.c_uint32),('guards_ok',C.c_uint32),('reserved',C.c_uint32),
              ('elapsed_ns',C.c_uint64),('clock_hz',C.c_uint64),('dma',C.c_uint64*84)]
assert C.sizeof(Status)==736
def call(args):
    p=subprocess.run(args,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(repr(args)+'\n'+p.stdout+p.stderr)
    return p.stdout
def verify():
    m=json.loads((PACKAGE/'manifest.json').read_text())
    assert m['build_id']=='c6496c6dc89aa54c4500'
    for n,r in m['files'].items():
        p=(PACKAGE/n).resolve()
        assert p.is_relative_to(PACKAGE) and p.stat().st_size==r['bytes']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],n
def main():
    global PACKAGE
    PACKAGE=Path('/home/ubuntu/fifo_hold_release_20261102')
    verify()
    for n in ('joint_image','joint_resources'):
        call(['dtc','-@','-I','dts','-O','dtb','-o',str(ROOT/(n+'.dtbo')),str(ROOT/(n+'.dtso'))])
    call(['dtc','-I','fs','-O','dtb','-o',str(ROOT/'base.dtb'),'/proc/device-tree'])
    call(['fdtoverlay','-i',str(ROOT/'base.dtb'),'-o',str(ROOT/'merged.dtb'),str(ROOT/'joint_image.dtbo'),str(ROOT/'joint_resources.dtbo')])
    assert call(['modinfo','-F','vermagic',str(ROOT/'kv260_joint_once.ko')]).split()[0]==os.uname().release
    if '--execute' not in sys.argv:
        print('JOINT_PREFLIGHT_PASS: package, module ABI and offline DT merge; hardware unchanged',flush=True)
        return
    if os.geteuid()!=0:raise RuntimeError('sudo required')
    locks=[]
    for n in ('/run/kv260-image-app/owner.lock','/run/lock/kv260-weather.lock'):
        Path(n).parent.mkdir(exist_ok=True)
        f=open(n,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
    reuse='--reuse-image' in sys.argv
    if reuse:
        prior=json.loads(Path('/home/ubuntu/joint_fps_optimized_v1/result.json').read_text());prior['status']=prior['cases'][-1]['status']
        assert prior['phase']=='PASS' and prior['status']['pending']==0 and prior['build_id']=='c6496c6dc89aa54c4500'
        assert loader.firmware()=='kv260-joint-fifo-v1/joint_system.bit.bin'
        assert loader.MANAGER.joinpath('state').read_text().strip()=='operating'
        assert loader.overlays()=={'kv260_joint_fifo_image','kv260_joint_fifo_resources'}
        assert (loader.OVERLAYS/'kv260_joint_fifo_resources/dtbo').read_bytes()==(ROOT/'joint_resources.dtbo').read_bytes()
        assert Path('/lib/firmware/kv260-joint-fifo-v1/joint_system.bit.bin').read_bytes()==(PACKAGE/'joint_system.bit.bin').read_bytes()
        assert int(Path('/sys/module/kv260_joint_once/refcnt').read_text())==0
        loader.audit_owners()
    else:
        loader.stock();loader.audit_owners()
    if int(Path('/proc/sys/kernel/tainted').read_text())&128:raise RuntimeError('Kernel fault taint')
    free=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('CmaFree:')))*1024
    if free<400*1024**2:raise RuntimeError('Insufficient CMA')
    record={'phase':'PREPARED','build_id':'c6496c6dc89aa54c4500','ip_starts':0,'automatic_retry':False}
    marker=Path('/run/kv260-joint-fifo-fps-v1.json')
    with marker.open('x') as f:json.dump(record,f)
    def save():
        data=json.dumps(record,indent=2)+'\n';marker.write_text(data);(ROOT/'result.json').write_text(data)
    fd=None
    try:
        record['phase']='LOADING';save()
        if reuse:
            # Previous batch completed and closed; no active DMA or open owner.
            call(['rmmod','kv260_joint_once'])
            call(['insmod',str(ROOT/'kv260_joint_once.ko')])
        else:
            load_image()
        assert loader.overlays()=={'kv260_joint_fifo_image','kv260_joint_fifo_resources'}
        record['phase']='ALLOCATING';save()
        fd=os.open('/dev/kv260_joint_once',os.O_RDWR|os.O_CLOEXEC)
        fcntl.ioctl(fd,0x47e2)
        from video_session import run_session
        run_session(fd,PACKAGE,ROOT,Status,record,save)
    except BaseException as e:
        record['failure']=repr(e);record['phase']='FAILED';save();raise
    finally:
        if fd is not None:os.close(fd)

def load_image():
        call(['systemctl','stop','--no-block','dfx-mgr.service'])
        deadline=time.monotonic()+20
        while subprocess.run(['systemctl','is-active','--quiet','dfx-mgr.service']).returncode==0:
            if time.monotonic()>deadline:raise RuntimeError('dfx-mgr stop timeout')
            time.sleep(.2)
        loader.audit_owners();loader.stock()
        loader.MANAGER.joinpath('flags').write_text('0\n')
        assert int(loader.MANAGER.joinpath('flags').read_text().strip(),16)==0
        target=Path('/lib/firmware/kv260-joint-fifo-v1/joint_system.bit.bin')
        target.parent.mkdir(exist_ok=True)
        data=(PACKAGE/'joint_system.bit.bin').read_bytes()
        if target.exists() or target.is_symlink():
            assert not target.is_symlink() and target.read_bytes()==data
        else:
            with target.open('xb') as f:f.write(data)
            target.chmod(0o644)
        (loader.OVERLAYS/'k26-starter-kits_image_1').rmdir()
        assert not loader.overlays()
        loader.apply('kv260_joint_fifo_image',ROOT/'joint_image.dtbo')
        assert loader.firmware()=='kv260-joint-fifo-v1/joint_system.bit.bin'
        assert loader.MANAGER.joinpath('state').read_text().strip()=='operating'
        print('JOINT_IMAGE_LOADED',flush=True)
        call(['insmod',str(ROOT/'kv260_joint_once.ko')])
        loader.apply('kv260_joint_fifo_resources',ROOT/'joint_resources.dtbo')
if __name__=='__main__':main()
