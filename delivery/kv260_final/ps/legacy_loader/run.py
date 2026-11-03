#!/usr/bin/env python3
"""Compile offline, load from known stock boot, run exactly one full 720p frame."""
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time

from ownership import elf_build_note
from system_uio_policy import audit_system_uios

ROOT=Path(__file__).resolve().parent
KERNEL='5.15.0-1027-xilinx-zynqmp'
OVERLAYS=Path('/sys/kernel/config/device-tree/overlays')
MANAGER=Path('/sys/class/fpga_manager/fpga0')
FW='kv260-compact-d-v1/compact_d_system.bit.bin'
IMAGE='kv260_compact_d_v1_image'
RESOURCE='kv260_compact_d_v1_resources'
MARKER=Path('/run/kv260-compact_d-once-v1.json')
CASE=os.environ.get('COMPACT_D_CASE','8')
if CASE not in ('8','720'):raise RuntimeError('COMPACT_D_CASE must be 8 or 720')
H,W=(8,8) if CASE=='8' else (720,1280)
PAYLOAD=(6*H*W,6*H*W)

class Status(C.LittleEndianStructure):
    _fields_=[('abi',C.c_uint32),('attempted',C.c_uint32),('pending',C.c_uint32),('completed',C.c_uint32),
              ('error',C.c_int32),('ctrl',C.c_uint32),('core_return',C.c_uint32),('completed_nodes',C.c_uint32),
              ('hardware_model',C.c_uint32),('hardware_abi',C.c_uint32),('guards_ok',C.c_uint32),('reserved',C.c_uint32),
              ('elapsed_ns',C.c_uint64),('clock_hz',C.c_uint64),('dma',C.c_uint64*2)]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def verify():
    m=read(ROOT/'manifest.json')
    for name,row in m['files'].items():
        p=ROOT/name
        if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise RuntimeError('Package differs: '+name)
    if C.sizeof(Status)!=80:raise RuntimeError('Status layout differs')
    return m

def call(args,cwd=None,timeout=120):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(repr(args)+'\n'+p.stdout+p.stderr)
    return p.stdout.strip()

def firmware():return Path('/proc/device-tree/fpga-full/firmware-name').read_bytes().rstrip(b'\0').decode()
def overlays():return {p.name for p in OVERLAYS.iterdir() if p.is_dir()}

def audit_owners():
    audit_system_uios(Path('/sys/class/uio'),Path('/sys'))
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            for fd in (proc/'fd').iterdir():
                try:target=os.readlink(fd)
                except FileNotFoundError:continue
                if target=='/dev/mem' or target.startswith(('/dev/uio','/dev/kv260')):
                    raise RuntimeError('Device is open by pid='+proc.name+' '+target)
            maps=(proc/'maps').read_text()
            if any(x in maps for x in ('/dev/mem','/dev/uio','/dev/kv260')):raise RuntimeError('Active device map pid='+proc.name)
        except (FileNotFoundError,ProcessLookupError):continue

def stock():
    if firmware()!='k26-starter-kits.bit.bin' or overlays()!={'k26-starter-kits_image_1'}:
        raise RuntimeError('Requires official base after reboot. No hardware operation performed; reboot board, reconnect SSH, run again.')
    if any(p.name.startswith(('kv260_','weather_')) for p in Path('/sys/module').iterdir()):
        raise RuntimeError('Project module present; reboot into official base first')
    if MANAGER.joinpath('state').read_text().strip()!='operating':raise RuntimeError('FPGA manager is not operating')

def apply(name,path):
    target=OVERLAYS/name;target.mkdir()
    fd=os.open(target/'dtbo',os.O_WRONLY)
    try:
        data=path.read_bytes()
        if os.write(fd,data)!=len(data):raise RuntimeError('Partial overlay write; no retry')
    finally:os.close(fd)
    if (target/'status').read_text().strip()!='applied':raise RuntimeError('Overlay application unconfirmed')

def compile_only():
    if os.geteuid()==0:raise RuntimeError('Start as ubuntu, without sudo')
    m=verify()
    if platform.release()!=KERNEL or platform.machine()!='aarch64':raise RuntimeError('Unexpected board kernel/CPU')
    stock()
    if MARKER.exists():raise RuntimeError('Already attempted this boot; preserve logs and do not retry')
    for command in ['make','gcc','dtc','fdtoverlay','modinfo','dpkg-deb']:
        if not shutil.which(command):raise RuntimeError('Missing command '+command)
    if '# CONFIG_MODULE_SIG_FORCE is not set' not in Path('/boot/config-'+KERNEL).read_text():
        raise RuntimeError('Module signature policy differs')
    build=Path(tempfile.mkdtemp(prefix='compact_d_build.',dir=Path.home()))
    print('BUILD='+str(build),flush=True)
    for p in ROOT.iterdir():
        if p.suffix in ('.c','.h','.dtso') or p.name=='Makefile':shutil.copyfile(p,build/p.name)
    (build/'shape.h').write_text('#define D_HEIGHT '+str(H)+'\n#define D_WIDTH '+str(W)+'\n')
    command=['make','-C','/lib/modules/'+KERNEL+'/build','M='+str(build),'KCFLAGS=-Werror','modules']
    p=subprocess.run(command,capture_output=True,text=True)
    (build/'compile.log').write_text(p.stdout+p.stderr)
    if p.returncode:print(p.stdout+p.stderr);raise RuntimeError('Compile failed; hardware unchanged. '+str(build/'compile.log'))
    if call(['modinfo','-F','vermagic',str(build/'kv260_compact_d_once.ko')]).split()[0]!=KERNEL:raise RuntimeError('Module version differs')
    # Check the file-only BIT->BIN transformation with the bundled official ARM tool.
    toolroot=build/'bootgen';toolroot.mkdir()
    call(['dpkg-deb','--extract',str(ROOT/'bootgen_arm64.deb'),str(toolroot)])
    work=build/'conversion';work.mkdir()
    shutil.copyfile(ROOT/'compact_d_system.bit',work/'compact_d_system.bit')
    (work/'bitstream.bif').write_text('all:\n{\n compact_d_system.bit\n}\n')
    executable=toolroot/'usr/bin/bootgen'
    hdr=executable.read_bytes()[:64]
    if hdr[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',hdr,18)[0]!=183:raise RuntimeError('Bootgen is not AArch64')
    log=call([str(executable),'-image','bitstream.bif','-arch','zynqmp','-process_bitstream','bin','-w'],cwd=work)
    (build/'bootgen.log').write_text(log)
    bins=list(work.glob('*.bin'))
    if len(bins)!=1 or bins[0].read_bytes()!=(ROOT/'compact_d_system.bit.bin').read_bytes():
        raise RuntimeError('Official Bootgen conversion differs; hardware unchanged')
    for name in ('d_image','d_resources'):
        call(['dtc','-@','-I','dts','-O','dtb','-o',str(build/(name+'.dtbo')),str(build/(name+'.dtso'))])
    call(['dtc','-I','fs','-O','dtb','-o',str(build/'base.dtb'),'/proc/device-tree'])
    call(['fdtoverlay','-i',str(build/'base.dtb'),'-o',str(build/'merged.dtb'),str(build/'d_image.dtbo'),str(build/'d_resources.dtbo')])
    outputs={name:sha(build/name) for name in ['kv260_compact_d_once.ko','d_image.dtbo','d_resources.dtbo','merged.dtb']}
    record={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'manifest_sha256':sha(ROOT/'manifest.json'),'outputs':outputs,'kernel':KERNEL,'case':CASE}
    (build/'build_report.json').write_text(json.dumps(record,indent=2)+'\n')
    print('COMPACT_D_BUILD_PASS bootgen=EXACT DT_MERGE=PASS hardware_unchanged=1',flush=True)
    subprocess.run(['sudo','env','COMPACT_D_CASE='+CASE,sys.executable,str(ROOT/'run.py'),'--execute',str(build)],check=True)

def execute(build):
    if os.geteuid()!=0:raise RuntimeError('Execution needs sudo')
    verify();stock()
    Path('/run/kv260-image-app').mkdir(exist_ok=True)
    with open('/run/kv260-image-app/owner.lock','a') as a,open('/run/lock/kv260-weather.lock','a') as b:
        fcntl.flock(a,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(b,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if MARKER.exists():raise RuntimeError('Already attempted this boot')
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        report=read(build/'build_report.json')
        if report.get('case')!=CASE or report['boot_id']!=boot or report['manifest_sha256']!=sha(ROOT/'manifest.json'):raise RuntimeError('Build/package/boot mismatch')
        for name,digest in report['outputs'].items():
            if Path(name).name!=name or sha(build/name)!=digest:raise RuntimeError('Build output differs '+name)
        if int(Path('/proc/sys/kernel/tainted').read_text())&128:raise RuntimeError('Kernel fault taint present')
        audit_owners()
        mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('CmaTotal:','CmaFree:'))}
        needed=sum((n+128+4095)//4096*4096 for n in PAYLOAD)
        if mem.get('CmaFree',0)*1024<needed+16*1024**2:raise RuntimeError('Insufficient free CMA; hardware unchanged: '+str(mem))
        note=elf_build_note((build/'kv260_compact_d_once.ko').read_bytes())
        result={'phase':'PREPARED','build':str(build),'boot_id':boot,'shape':[1,3,H,W],
                'B_commit':'d8880cce7241628f5472a36802b1791e85935e27',
                'bundle_id':'2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a',
                'CMA_before_kB':mem,'dma_allocation_bytes':needed,'ip_starts':0,'automatic_recovery':False}
        fd=None;worker=None;worker_errors=[]
        def save():
            data=json.dumps(result,indent=2)+'\n';MARKER.write_text(data);(build/'result.json').write_text(data)
        with MARKER.open('x') as f:f.write(json.dumps(result)+'\n')
        os.chmod(MARKER,0o600)
        try:
            result['phase']='LOADING';save()
            subprocess.run(['systemctl','stop','--no-block','dfx-mgr.service'],check=True)
            limit=time.monotonic()+20
            while subprocess.run(['systemctl','is-active','--quiet','dfx-mgr.service']).returncode==0:
                if time.monotonic()>limit:raise RuntimeError('DFX manager did not stop')
                time.sleep(.2)
            audit_owners();stock()
            MANAGER.joinpath('flags').write_text('0\n')
            if int(MANAGER.joinpath('flags').read_text().strip(),16)!=0:raise RuntimeError('File loading flags differ')
            (OVERLAYS/'k26-starter-kits_image_1').rmdir()
            if overlays():raise RuntimeError('Unexpected active overlay')
            target=Path('/lib/firmware')/FW;target.parent.mkdir(exist_ok=True)
            if target.exists() or target.is_symlink():
                if target.is_symlink() or sha(target)!=sha(ROOT/'compact_d_system.bit.bin'):raise RuntimeError('Installed firmware differs')
            else:
                with target.open('xb') as f:f.write((ROOT/'compact_d_system.bit.bin').read_bytes())
                target.chmod(0o644)
            apply(IMAGE,build/'d_image.dtbo')
            if firmware()!=FW or MANAGER.joinpath('state').read_text().strip()!='operating':raise RuntimeError('Image load unconfirmed')
            call(['insmod',str(build/'kv260_compact_d_once.ko')])
            apply(RESOURCE,build/'d_resources.dtbo')
            module=Path('/sys/module/kv260_compact_d_once')
            if (module/'notes/.note.gnu.build-id').read_bytes()!=note or int((module/'refcnt').read_text())!=0:
                raise RuntimeError('Module identity or ownership differs')
            if overlays()!={IMAGE,RESOURCE}:raise RuntimeError('Overlay set differs')
            for name,path in [(IMAGE,'d_image.dtbo'),(RESOURCE,'d_resources.dtbo')]:
                if sha(OVERLAYS/name/'dtbo')!=sha(build/path):raise RuntimeError('Overlay bytes differ')
            device=Path('/sys/class/misc/kv260_compact_d_once/device').resolve(strict=True)
            if (device/'driver').resolve().name!='kv260_compact_d_once':raise RuntimeError('Unexpected device owner')
            node=(device/'of_node').resolve(strict=True)
            if (node/'compatible').read_bytes()!=b'fpga-compact-d,kv260-once-v1\0':raise RuntimeError('Wrong device binding')
            if (node/'reg').read_bytes()!=struct.pack('>16I',0,0xa0050000,0,0x10000,0,0xfd800000,0,0x1000,0,0xfd380000,0,0x1000,0,0xfd3b0000,0,0x1000):raise RuntimeError('Wrong register resource')
            fd=os.open('/dev/kv260_compact_d_once',os.O_RDWR|os.O_CLOEXEC)
            result['phase']='ALLOCATING_720P_DMA';save();print('GRID_ALLOC_BEGIN two guarded image buffers; no IP start yet',flush=True)
            fcntl.ioctl(fd,0x47e2)
            for name in ('input_'+CASE+'.raw',):
                with (ROOT/name).open('rb') as f:
                    while True:
                        block=f.read(1048576)
                        if not block:break
                        view=memoryview(block)
                        while view:
                            n=os.write(fd,view)
                            if n<=0:raise RuntimeError('Short device upload')
                            view=view[n:]
            result['phase']='RUNNING';result['ip_starts']=1;save()
            print('GRID720_BEGIN single_frame; deadline=5s. Do not retry/reset.',flush=True)
            def launch():
                try:fcntl.ioctl(fd,0x47e1)
                except BaseException as exc:worker_errors.append(repr(exc))
            worker=threading.Thread(target=launch);started=time.monotonic();worker.start()
            while worker.is_alive():
                worker.join(1)
                if worker.is_alive():print('GRID720_RUNNING elapsed_seconds='+str(round(time.monotonic()-started)),flush=True)
            if worker_errors:result['run_error']=worker_errors[0]
            raw=bytearray(80);fcntl.ioctl(fd,0x805047e0,raw,True);status=Status.from_buffer_copy(raw)
            result['status']={name:getattr(status,name) for name,_ in Status._fields_ if name!='dma'}
            result['status']['dma']=list(status.dma)
            if status.pending:raise RuntimeError('Completion uncertain; DMA retained. Do not reset/reload/retry.')
            if worker_errors or status.error or not status.completed or not status.guards_ok:
                raise RuntimeError('Hardware frame failed; output invalid')
            actual=build/'actual_720p_q14.raw'
            with actual.open('xb') as f:
                remaining=PAYLOAD[1]
                while remaining:
                    data=os.read(fd,min(1048576,remaining))
                    if not data:raise RuntimeError('Short result read')
                    f.write(data);remaining-=len(data)
            expected=(ROOT/('expected_'+CASE+'.raw')).read_bytes();data=actual.read_bytes()
            result['actual_sha256']=sha(actual);result['golden_sha256']=sha(ROOT/('expected_'+CASE+'.raw'))
            result['golden_exact']=data==expected;result['core_elapsed_seconds']=status.elapsed_ns/1e9
            if data!=expected:
                import numpy as np
                a=np.frombuffer(data,dtype='<i2');e=np.frombuffer(expected,dtype='<i2');bad=np.flatnonzero(a!=e)
                first=int(bad[0]);result['mismatch']={'count':int(len(bad)),'first_flat':first,'actual':int(a[first]),'expected':int(e[first])}
                raise RuntimeError('Full-frame Golden mismatch; preserve actual raw and logs')
            import numpy as np
            from PIL import Image
            a=np.frombuffer(data,dtype='<i2').reshape(3,H,W).astype(np.int32)
            rgb=np.rint(np.clip(a.astype(np.float64)/16384,0,1)*255).astype(np.uint8).transpose(1,2,0)
            Image.fromarray(rgb).save(build/'output.png')
            result['phase']='COMPACT_D_GOLDEN_PASS'
            print('COMPACT_D_GOLDEN_PASS all_values_exact guards=PASS input=UNCHANGED',flush=True)
        except BaseException as exc:
            result['error']=repr(exc);result['phase']='STOPPED_NO_AUTOMATIC_RECOVERY'
            if worker is not None and worker.is_alive():
                print('Waiting for active ioctl; closing terminal does not cancel hardware DMA.',flush=True)
                worker.join()
            if fd is not None:
                try:
                    raw=bytearray(80);fcntl.ioctl(fd,0x805047e0,raw,True);s=Status.from_buffer_copy(raw)
                    result['status']={n:getattr(s,n) for n,_ in Status._fields_ if n!='dma'};result['status']['dma']=list(s.dma)
                except Exception as status_error:result['status_error']=repr(status_error)
            raise
        finally:
            if fd is not None:os.close(fd)
            p=Path('/sys/module/kv260_compact_d_once/refcnt');result['module_refcnt_after_close']=int(p.read_text()) if p.exists() else None
            log=subprocess.run(['dmesg'],capture_output=True,text=True);(build/'kernel.log').write_text(log.stdout+log.stderr)
            save();print(json.dumps(result,indent=2));print('RESULT='+str(build/'result.json'),flush=True)

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--execute':execute(Path(sys.argv[2]).resolve(strict=True))
    elif len(sys.argv)==1:compile_only()
    else:raise SystemExit('Run python3 run.py as ubuntu')
