"""Audit the actual generated BD/IP/optional XSA against the integration contract."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--xsa',type=Path)
a=p.parse_args(); build=a.build.resolve(); checks={}
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def check(name,value):
    checks[name]=bool(value)

seed=json.loads((build/'system_seed.bd').read_text())['design']
path=build/'project/weather_system.srcs/sources_1/bd/system/system.bd'
bd=json.loads(path.read_text())['design']
check('ps_configuration_unchanged',seed['components']['zynq_ultra_ps_e_0']['parameters']==bd['components']['zynq_ultra_ps_e_0']['parameters'])
old=seed['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']
new=bd['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']
for key,value in old.items():
    check('old_csr_'+key,new.get(key,{}).get('offset')==value['offset'] and new.get(key,{}).get('range')==value['range'])
weather=next(v for v in new.values() if 'weather_frame_top_0' in v['address_block'])
check('weather_csr_A0030000_64K',int(weather['offset'],16)==0xA0030000 and weather['range']=='64K')
nets=[set(v['interface_ports']) for v in bd['interface_nets'].values()]
for name,ports in {
    'control':['axi_control/M03_AXI','weather_frame_top_0/s_axi_CTRL'],
    'input_to_hp0':['weather_frame_top_0/m_axi_gmem_in','cnn_data_sc/S03_AXI'],
    'output_to_hp3':['weather_frame_top_0/m_axi_gmem_out','curve_ddr_sc/S03_AXI']}.items():
    check(name,any(set(ports)<=s for s in nets))
signalnets=[set(v['ports']) for v in bd['nets'].values()]
check('weather_clock_ps_plclk0',any({'zynq_ultra_ps_e_0/pl_clk0','weather_frame_top_0/ap_clk'}<=s for s in signalnets))
check('weather_reset_synchronized',any({'rst_ps_100m/peripheral_aresetn','weather_frame_top_0/ap_rst_n'}<=s for s in signalnets))
spaces=bd['addressing']['/weather_frame_top_0']['address_spaces']
for name,space in spaces.items():
    active=[s for s in space['segments'].values() if s.get('is_excluded','FALSE')!='TRUE']
    check(name+'_only_low_ddr',len(active)==1 and int(active[0]['offset'],16)==0 and active[0]['range']=='2G')
ip=build/'ip/weather'
header=next(ip.rglob('xweather_frame_top_hw.h'))
registers=dict(re.findall(r'#define\s+XWEATHER_FRAME_TOP_CTRL_ADDR_(\w+)\s+(0x[0-9a-fA-F]+)',header.read_text()))
for name,offset in {'AP_CTRL':0,'AP_RETURN':0x10,'INPUT_R_DATA':0x18,'OUTPUT_R_DATA':0x24,
                    'HEIGHT_DATA':0x30,'WIDTH_DATA':0x38,'TASK_R_DATA':0x40}.items():
    check('csr_'+name,int(registers.get(name,'-1'),16)==offset)
rtl=(ip/'hdl/verilog/weather_frame_top.v').read_text()
for bundle in ('IN','OUT'):
    check('axi_'+bundle+'_data32',bool(re.search(r'C_M_AXI_GMEM_'+bundle+r'_DATA_WIDTH\s*=\s*32',rtl)))
    check('axi_'+bundle+'_address64',bool(re.search(r'C_M_AXI_GMEM_'+bundle+r'_ADDR_WIDTH\s*=\s*64',rtl)))
# HLS advertises 2-bit LOCK, SmartConnect uses AXI4's 1-bit LOCK. The discarded
# bit is safe only while actual generated masters drive normal (00) accesses.
for bundle in ('in','out'):
    helper=(ip/('hdl/verilog/weather_frame_top_gmem_'+bundle+'_m_axi.v')).read_text()
    locks=re.findall(r'assign\s+[A-Za-z_]*LOCK\s*=\s*([^;]+);',helper)
    check('axi_'+bundle+'_normal_lock',bool(locks) and all(v.strip() in ("2'b00","2'b0","2'd0") for v in locks))
artifacts={'bd_sha256':sha(path),'weather_component_sha256':sha(ip/'component.xml'),
           'weather_driver_sha256':sha(header)}
if a.xsa:
    tops=list((build/'project/weather_system.gen/sources_1/bd/system/ipshared').glob('*/hdl/verilog/weather_frame_top.v'))
    # Vivado shares .v files under ipshared, but stages memory initialization
    # files under the individual generated IP. Both are actual synthesis inputs.
    generated=build/'project/weather_system.gen/sources_1/bd/system/ip/system_weather_frame_top_0_0'
    compiled={}
    if len(tops)==1:
        for f in (ip/'hdl/verilog').iterdir():
            if f.suffix not in ('.v','.dat'):continue
            selected=(generated/'hdl/verilog'/f.name) if f.suffix=='.dat' else (tops[0].parent/f.name)
            compiled[f.name]={'path':selected.relative_to(build).as_posix(),
                              'sha256':sha(selected) if selected.is_file() else None,
                              'matches':selected.is_file() and sha(selected)==sha(f)}
    check('compiled_weather_rtl_rom_exact',len(tops)==1 and all(
        item['matches'] for item in compiled.values()))
    artifacts['weather_compiled_sources']=compiled
    synth_log=build/'project/weather_system.runs/system_weather_frame_top_0_0_synth_1/runme.log'
    synth_text=synth_log.read_text(errors='replace')
    check('compiled_weather_rom_read_success',all(
        "$readmem data file './"+f.name+"' is read successfully" in synth_text
        for f in (ip/'hdl/verilog').glob('*.dat')))
    artifacts['weather_synth_log_sha256']=sha(synth_log)
    dcp=build/'project/weather_system.runs/system_weather_frame_top_0_0_synth_1/system_weather_frame_top_0_0.dcp'
    check('compiled_weather_checkpoint_present',dcp.is_file())
    if dcp.is_file():artifacts['weather_synth_checkpoint_sha256']=sha(dcp)
    with zipfile.ZipFile(a.xsa) as z:
        check('xsa_zip_crc',z.testzip() is None)
        bits=[n for n in z.namelist() if n.endswith('.bit')]
        check('xsa_single_bit',len(bits)==1)
        if bits:
            check('xsa_bit_equals_external',z.read(bits[0])==(build/'weather_system.bit').read_bytes())
        check('xsa_hwh_present',any(n.endswith('.hwh') for n in z.namelist()))
    artifacts.update({'xsa_sha256':sha(a.xsa),'bit_sha256':sha(build/'weather_system.bit')})
report={'pass':all(checks.values()),'checks':checks,'artifacts':artifacts,
        'scope':'offline generated design/ABI audit; no board execution'}
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['pass'] else 1)
