import os,socket,fcntl,ctypes as C,json,time,struct,sys,signal
from pathlib import Path
from driver_status import Status
BASE=Path(__file__).resolve().parent;PACKAGE=BASE.parent/'hardware';locks=[]
for n in ['/run/kv260-image-app/owner.lock','/run/lock/kv260-weather.lock']:
 Path(n).parent.mkdir(parents=True,exist_ok=True);f=open(n,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
params=Path('/sys/module/kv260_joint_once/parameters')
for k,v in [('ps_mode',2),('bench_frames',1),('verify_all',0),('cache_poison',0),('verify_output',0)]:(params/k).write_text(str(v))
initial=[(PACKAGE/n).read_bytes() for n in ['golden/original.i16','golden/d_input.i16','golden/cnn_input.i16','model/weights_int8.bin','model/bias_int32.bin','model/weight_frac.bin','model/tanh_lut_q15.bin','golden/fused.i16']]
def recv(c,n):
 b=bytearray()
 while len(b)<n:
  x=c.recv(n-len(b))
  if not x:raise EOFError()
  b.extend(x)
 return bytes(b)
path=BASE/'hardware.sock'
if path.exists():path.unlink()
sock=socket.socket(socket.AF_UNIX);sock.bind(str(path));os.chown(path,int(os.environ.get('SUDO_UID','1000')),int(os.environ.get('SUDO_GID','1000')));os.chmod(path,0o600);sock.listen(2);sock.settimeout(1);quitting=False;fd=None;count_total=0
(BASE/'hardware.pid').write_text(str(os.getpid()))
def quit_signal(*args):
 global quitting
 quitting=True
signal.signal(signal.SIGTERM,quit_signal);signal.signal(signal.SIGINT,quit_signal)
print('FAST_SERVICE_READY',flush=True)
try:
 while not quitting:
  try:c,_=sock.accept()
  except socket.timeout:continue
  c.settimeout(150)
  try:
   variant,count=recv(c,2)
   if variant>2 or not 1<=count<=6:raise ValueError('Invalid batch header')
   raw=recv(c,count*2747520);begin=time.perf_counter();(params/'bench_frames').write_text(str(count));(params/'output_variant').write_text(str(variant))
   if fd is None:fd=os.open('/dev/kv260_joint_once',os.O_RDWR);fcntl.ioctl(fd,0x47e2);uploads=initial+[raw]
   else:fcntl.ioctl(fd,0x47e4);uploads=[raw]
   for data in uploads:
    view=memoryview(data)
    while view:
     n=os.write(fd,view)
     if n<=0:raise RuntimeError('Short upload')
     view=view[n:]
   fcntl.ioctl(fd,0x47e1);status=bytearray(736);fcntl.ioctl(fd,0x82e047e0,status,True);st=Status.from_buffer_copy(status)
   if st.error or st.pending or not st.completed or not st.guards_ok or st.reserved!=count:raise RuntimeError('Hardware status failed')
   output=bytearray();size=count*2747520
   while len(output)<size:
    b=os.read(fd,size-len(output))
    if not b:raise RuntimeError('Short output')
    output.extend(b)
   count_total+=count;info=json.dumps({'ok':True,'hardware_ms':st.elapsed_ns/1e6,'total_ms':(time.perf_counter()-begin)*1000,'count':count,'bytes':size,'build':'c6496c6dc89aa54c4500','mode':'six-slot-distinct-input','completed_total':count_total}).encode();c.sendall(struct.pack('!I',len(info))+info+output)
  except Exception as e:
   try:
    info=json.dumps({'ok':False,'error':str(e)}).encode();c.sendall(struct.pack('!I',len(info))+info)
   except Exception:pass
   print('FRAME_ERROR',repr(e),flush=True);raise
  finally:c.close()
finally:
 if fd is not None:os.close(fd)
 sock.close();path.unlink(missing_ok=True);(BASE/'hardware.pid').unlink(missing_ok=True)
