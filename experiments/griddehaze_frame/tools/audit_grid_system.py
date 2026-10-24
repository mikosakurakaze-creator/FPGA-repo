"""Check actual BD preservation and additive address/DDR wiring, not a board test."""
import argparse
import json
from pathlib import Path
from preflight import sha,save

p=argparse.ArgumentParser(__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
manifest=json.loads((a.build/'build.json').read_text(encoding='utf-8'))
source=Path(manifest['seed_source'])
new=a.build/'project/weather_system.srcs/sources_1/bd/system/system.bd'
seed=json.loads(source.read_text(encoding='utf-8'))['design']
actual=json.loads(new.read_text(encoding='utf-8'))['design']
def require(condition,message):
    if not condition:raise RuntimeError(message)
require(sha(source)==manifest['seed_sha256'],'seed changed')
require(actual['components']['zynq_ultra_ps_e_0']['parameters']==seed['components']['zynq_ultra_ps_e_0']['parameters'],'PS configuration changed')
legacy=['zero_dce_cnn_top_0','bilinear_fixed16_buffered_0','curve_image_fixed16_0','weather_frame_top_0']
for name in legacy:
    for key in ['vlnv','parameters','addressing']:
        require(actual['components'][name].get(key)==seed['components'][name].get(key),'Legacy core changed '+name+'/'+key)
for kind,field in [('interface_nets','interface_ports'),('nets','ports')]:
    for name,net in seed[kind].items():
        require(name in actual[kind] and set(net[field])<=set(actual[kind][name][field]),'legacy net changed '+name)
for component,row in seed['addressing'].items():
    for space,entry in row['address_spaces'].items():
        for name,segment in entry.get('segments',{}).items():
            require(actual['addressing'][component]['address_spaces'][space]['segments'][name]==segment,'legacy address changed '+name)
def linked(*endpoints):
    return any(set(endpoints)<=set(n['interface_ports']) for n in actual['interface_nets'].values())
require(linked('axi_control/M04_AXI','griddehaze_frame_top_0/s_axi_control'),'new control disconnected')
require(linked('curve_ddr_sc/S04_AXI','griddehaze_frame_top_0/m_axi_feature_mem'),'feature disconnected')
require(linked('cnn_data_sc/S04_AXI','griddehaze_frame_top_0/m_axi_parameter_mem'),'parameters disconnected')
require(linked('curve_ddr_sc/M00_AXI','zynq_ultra_ps_e_0/S_AXI_HP3_FPD'),'HP3 disconnected')
require(linked('cnn_data_sc/M00_AXI','zynq_ultra_ps_e_0/S_AXI_HP0_FPD'),'HP0 disconnected')
seg=actual['addressing']['/zynq_ultra_ps_e_0']['address_spaces']['Data']['segments']['SEG_griddehaze_frame_top_0_Reg']
require(int(seg['offset'],16)==0xa0040000 and seg['range']=='64K','new control range')
ddr={}
for bundle,hp in [('feature_mem',3),('parameter_mem',0)]:
    segments=actual['addressing']['/griddehaze_frame_top_0']['address_spaces']['Data_m_axi_'+bundle]['segments']
    require(len(segments)==1,'unexpected new master window')
    entry=next(iter(segments.values()))
    require(entry['address_block']==f'/zynq_ultra_ps_e_0/SAXIGP{hp+2}/HP{hp}_DDR_LOW' and int(entry['offset'],16)==0 and entry['range']=='2G','DDR window mismatch')
    ddr[bundle]=entry
report=dict(pass_result=True,kind='actual_bd_structural_audit',seed_sha256=sha(source),new_bd_sha256=sha(new),
            legacy_cores_preserved=legacy,all_ps_parameters_preserved=True,all_legacy_nets_and_addresses_preserved=True,
            new_control_base='0xA0040000',new_control_range='64K',new_ddr_windows=ddr,
            configured_clock_mhz=actual['components']['zynq_ultra_ps_e_0']['parameters']['PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ']['value'],
            ps_hp_widths={f'HP{hp}':actual['components']['zynq_ultra_ps_e_0']['parameters'][f'PSU__SAXIGP{hp+2}__DATA_WIDTH']['value'] for hp in [0,3]},
            limitations=['Structural BD and configured PS values; not PS register readback, RTL arithmetic, timing or board validation.',
                         'Shared reset remains; no independent abort/drain recovery.'])
save(a.out,report)
print(json.dumps(report,indent=2))
