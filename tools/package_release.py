"""Collect only a timing-clean, audited build as a local board candidate.

Never uploads, programs hardware, or labels the candidate board-tested.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--hls',type=Path,required=True)
p.add_argument('--sequence',type=Path,required=True)
p.add_argument('--vendor-sequence',type=Path,required=True)
p.add_argument('--host-report',type=Path,required=True)
p.add_argument('--driver-report',type=Path,required=True)
p.add_argument('--delivery',type=Path,required=True,help='read-only manifest-verified A a_compute')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--experiment',choices=('onchip_frame','stream_frame'),default='onchip_frame')
p.add_argument('--report',type=Path,help='current integration Markdown report; defaults to original system report')
a=p.parse_args();b=a.build.resolve();out=a.output.resolve()
root=Path(__file__).resolve().parents[1]
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
build=json.loads((b/'build.json').read_text())
for stage in ('create','synth','impl','package'):
    if not build['stages'].get(stage,{}).get('pass'):raise RuntimeError('system stage not passed: '+stage)
    expected=build['stages'][stage]['script_sha256']
    if sha(b/(stage+'.tcl'))!=expected or sha(root/'system'/(stage+'.tcl'))!=expected:
        raise RuntimeError('build recipe differs from executed stage: '+stage)
    if sha(b/(stage+'_console.log'))!=build['stages'][stage]['console_sha256']:
        raise RuntimeError('executed build log differs: '+stage)
for rel,expected in build['input_files'].items():
    if sha(b/rel)!=expected:raise RuntimeError('frozen system input differs: '+rel)
for path in (a.hls/'run.json',a.sequence/'run.json',a.vendor_sequence/'run.json',
             a.host_report,a.driver_report,b/'interface_final_audit.json'):
    if not json.loads(path.read_text())['pass']:raise RuntimeError('verification not passed: '+str(path))
# Detailed function/loop reports must travel with the HLS claim, not only logs.
for task in ('derain','dehaze'):
    reports=a.hls/task/'component/hls/syn/report'
    if not (reports/'weather_frame_top_csynth.xml').is_file() or not list(reports.glob('*csynth.rpt')):
        raise RuntimeError('detailed HLS reports absent: '+task)
timing=(b/'routed_timing.rpt').read_text(errors='replace')
summary=re.search(r'WNS\(ns\).*?WPWS\(ns\).*?\n\s*-[-\s]+\n\s*([^\n]+)',timing,re.S)
if not summary:raise RuntimeError('timing summary missing')
fields=summary.group(1).split()
if len(fields)!=12:raise RuntimeError('unexpected timing summary fields: '+str(fields))
for i in (0,1,4,5,8,9):
    if float(fields[i])<0:raise RuntimeError('negative timing slack/sum')
for i in (2,6,10):
    if int(fields[i])!=0:raise RuntimeError('failing timing endpoints')
timing_checks=dict(re.findall(r'^\d+\.\s+checking\s+(\w+)\s+\((\d+)\)',timing,re.M))
if len(timing_checks)!=12 or any(int(n) for n in timing_checks.values()):
    raise RuntimeError('missing/nonzero check_timing categories: '+str(timing_checks))
route=(b/'route_status.rpt').read_text(errors='replace')
route_counts={name:int(re.search(r'# of '+name+r'\.+\s*:\s*(\d+)',route).group(1))
              for name in ('routable nets','fully routed nets','nets with routing errors')}
if (route_counts['routable nets']<=0 or route_counts['routable nets']!=route_counts['fully routed nets']
        or route_counts['nets with routing errors']):
    raise RuntimeError('routing incomplete: '+str(route_counts))
drc=(b/'routed_drc.rpt').read_text(errors='replace')
drc_rows=re.findall(r'^\|\s*([A-Z][A-Z0-9]+-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|$',drc,re.M)
if sum(int(n) for _,_,_,n in drc_rows)!=int(re.search(r'Checks found:\s*(\d+)',drc).group(1)):
    raise RuntimeError('DRC summary incomplete')
if any(severity in ('Error','Critical Warning') for _,severity,_,_ in drc_rows):
    raise RuntimeError('blocking routed DRC violation')
qualification={'pass':True,'timing_summary_fields':fields,'check_timing':timing_checks,
               'route':route_counts,'drc':[{'rule':rule,'severity':severity,'description':desc,'count':int(n)}
                                         for rule,severity,desc,n in drc_rows],
               'scope':'offline routed hardware qualification; no board execution'}
# Make sure the exercised HLS RTL is precisely the copied system IP RTL.
rtl=b/'ip/weather/hdl/verilog'
sequence_report=json.loads((a.sequence/'run.json').read_text())
vendor_report=json.loads((a.vendor_sequence/'run.json').read_text())
for rel,expected in sequence_report.get('test_source_sha256',{}).items():
    if sha(root/rel)!=expected:raise RuntimeError('current independent RTL test differs: '+rel)
for path,expected in vendor_report.get('source_sha256',{}).items():
    if sha(Path(path))!=expected:raise RuntimeError('current vendor sequence source differs: '+path)
if 'simulation_log_sha256' in sequence_report:
    if sha(a.sequence/'simulation.log')!=sequence_report['simulation_log_sha256']:
        raise RuntimeError('independent RTL log differs')
sim=a.sequence/'component/hls/syn/verilog'
if sequence_report.get('verification_kind')=='independent_axi_rtl':
    sim=a.sequence
    required_frames=9 if a.experiment=='stream_frame' else 7
    if len(sequence_report.get('frames',[]))!=required_frames:
        raise RuntimeError('independent RTL sequence incomplete')
    if a.experiment=='stream_frame' and (not sequence_report.get('full_frame_performance') or len(sequence_report.get('performance_frames',[]))!=2):
        raise RuntimeError('both-model full-frame RTL performance evidence absent')
    if a.experiment=='stream_frame':
        performance={}
        for line in sequence_report['performance_frames']:
            match=re.search(r'task=([01]) shape=720x1280 cycles=(\d+)\b',line)
            if not match:raise RuntimeError('invalid full-frame RTL performance record')
            performance[int(match[1])]=int(match[2])
        if set(performance)!={0,1} or any(n<=0 or n>3333333 for n in performance.values()):
            raise RuntimeError('720p30 RTL cycle budget not passed: '+str(performance))
for f in rtl.iterdir():
    if not f.is_file() or f.suffix not in ('.v','.dat'):continue
    if not (sim/f.name).is_file() or sha(f)!=sha(sim/f.name):
        raise RuntimeError('system/sequence RTL differs: '+f.name)
vendor=a.vendor_sequence/'component/hls/syn/verilog'
# Vendor cosim consumes the primary synthesis files. IP export additionally
# inserts a simulation-only DATAFLOW deadlock detector into the packaged top.
# Compare vendor cosim byte-for-byte with its actual synthesis input; the
# independent AXI test above separately requires the exact packaged RTL/ROM.
primary=a.hls/'derain/component/hls/syn/verilog'
primary_files={f.name for f in primary.iterdir() if f.is_file() and f.suffix in ('.v','.dat')}
vendor_files={f.name for f in vendor.iterdir() if f.is_file() and f.suffix in ('.v','.dat')}
if not primary_files or primary_files!=vendor_files:
    raise RuntimeError('primary/vendor-sequence RTL/ROM file set differs')
for name in primary_files:
    if sha(primary/name)!=sha(vendor/name):
        raise RuntimeError('primary/vendor-sequence RTL/ROM differs: '+name)
host=json.loads(a.host_report.read_text())
hls=json.loads((a.hls/'run.json').read_text())
if host.get('source_sha256')!=hls.get('source_sha256'):
    raise RuntimeError('host and HLS experiment sources differ')
experiment=root/'experiments'/a.experiment
for rel,expected in hls['source_sha256'].items():
    if sha(experiment/rel)!=expected:raise RuntimeError('current experiment differs: '+rel)
driver=json.loads(a.driver_report.read_text())
for rel,expected in driver['source_sha256'].items():
    if sha(root/rel)!=expected:raise RuntimeError('current driver/core source differs: '+rel)
delivery=a.delivery.resolve();a_manifest=delivery.parents[1]/'DELIVERY_MANIFEST.json'
if sha(a_manifest)!=host['a_delivery_manifest_sha256']:
    raise RuntimeError('A manifest identity differs')
for rel,expected in host['fixture_sha256'].items():
    if sha(delivery/rel)!=expected:raise RuntimeError('A fixture differs: '+rel)
with zipfile.ZipFile(b/'weather_system.xsa') as z:
    if z.testzip() is not None:raise RuntimeError('XSA CRC failure')
    bit=next(n for n in z.namelist() if n.endswith('.bit'))
    if z.read(bit)!=(b/'weather_system.bit').read_bytes():raise RuntimeError('embedded bit mismatch')
out.mkdir(parents=True,exist_ok=False)
for name in ('weather_system.bit','weather_system.xsa','system_routed.dcp','routed_utilization.rpt',
             'routed_utilization_summary.rpt','routed_timing.rpt','route_status.rpt','routed_drc.rpt','interface_final_audit.json',
             'build.json','system_recreate.tcl','system_seed.bd'):
    shutil.copy2(b/name,out/name)
shutil.copytree(root/'deployment',out/'recipe/deployment',ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(root/'system',out/'recipe/system')
shutil.copytree(root/'tools',out/'recipe/tools',ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(root/'experiments/onchip_frame',out/'recipe/experiments/onchip_frame',ignore=shutil.ignore_patterns('__pycache__'))
if a.experiment!='onchip_frame':
    shutil.copytree(experiment,out/'recipe/experiments'/a.experiment,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(b/'ip',out/'ip_repo')
shutil.copy2(a.hls/'run.json',out/'hls_run.json')
shutil.copy2(a.sequence/'run.json',out/'sequence_run.json')
verification=out/'verification';verification.mkdir()
system_evidence=verification/'system';system_evidence.mkdir()
for stage in ('create','synth','impl','package'):
    shutil.copy2(b/(stage+'_console.log'),system_evidence/(stage+'_console.log'))
shutil.copy2(b/'project/weather_system.runs/system_weather_frame_top_0_0_synth_1/runme.log',
             system_evidence/'weather_ooc_synth.log')
shutil.copy2(b/'interface_audit.json',system_evidence/'interface_audit.json')
lineage=json.loads((root/'evidence/system_lineage_20261020.json').read_text())
for name in ('lowlight_rebuild','writer_overlay_audit'):
    report=lineage['reports'][name]
    source=Path(report['path'])
    if sha(source)!=report['sha256']:raise RuntimeError('lineage report differs: '+name)
    shutil.copy2(source,system_evidence/(name+'.json'))
(out/'implementation_qualification.json').write_text(json.dumps(qualification,indent=2)+'\n',encoding='utf-8')
shutil.copy2(a.vendor_sequence/'run.json',verification/'vendor_sequence_run.json')
shutil.copy2(a.vendor_sequence/'cosim.log',verification/'vendor_sequence_cosim.log')
shutil.copy2(a.host_report,verification/'host_verification.json')
shutil.copy2(a.driver_report,verification/'driver_verification.json')
for name in ('simulation.log','negative_control.log','cosim.log','host.log'):
    if (a.sequence/name).is_file():shutil.copy2(a.sequence/name,verification/name)
for f in a.sequence.glob('*.hex'):shutil.copy2(f,verification/f.name)
for name in ('derain','dehaze'):
    dest=verification/name;dest.mkdir()
    shutil.copytree(a.hls/name/'component/hls/syn/report',dest/'hls_syn_report')
    sim_reports=a.hls/name/'component/hls/sim/report'
    if sim_reports.is_dir():shutil.copytree(sim_reports,dest/'hls_sim_report')
    for f in ('csim.log','synth.log','cosim.log','package.log','official_input.bin','official_output.bin','cosim_input.bin','cosim_output.bin'):
        if (a.hls/name/f).is_file():shutil.copy2(a.hls/name/f,dest/f)
shutil.copytree(root/'docs',out/'recipe/docs')
shutil.copytree(root/'evidence',out/'recipe/evidence')
shutil.copy2(root/'README.md',out/'recipe/README.md')
fixture_root=out/'verification/a_delivery'
fixture_root.mkdir()
shutil.copy2(a_manifest,fixture_root/'DELIVERY_MANIFEST.json')
for rel in host['fixture_sha256']:
    source=delivery/rel
    dest=fixture_root/'weather_restore_lab/a_compute'/rel
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
(fixture_root/'README.md').write_text(
    'Verified fixture subset, not the entire A delivery. The original manifest is preserved.\n'
    'For host/HLS reproduction use weather_restore_lab/a_compute/ as --delivery.\n'
    'Files used by the current host/HLS runner are included; unrelated manifest payloads are intentionally absent.\n',encoding='utf-8')
shutil.copy2(a.report or root/'docs/system_integration_20261020.md',out/'integration_report.md')
status={'hardware_candidate':'TIMING_CLEAN_BIT_XSA','board':'NOT_TESTED',
        'standalone_elf':'NOT_BUILT_MISSING_A53_TOOLCHAIN','linux_dma':'NOT_IMPLEMENTED',
        'camera_display':'NOT_INTEGRATED','sustained_720p_fps':'NOT_MEASURED',
        'timing_summary_fields':fields,'experiment':a.experiment,
        'full_frame_rtl_performance':sequence_report.get('performance_frames',[])}
(out/'status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
(out/'README.md').write_text('''# K26 Low-light + Weather board candidate

Hardware build: Vivado/Vitis 2025.2, xck26-sfvc784-2LV-c, nominal PL0 100 MHz.
This is a new timing-clean bitstream/XSA candidate; no board test was performed.

Control map: Bilinear A0000000, Curve A0010000, low-light CNN A0020000,
Weather Frame A0030000 (64 KiB each). Weather ABI v2 is RGB NCHW signed16 Q14,
H<=720 W<=1280, task 0 derain / 1 dehaze, independent input/output DDR buffers.
Weather input uses HP0 and output HP3; no AXI Stream or external scratch.

Use the board's supported boot/FPGA manager or reviewed JTAG bring-up procedure
for this exact XSA/bit identity. Never reuse historical scratch addresses as
allocated memory. No automatic board/program/reset actions are supplied here.

The standalone PS source and explicit cache/MMIO backend are under recipe/deployment/.
An ELF was NOT built: install matching Vitis Embedded A53 tools and execute
recipe/tools/run_standalone.py through recipe/tools/run_windows_desktop.py.
The ELF is a separately launched 8x8 Golden/guard test, not a Linux application.
Linux DMA/cache allocation, camera/display, sustained FPS and real board
validation remain open. See integration_report.md and status.json.

Reproduction inputs: system_seed.bd and ip_repo/; recipe/system and recipe/tools
contain the staged build drivers. Choose a NEW output directory. Keep the
primary host/HLS reports. verification/a_delivery/ contains the original A
manifest and only the verified fixtures used by these runners; use its
weather_restore_lab/a_compute/ subdirectory as --delivery. This subset is not
the full A delivery. Historical runtime paths in reports are provenance.
manifest.json records the SHA-256/size of every collected local payload file.
''',encoding='utf-8')
files={f.relative_to(out).as_posix():{'bytes':f.stat().st_size,'sha256':sha(f)}
       for f in sorted(out.rglob('*')) if f.is_file()}
(out/'manifest.json').write_text(json.dumps({'files':files,'status':status},indent=2)+'\n',encoding='utf-8')
print('WEATHER_LOCAL_RELEASE_PASS',out,'FILES',len(files))
