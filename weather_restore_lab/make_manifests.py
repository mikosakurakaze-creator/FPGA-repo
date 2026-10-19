"""Prepare explicit, local experimental split manifests; never mix benchmarks."""
import argparse
import json
import random
from pathlib import Path
from PIL import Image
from public_data import extract_images,digest

ROOT=Path(__file__).resolve().parent/'data'


def rainlight():
    for name in ('RainTrainL','Rain100L'):
        archive=ROOT/'archives'/(name+'.zip')
        # gdown outputs final pathname only after a successful download.
        if not archive.is_file():raise FileNotFoundError(archive)
        extract_images(archive,ROOT/name)
    def pairs(folder):
        inputs={};targets={}
        for path in sorted(folder.rglob('*.png')):
            lower=path.name.lower()
            table=targets if 'norain' in lower else (inputs if lower.startswith('rain-') else None)
            if table is None:continue
            key=lower.rsplit('-',1)[-1].split('.')[0]
            if key in table:raise ValueError('Duplicate pair number: '+str(path))
            table[key]=path
        if set(inputs)!=set(targets):raise ValueError('Unpaired RainLight data')
        return [(k,inputs[k],targets[k]) for k in sorted(inputs,key=int)]
    training=pairs(ROOT/'RainTrainL');testing=pairs(ROOT/'Rain100L')
    if len(training)!=200 or len(testing)!=100:
        raise ValueError(f'Expected original RainTrainL/Rain100L 200/100 pairs, got {len(training)}/{len(testing)}')
    random.Random(42).shuffle(training)
    rows=[]
    for source,items in (('RainTrainL',training),('Rain100L',testing)):
        for i,(key,a,b) in enumerate(items):
            split='test' if source=='Rain100L' else ('train' if i<180 else 'val')
            rows.append({'id':source+'-'+key,'clean_id':source+'-'+key,'split':split,
                         'input':a.relative_to(ROOT).as_posix(),'target':b.relative_to(ROOT).as_posix()})
    target=ROOT/'rainlight_manifest.json'
    if target.exists():raise FileExistsError(target)
    target.write_text(json.dumps({'task':'derain','kind':'RAINTRAINL_CUSTOM_180_20_VALIDATION_RAIN100L_TEST',
        'split_note':'Original 200 training sources split 180/20 with seed42; original100 test pairs preserved',
        'archives_sha256':{name:digest(ROOT/'archives'/(name+'.zip')) for name in ('RainTrainL','Rain100L')},
        'redistribution_source':'https://github.com/bupt-ai-cz/ANRN, Google Drive Rain100H-Rain100L folder',
        'pairs':rows},indent=2),encoding='utf-8')


def derain_bootstrap():
    source=ROOT/'synthetic_derain'/'manifest.json'
    manifest=json.loads(source.read_text())
    rows=[]
    for row in manifest['pairs']:
        if row['split']=='test':continue
        item=dict(row)
        item['input']='synthetic_derain/'+item['input']
        item['target']='synthetic_derain/'+item['target']
        rows.append(item)
    for path in sorted((ROOT/'rain12_official').glob('*_in.png')):
        key=path.stem.split('_')[0]
        rows.append({'id':'Rain12-'+key,'clean_id':'Rain12-'+key,'split':'test',
                     'input':'rain12_official/'+path.name,'target':f'rain12_official/{key}_GT.png'})
    if sum(row['split']=='test' for row in rows)!=12:raise ValueError('Expected official Rain12 twelve pairs')
    target=ROOT/'derain_bootstrap_manifest.json'
    if target.exists():raise FileExistsError(target)
    target.write_text(json.dumps({'task':'derain',
        'kind':'BOOTSTRAP_SYNTHETIC_SET12_TRAIN_VAL_OFFICIAL_RAIN12_TEST',
        'limitations':'Not trained on RainTrainL; engineering baseline, not a standard benchmark reproduction',
        'pairs':rows},indent=2),encoding='utf-8')


def ohaze():
    hazy=sorted((ROOT/'ohaze_official').rglob('*hazy.jpg'))
    if len(hazy)!=45:raise ValueError(f'Expected 45 O-HAZE pairs, got {len(hazy)}')
    folder=ROOT/'ohaze_custom_800'
    if folder.exists() and any(folder.iterdir()):raise FileExistsError(folder)
    folder.mkdir(exist_ok=True)
    pairs=[]
    for path in hazy:
        key=path.stem[:-5]
        candidates=list((ROOT/'ohaze_official').rglob(key+'_GT.jpg'))
        if len(candidates)!=1:raise ValueError('Cannot locate GT for '+key)
        pairs.append((key,path,candidates[0]))
    random.Random(42).shuffle(pairs)
    rows=[]
    for i,(key,a,b) in enumerate(pairs):
        split='train' if i<30 else ('val' if i<35 else 'test')
        for name,path in (('input',a),('target',b)):
            with Image.open(path) as image:
                image=image.convert('RGB');image.thumbnail((800,800),Image.Resampling.LANCZOS)
                image.save(folder/f'{key}_{name}.png')
        rows.append({'id':key,'clean_id':'OHAZE-'+key,'split':split,
                     'input':key+'_input.png','target':key+'_target.png'})
    (folder/'manifest.json').write_text(json.dumps({'task':'dehaze',
        'kind':'OHAZE_CUSTOM_30_5_10_SCENE_SPLIT_MAX800_NOT_OFFICIAL_CHALLENGE_SPLIT',
        'seed':42,'pairs':rows},indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['derain-bootstrap','ohaze','rainlight'])
    args=p.parse_args()
    {'derain-bootstrap':derain_bootstrap,'ohaze':ohaze,'rainlight':rainlight}[args.command]()
