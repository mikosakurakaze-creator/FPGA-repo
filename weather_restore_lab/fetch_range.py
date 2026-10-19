"""Bounded parallel HTTP ranges, resumable parts, optional publisher SHA-256."""
import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.request
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True);p.add_argument('--output',required=True)
    p.add_argument('--bytes',type=int,required=True);p.add_argument('--sha256')
    p.add_argument('--workers',type=int,default=6);p.add_argument('--part-mib',type=int,default=2)
    args=p.parse_args()
    if args.bytes<=0 or not 1<=args.workers<=12 or not 1<=args.part_mib<=16:raise ValueError('Invalid bounds')
    destination=Path(args.output).resolve()
    if destination.exists():raise FileExistsError(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    parts=destination.with_suffix(destination.suffix+'.ranges');parts.mkdir(exist_ok=True)
    identity={'url':args.url,'bytes':args.bytes,'sha256':args.sha256,'part_mib':args.part_mib}
    manifest=parts/'source.json'
    if manifest.exists() and json.loads(manifest.read_text())!=identity:raise ValueError('Resume identity differs')
    manifest.write_text(json.dumps(identity,indent=2))
    part_size=args.part_mib*1024*1024
    count=(args.bytes+part_size-1)//part_size
    def fetch(index):
        start=index*part_size;end=min(args.bytes,start+part_size)-1
        path=parts/f'{index:06d}.part'
        if path.exists() and path.stat().st_size==end-start+1:return index
        last=None
        for attempt in range(3):
            try:
                request=urllib.request.Request(args.url,headers={'Range':f'bytes={start}-{end}',
                    'Accept-Encoding':'identity','User-Agent':'FPGA-weather-research/0.1'})
                with urllib.request.urlopen(request,timeout=25) as response:
                    expected=f'bytes {start}-{end}/{args.bytes}'
                    if response.status!=206 or response.headers.get('Content-Range')!=expected:
                        raise ValueError('Range identity/size differs: '+str(response.headers.get('Content-Range')))
                    data=response.read(end-start+2)
                if len(data)!=end-start+1:raise IOError('Incomplete or overlong range')
                path.write_bytes(data)
                return index
            except Exception as error:last=error;time.sleep(1)
        raise RuntimeError(f'Range {index} failed: {last}')
    started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(fetch,i) for i in range(count)]
        try:
            for done,future in enumerate(concurrent.futures.as_completed(futures),1):
                future.result()
                if done%16==0 or done==count:print(f'parts={done}/{count} seconds={time.monotonic()-started:.1f}',flush=True)
        except Exception:
            for future in futures:future.cancel()
            raise
    temporary=destination.with_suffix(destination.suffix+'.assembling')
    h=hashlib.sha256()
    with temporary.open('wb') as output:
        for index in range(count):
            data=(parts/f'{index:06d}.part').read_bytes();h.update(data);output.write(data)
    actual=h.hexdigest()
    if args.sha256 and actual.lower()!=args.sha256.lower():raise ValueError('Publisher SHA256 mismatch; file not installed')
    temporary.replace(destination)
    destination.with_suffix(destination.suffix+'.source.json').write_text(json.dumps({**identity,
        'actual_sha256':actual,'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2))
    print('COMPLETE',destination,actual,flush=True)


if __name__=='__main__':main()
