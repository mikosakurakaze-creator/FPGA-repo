"""Collect identified reports for review without publishing datasets, weights or tools caches."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import time
from preflight import ROOT, save, sha


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--with-elementwise',action='store_true',help='also collect the additive-integration operator work')
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    records={}
    selections={
        'preflight02':['package_audit.json','alternative_int8_audit.json',*[f'memory_{h}x{w}.json' for h,w in ((4,4),(32,48),(33,47),(34,46),(675,1280),(720,1280))]],
        'cpp05':['summary.json','test_math.json'],
        'tile02':['summary.json','test_math.json','a_comparator_random.json'],
        'cpp_large01':['summary.json','execute_foggy001_675x1280.json','foggy001_675x1280/comparison.json','foggy001_675x1280/node_hashes.txt'],
        'cpp_720p01':['summary.json','execute_random_720x1280.json','random_720x1280/comparison.json','random_720x1280/node_hashes.txt'],
        'hls02':['result.json','version.log','csim.log','synth.log','hls_config.cfg',
                 'component/hls/syn/report/griddehaze_conv_tile_top_csynth.rpt',
                 'component/hls/syn/report/griddehaze_conv_tile_top_csynth.xml',
                 'component/hls/impl/ip/drivers/griddehaze_conv_tile_top_v1_0/src/xgriddehaze_conv_tile_top_hw.h']}
    if a.with_elementwise:
        selections.update({
            'operators02':['summary.json','test_math.json'],
            'elementwise_native02':['result.json','compile.log','native.log'],
            'elementwise_hls02':['result.json','version.log','csim.log','synth.log','hls_config.cfg',
                'component/hls/syn/report/griddehaze_elementwise_top_csynth.rpt',
                'component/hls/syn/report/griddehaze_elementwise_top_csynth.xml',
                'component/hls/impl/ip/drivers/griddehaze_elementwise_top_v1_0/src/xgriddehaze_elementwise_top_hw.h']})
    for run,files in selections.items():
        for relative in files:
            source=ROOT/'work'/run/relative
            target=a.out/run/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            records[target.relative_to(a.out).as_posix()]=dict(bytes=target.stat().st_size,sha256=sha(target),source=str(source))
    for run in ('cpp05','tile02',*(['operators02'] if a.with_elementwise else [])):
        for source in (ROOT/'work'/run).glob('*/comparison.json'):
            target=a.out/run/source.relative_to(ROOT/'work'/run)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            records[target.relative_to(a.out).as_posix()]=dict(bytes=target.stat().st_size,sha256=sha(target),source=str(source))
    candidate=ROOT/'a_candidate'
    delivery=json.loads((candidate/'DELIVERY.json').read_text())
    assert delivery['bundle_id']=='5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710'
    for item in delivery['files']:
        path=candidate/item['path']
        assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
    save(a.out/'handoff_identity.json',dict(zip_sha256=sha(Path('C:/Users/wzh16/Downloads/GridDehazeNet_A_for_wzh_20261024.zip')),
        verified_payload_files=len(delivery['files']),delivery_sha256=sha(candidate/'DELIVERY.json'),bundle_id=delivery['bundle_id'],
        task_branch='feat/software',task_commit='a8d1d9a0b2ceb34ff5c7c77100eb3626e0505e35',
        baseline_commit='e8662ce5bd177f4014da469ab9885eca06e396f3',
        archive_zip_extracted=False,fog_rain_recalibration=False))
    rtl=ROOT/'work/hls02/component/hls/syn/verilog/griddehaze_conv_tile_top.v'
    text=rtl.read_text(encoding='utf-8')
    widths={key:int(re.search(r'parameter\s+'+key+r'\s*=\s*(\d+)\s*;',text).group(1))
        for key in ('C_S_AXI_CONTROL_DATA_WIDTH','C_S_AXI_CONTROL_ADDR_WIDTH',
                    'C_M_AXI_READ_MEM_ADDR_WIDTH','C_M_AXI_READ_MEM_DATA_WIDTH',
                    'C_M_AXI_WRITE_MEM_ADDR_WIDTH','C_M_AXI_WRITE_MEM_DATA_WIDTH')}
    save(a.out/'generated_interface.json',dict(source=str(rtl),sha256=sha(rtl),widths=widths,
        ps_hp_mapping_established=False,whole_image_abi_implemented=False,
        note='Actual generated RTL parameters; requested max widening 128 is not actual master width.'))
    if a.with_elementwise:
        rtl=ROOT/'work/elementwise_hls02/component/hls/syn/verilog/griddehaze_elementwise_top.v'
        text=rtl.read_text(encoding='utf-8')
        widths={key:int(re.search(r'parameter\s+'+key+r'\s*=\s*(\d+)\s*;',text).group(1))
            for key in ('C_S_AXI_CONTROL_DATA_WIDTH','C_S_AXI_CONTROL_ADDR_WIDTH',
                        'C_M_AXI_READ_MEM_ADDR_WIDTH','C_M_AXI_READ_MEM_DATA_WIDTH',
                        'C_M_AXI_WRITE_MEM_ADDR_WIDTH','C_M_AXI_WRITE_MEM_DATA_WIDTH')}
        save(a.out/'generated_elementwise_interface.json',dict(source=str(rtl),sha256=sha(rtl),widths=widths,
            ps_hp_mapping_established=False,whole_image_abi_implemented=False,
            note='Internal elementwise operator; no system DDR window or reset/drain guarantee yet.'))
    # Obtain source and tool identities for this review; outputs remain immutable.
    source_sha={f.relative_to(ROOT).as_posix():sha(f) for folder in ('src','tools','hls') for f in (ROOT/folder).rglob('*') if f.is_file() and f.suffix in ('.py','.cpp','.hpp')}
    doc_sha={f.relative_to(ROOT).as_posix():sha(f) for f in [ROOT/'README.md',*(ROOT/'docs').glob('*.md')]}
    save(a.out/'review_manifest.json',dict(files=records,current_source_sha256=source_sha,current_document_sha256=doc_sha,
        notes=['Per-run executed_sources and summary identify the source actually executed.',
               'Full-image tests predate tile backend additions; their recorded source hashes remain authoritative.',
               'A source package unchanged; raw files and generated tools outputs kept locally under ignored directories.']))
    print('REVIEW_COLLECT_PASS files='+str(len(records)))


if __name__=='__main__': main()
