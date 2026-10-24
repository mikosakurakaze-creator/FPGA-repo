"""Run the unchanged legacy board-fixture test with the new five-port idle map.

Only the diagnostic PS replacement boundary is injected in memory. No legacy
checkout or IP is edited. The original datapath/netlist remains verbatim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import sys
from grid_physical_path import build_path

p=argparse.ArgumentParser(__doc__)
p.add_argument('--reference',type=Path,required=True)
known,rest=p.parse_known_args()
reference=known.reference.resolve()
runner=reference/'tools/run_board_repro.py'
sys.path.insert(0,str(reference/'tools'))
import physical_system_repro
def build_legacy_path(source,target,interface):
    report=build_path(source,target,interface,core='weather_frame_top_0',selected=3,top_name='diagnostic_weather_path')
    # The legacy runner needs to know whether the unchanged export already
    # contains glbl before deciding to compile the vendor glbl.v separately.
    # Derive this from the actual emitted netlist, never from a fixed default.
    emitted=Path(target).read_text(encoding='utf-8')
    report['includes_glbl']=bool(re.search(r'\bmodule\s+glbl\b',emitted))
    return report
physical_system_repro.build_physical_path=build_legacy_path
sys.argv=[str(runner),*rest]
code=1
try:runpy.run_path(str(runner),run_name='__main__')
except SystemExit as e:code=int(e.code or 0)
output=Path(rest[rest.index('--output')+1])
record=output/'run.json'
if record.is_file():
    report=json.loads(record.read_text(encoding='utf-8'))
    snapshot=output/'executed_boundary_adapter';snapshot.mkdir(exist_ok=False)
    for f in [Path(__file__).resolve(),Path(__file__).with_name('grid_physical_path.py')]:shutil.copy2(f,snapshot/f.name)
    report['injected_boundary_adapter_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in snapshot.iterdir()}
    report['boundary_adapter_scope']='five-port system, new GridDehazeNet port held idle; unchanged legacy test arithmetic and actual netlist'
    pending=output/'run.pending.json';pending.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');pending.replace(record)
raise SystemExit(code)
