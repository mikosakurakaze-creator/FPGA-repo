"""Compare actual service RGB output against all three frozen Q14 Goldens."""
import argparse,hashlib,json,socket,struct,time,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def recv(c,n):
    b=bytearray()
    while len(b)<n:
        v=c.recv(n-len(b))
        if not v:raise RuntimeError('Service disconnected')
        b.extend(v)
    return bytes(b)
def main():
    p=argparse.ArgumentParser();p.add_argument('--socket',type=Path,default=ROOT/'ps/hardware.sock');p.add_argument('--hardware',type=Path,default=ROOT/'hardware');p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=1);a=p.parse_args()
    assert 1<=a.frames<=6
    assert not a.out.exists(),'Preserve prior validation'
    rows=[];raw=(a.hardware/'golden/rgb.u8').read_bytes()
    for variant,name,golden in [(0,'lowlight','lowlight.i16'),(1,'derain_dehaze','d_output.i16'),(2,'fused','fused.i16')]:
        q=np.fromfile(a.hardware/'golden'/golden,dtype='<i2').astype(np.int32).reshape(3,720,1272)
        expected=np.clip((q*255+8192)//16384,0,255).astype(np.uint8).transpose(1,2,0).tobytes()
        with socket.socket(socket.AF_UNIX) as c:
            c.settimeout(150);c.connect(str(a.socket));c.sendall(bytes([variant,a.frames])+raw*a.frames)
            meta=json.loads(recv(c,struct.unpack('!I',recv(c,4))[0]));assert meta['ok'],meta
            data=recv(c,meta['bytes'])
        assert len(data)==len(expected)*a.frames
        mismatches=sum(x!=y for x,y in zip(data,expected*a.frames));assert mismatches==0,(name,mismatches)
        rows.append(dict(branch=name,frames=a.frames,mismatched_bytes=mismatches,output_sha256=hashlib.sha256(data).hexdigest(),metadata=meta))
        a.out.parent.mkdir(parents=True,exist_ok=True);(a.out.parent/(a.out.stem+'_'+name+'.rgb')).write_bytes(data)
        print('GOLDEN_PASS',name,a.frames,flush=True)
    a.out.write_text(json.dumps(dict(pass_all=True,build_id='c6496c6dc89aa54c4500',scope='RGB8 outputs versus Q14 Goldens after exact driver conversion',cases=rows),indent=2)+'\n')
if __name__=='__main__':main()
