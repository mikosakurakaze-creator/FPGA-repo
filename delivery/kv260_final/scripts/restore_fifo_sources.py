"""Install all 132 frozen sim/synth wrappers after Vivado BD generation."""
import argparse,hashlib,json,shutil
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['apply','verify']);p.add_argument('root',type=Path);a=p.parse_args();root=a.root.resolve();frozen=root/'frozen_smartconnect';files=sorted(frozen.rglob('*.sv'));assert len(files)==132,len(files)
    rows=[]
    for source in files:
        relative=source.relative_to(frozen);target=root/relative
        assert target.is_file(),'Vivado generated source missing: '+str(relative)
        if a.mode=='apply':shutil.copyfile(source,target)
        assert target.read_bytes()==source.read_bytes(),'FIFO source mismatch: '+str(relative)
        rows.append(dict(path=relative.as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    if a.mode=='apply':(root/'frozen_fifo_restore.json').write_text(json.dumps(rows,indent=2))
    print('FROZEN_FIFO_PASS',a.mode,len(rows))
if __name__=='__main__':main()
