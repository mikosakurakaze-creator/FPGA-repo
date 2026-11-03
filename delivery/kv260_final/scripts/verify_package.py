"""Offline integrity check; never accesses FPGA devices."""
import argparse, hashlib, json, ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');a=ap.parse_args()
    manifest=ROOT/'SHA256SUMS'
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and p!=manifest and '__pycache__' not in p.parts and not any(x in p.parts for x in ['deps','results','build']))
    if a.write:
        manifest.write_text(''.join(sha(p)+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in files),encoding='utf-8',newline='\n')
    rows=[line.split('  ',1) for line in manifest.read_text(encoding='utf-8').splitlines()]
    for expected,name in rows:
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and sha(p)==expected,name
    hw=ROOT/'hardware'
    for line in (hw/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);assert sha(hw/name)==expected,'hardware/'+name
    for p in (ROOT/'ps').rglob('*.py'):
        if '__pycache__' not in p.parts and 'deps' not in p.parts:ast.parse(p.read_text(encoding='utf-8'))
    assert 'FPS' not in (ROOT/'ps/app.py').read_text(encoding='utf-8')
    m=json.loads((hw/'manifest.json').read_text());assert m['build_id']=='c6496c6dc89aa54c4500'
    print('PACKAGE_VERIFY_PASS files=%d build=%s'%(len(rows),m['build_id']))
if __name__=='__main__':main()
