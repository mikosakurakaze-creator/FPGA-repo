from engine import recv,BASE
import socket,struct,json,time,hashlib
from pathlib import Path
inputs=Path('/home/ubuntu/dawn_detection500');rows=json.loads((inputs/'manifest.json').read_text())['samples'][:6];raw=b''.join((inputs/r['rgb']).read_bytes() for r in rows);report=[]
for variant,name in enumerate(['lowlight','d','fused']):
 begin=time.perf_counter()
 with socket.socket(socket.AF_UNIX) as c:
  c.settimeout(150);c.connect(str(BASE/'hardware.sock'));c.sendall(bytes([variant,6])+raw);meta=json.loads(recv(c,struct.unpack('!I',recv(c,4))[0]));assert meta['ok'],meta;data=recv(c,meta['bytes'])
 for i,r in enumerate(rows):
  expected=(Path('/home/ubuntu/fusion_ablation_v1/dawn')/(r['id']+'.'+name+'.rgb')).read_bytes();assert data[i*2747520:(i+1)*2747520]==expected,(name,r['id'])
 report.append({'branch':name,'frames':6,'hardware_ms':meta['hardware_ms'],'call_seconds':time.perf_counter()-begin,'bit_exact':True});print('BATCH_PASS',report[-1],flush=True)
# Exercise varying batch length with retained models.
for count in [1,3,6,2,6]:
 with socket.socket(socket.AF_UNIX) as c:
  c.settimeout(150);c.connect(str(BASE/'hardware.sock'));c.sendall(bytes([2,count])+raw[:count*2747520]);meta=json.loads(recv(c,struct.unpack('!I',recv(c,4))[0]));assert meta['ok'],meta;data=recv(c,meta['bytes'])
 for i,r in enumerate(rows[:count]):assert data[i*2747520:(i+1)*2747520]==(Path('/home/ubuntu/fusion_ablation_v1/dawn')/(r['id']+'.fused.rgb')).read_bytes()
 print('TAIL_BATCH_PASS',count,flush=True)
(BASE/'fast_driver_validation.json').write_text(json.dumps({'branches':report,'tail_batches':[1,3,6,2,6],'all_bit_exact':True},indent=2))
