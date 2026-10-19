"""Download research assets with provenance; never execute downloaded code."""
import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.request
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parent/'data'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def download(url,destination):
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    receipt=destination.with_suffix(destination.suffix+'.source.json')
    if destination.exists():
        metadata=json.loads(receipt.read_text()) if receipt.exists() else {}
        if (metadata.get('sha256') or metadata.get('actual_sha256'))!=digest(destination):
            raise ValueError('Existing asset lacks matching receipt: '+str(destination))
        return str(destination)
    partial=destination.with_suffix(destination.suffix+'.part')
    last=None
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'FPGA-weather-research/0.1'})
            with urllib.request.urlopen(request,timeout=35) as response, partial.open('wb') as output:
                size=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>1024**3:raise ValueError('Asset exceeds 1 GiB bound')
                    output.write(chunk)
                expected=response.headers.get('Content-Length')
                if expected and size!=int(expected):raise IOError('Truncated download')
                final_url=response.url
            partial.replace(destination)
            receipt.write_text(json.dumps({'url':url,'resolved_url':final_url,
                'sha256':digest(destination),'bytes':size,'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'purpose':'research evaluation; original dataset/model terms apply',
                'hash_scope':'locally recorded download identity; not publisher signature'},indent=2),encoding='utf-8')
            print('DOWNLOADED',destination,size,flush=True)
            return str(destination)
        except Exception as error:
            last=error
            time.sleep(1)
    raise RuntimeError(f'Download failed: {url}: {last}')


def extract_images(archive,destination):
    """Whitelist image files, reject traversal; do not extract scripts or symlinks."""
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir() or Path(info.filename).suffix.lower() not in ('.png','.jpg','.jpeg','.bmp'):continue
            relative=Path(info.filename.replace('\\','/'))
            target=(destination/relative).resolve()
            if not target.is_relative_to(destination):raise ValueError('Unsafe archive member')
            if info.file_size>200*1024*1024:raise ValueError('Image exceeds extraction limit')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():continue
            target.write_bytes(z.read(info))


def assets():
    # Pin snapshots instead of silently changing branch-tip data on later runs.
    def revision(repo):
        url=f'https://api.github.com/repos/{repo}/commits/master'
        with urllib.request.urlopen(url,timeout=35) as response:return json.load(response)['sha']
    kair=revision('cszn/KAIR');aod=revision('Boyiliee/AOD-Net')
    jobs=[(f'https://raw.githubusercontent.com/cszn/KAIR/{kair}/testsets/set12/{i:02d}.png',ROOT/'clean_set12'/f'{i:02d}.png') for i in range(1,13)]
    jobs += [(f'https://raw.githubusercontent.com/Boyiliee/AOD-Net/{aod}/{name}',ROOT/'aod_reference'/Path(name).name)
             for name in ['AOD_Net.caffemodel','test/test_template.prototxt','data/img/canyon.jpg','data/img/gugong.jpg','data/img/man.jpg']]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for future in concurrent.futures.as_completed([pool.submit(download,*job) for job in jobs]):
            try:results.append({'path':future.result(),'status':'PASS'})
            except Exception as error:results.append({'status':'FAIL','error':str(error)})
    ROOT.mkdir(exist_ok=True)
    (ROOT/'download_status.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    if any(r['status']=='FAIL' for r in results):raise RuntimeError('Some assets failed; see download_status.json')


def synthetic():
    """Engineering-only synthetic pairs on Set12; NOT Rain100L/RESIDE benchmark."""
    clean=sorted((ROOT/'clean_set12').glob('*.png'))
    if len(clean)!=12:raise ValueError('Download all 12 Set12 sources first')
    for task in ('derain','dehaze'):
        folder=ROOT/f'synthetic_{task}'
        folder.mkdir(exist_ok=False)
        rows=[]
        for index,path in enumerate(clean):
            image=Image.open(path).convert('RGB')
            image.thumbnail((320,320),Image.Resampling.LANCZOS)
            x=np.asarray(image,dtype=np.float32)/255
            h,w=x.shape[:2]
            split='train' if index<8 else ('val' if index<10 else 'test')
            for variant in range(4):
                rng=np.random.default_rng(42000+index*17+variant)
                if task=='derain':
                    layer=Image.new('L',(w,h),0);draw=ImageDraw.Draw(layer)
                    for _ in range(int(h*w*rng.uniform(.003,.007))):
                        col,y=int(rng.integers(0,w)),int(rng.integers(-20,h))
                        draw.line((col,y,col+int(rng.integers(-6,7)),y+int(rng.integers(9,23))),
                                  fill=int(rng.integers(70,170)),width=1)
                    rain=np.asarray(layer.filter(ImageFilter.GaussianBlur(.4)),dtype=np.float32)/255
                    degraded=np.clip(x+(1-x)*rain[...,None],0,1)
                else:
                    # Smooth synthetic transmission, no measured scene depth.
                    yy,xx=np.mgrid[0:h,0:w]
                    depth=(.3+.7*(yy/max(h-1,1))+.15*np.sin(xx/w*6.28+rng.uniform(0,6)))
                    transmission=np.exp(-rng.uniform(.5,1.6)*depth)[...,None]
                    atmosphere=rng.uniform(.75,1.0,size=(1,1,3))
                    degraded=x*transmission+atmosphere*(1-transmission)
                identity=f'{index+1:02d}_{variant}'
                target=folder/f'{index+1:02d}_clean.png'
                if not target.exists():image.save(target)
                Image.fromarray(np.uint8(np.rint(degraded*255))).save(folder/f'{identity}_input.png')
                rows.append({'id':identity,'clean_id':f'Set12-{index+1:02d}','split':split,
                             'input':f'{identity}_input.png','target':target.name})
        (folder/'manifest.json').write_text(json.dumps({'task':task,'kind':'ENGINEERING_SYNTHETIC_SET12_NOT_ROAD_BENCHMARK',
            'seed':42000,'source':'../clean_set12/*.source.json','pairs':rows},indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['assets','synthetic','rain12','ohaze'])
    args=p.parse_args()
    if args.command=='assets':assets()
    elif args.command=='synthetic':synthetic()
    elif args.command=='rain12':
        archive=download('https://yu-li.github.io/paper/li_cvpr16_rain.zip',ROOT/'archives'/'rain12.zip')
        extract_images(archive,ROOT/'rain12_official')
    elif args.command=='ohaze':
        archive=download('https://data.vision.ee.ethz.ch/cvl/vision2/ntire18/o-haze/O-HAZE.zip',ROOT/'archives'/'ohaze.zip')
        extract_images(archive,ROOT/'ohaze_official')


if __name__=='__main__':main()
