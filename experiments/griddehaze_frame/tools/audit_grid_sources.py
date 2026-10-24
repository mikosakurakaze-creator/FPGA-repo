"""Compare all five generated synthesis payloads with the frozen IP snapshots."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from preflight import sha,save

p=argparse.ArgumentParser(__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--require-synth',action='store_true')
a=p.parse_args();b=a.build.resolve()
manifest=json.loads((b/'build.json').read_text(encoding='utf-8'))
ns={'s':'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
gen=b/'project/weather_system.gen/sources_1/bd/system'
cores={'cnn':'zero_dce_cnn_top','bilinear':'bilinear_fixed16_buffered',
       'curve':'curve_image_fixed16','weather':'weather_frame_top','griddehaze':'griddehaze_frame_top'}
records={};checks={}
for name,top in cores.items():
    ip=b/'ip'/name;component=ET.parse(ip/'component.xml')
    fs=[f for f in component.findall('s:fileSets/s:fileSet',ns)
        if f.findtext('s:name',namespaces=ns)=='xilinx_verilogsynthesis_view_fileset']
    if len(fs)!=1:raise RuntimeError('Synthesis file set absent '+name)
    payload=[ip/f.findtext('s:name',namespaces=ns) for f in fs[0].findall('s:file',ns)
             if Path(f.findtext('s:name',namespaces=ns)).suffix in ['.v','.dat']]
    tops=list((gen/'ipshared').glob('*/hdl/verilog/'+top+'.v'))
    if len(tops)!=1:raise RuntimeError('Generated top ambiguous '+name)
    staged=gen/'ip'/('system_'+top+'_0_0')
    log=b/'project/weather_system.runs'/('system_'+top+'_0_0_synth_1')/'runme.log'
    synthesis=log.read_text(errors='replace') if a.require_synth else None
    entries=[]
    for source in payload:
        rel=source.relative_to(b).as_posix()
        expected=manifest['input_files'][rel]
        actual=(staged/'hdl/verilog'/source.name) if source.suffix=='.dat' else tops[0].parent/source.name
        exact=sha(source)==expected and actual.is_file() and sha(actual)==expected
        entry=dict(source=rel,generated=actual.relative_to(b).as_posix(),sha256=expected,exact=exact)
        if synthesis is not None and source.suffix=='.dat':
            entry['rom_loaded']=("$readmem data file './"+source.name+"' is read successfully") in synthesis
            exact=exact and entry['rom_loaded']
        entries.append(entry)
        checks[name+'/'+source.name]=exact
    if synthesis is not None:
        checks[name+'/synthesis_completed']='synth_design completed successfully' in synthesis
    records[name]=entries
report=dict(pass_result=all(checks.values()),kind='actual_generated_five_core_source_audit',
            require_synth=a.require_synth,build_manifest_sha256=sha(b/'build.json'),
            checks=checks,cores=records,scope='generated Verilog/ROM bytes and optional actual synthesis log, not routed arithmetic or board execution')
save(a.out,report)
print(json.dumps(dict(pass_result=report['pass_result'],files=sum(map(len,records.values())),
                     checks=len(checks),failed=[k for k,v in checks.items() if not v]),indent=2))
raise SystemExit(0 if report['pass_result'] else 1)
