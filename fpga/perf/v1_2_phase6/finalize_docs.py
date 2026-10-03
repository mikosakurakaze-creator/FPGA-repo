"""Write only Phase6 report/map/handoff/checkpoint after artifact gates pass."""
import sys
sys.dont_write_bytecode=True
import copy,json
from pathlib import Path
OUT=Path(__file__).resolve().parent
REPO=Path('E:/github/-')
BASE=Path('E:/HLS/kv260_three_module_v1_2_phase4')
sys.path.insert(0,str(OUT))
from prepare import sha,save,stamp,git
bitgate=json.loads((OUT/'bitstream_gate.json').read_text(encoding='utf-8'))
xsagate=json.loads((OUT/'xsa_gate.json').read_text(encoding='utf-8'))
assert bitgate['status']=='BITSTREAM_PASS' and xsagate['status']=='XSA_PASS'
assert json.loads((OUT/'protection_after.json').read_text(encoding='utf-8'))['status']=='PASS'
bit=bitgate['bitstream']; xsa=xsagate['xsa']
assert sha(bit['path'])==bit['sha256'] and sha(xsa['path'])==xsa['sha256']
formal=BASE/'phase4g/ip_primary_05'
manifest=json.loads((formal/'build_manifest.json').read_text(encoding='utf-8'))
old=json.loads((REPO/'fpga/docs/v1_1_hw_register_map.json').read_text(encoding='utf-8'))
state={k:'PASS' for k in ('CNN_RTL_30FPS','SHORT_MULTI_FRAME_30FPS','IMPLEMENTABLE_CNN_IP','POST_ROUTE_100MHZ','BITSTREAM_XSA')}
state['BOARD_30FPS']='NOT_TESTED'
def rec(p):
    p=Path(p);return dict(path=p.as_posix(),bytes=p.stat().st_size,sha256=sha(p))
drivers={k:rec(next(p.glob('drivers/*/src/*hw.h'))) for k,p in {
 'cnn':formal,'bilinear':BASE/'phase4g/integration_01/stable_ip_repo/bilinear','curve':BASE/'phase4g/integration_01/stable_ip_repo/curve'}.items()}
buffers={
 'INPUT_Q14':dict(elements=19080,bytes=38160,dtype='signed int16',fractional_bits=14,shape=[1,3,60,106],axi='gmem_input',access='read'),
 'WEIGHTS_INT8':dict(elements=10075,bytes=10075,dtype='signed int8',layout='packed OIHW in kZeroDceLayers[14] order',axi='gmem8',access='read',payload=rec(BASE/'data/weights_int8.bin')),
 'BIAS_INT32':dict(elements=486,bytes=1944,dtype='signed int32',layout='one per output channel in layer order; fraction follows frozen quantization protocol',axi='gmem32',access='read',payload=rec(BASE/'data/bias_int32.bin')),
 'WEIGHT_FRAC':dict(elements=486,bytes=486,dtype='signed int8',layout='one fractional-bit value per output channel in layer order',axi='gmem8',access='read',payload=rec(BASE/'data/weight_frac.bin')),
 'TANH_LUT_Q15':dict(elements=4097,bytes=8194,dtype='signed int16',fractional_bits=15,layout='Q8 indices -2048 through +2048',axi='gmem_lut',access='read',payload=rec(BASE/'data/tanh_lut_q15.bin')),
 'A_LOW_Q14':dict(elements=19080,bytes=38160,dtype='signed int16',fractional_bits=14,shape=[1,3,60,106],axi='gmem_output',access='write'),
 'WORKSPACE_INT16':dict(elements=1221120,bytes=2442240,dtype='signed int16',layout='six ReLU skip tensors only; convolution working tiles are on chip',shape=[6,32,60,106],slot_elements=203520,slot_bytes=407040,slot_byte_offsets=[0,407040,814080,1221120,1628160,2035200],slot_fractional_bits=[14,14,14,12,13,14],axi='gmem_workspace',access='read-write')}
for key in ('A_FULL_Q14','MODEL_INPUT_Q14','ENHANCED_Q14'):
    buffers[key]=dict(elements=2747520,bytes=5495040,dtype='signed int16',fractional_bits=14,shape=[1,3,720,1272])
ips=copy.deepcopy(old['ips'])
for k,ip in ips.items():
    ip['driver_header']=drivers[k]
    ip['xsa_driver_header_sha256']=xsagate['driver_headers'][k]['sha256']
    assert ip['xsa_driver_header_sha256']==drivers[k]['sha256']
ips['cnn'].update(core_revision=2114810448,formal_package=formal.as_posix(),release_identity_sha256=manifest['identity_sha256'],axi_masters=['gmem_input','gmem_output','gmem_workspace','gmem8','gmem32','gmem_lut'])
ips['bilinear']['scalar_registers']['input_height']['handoff_value']=60
ips['bilinear']['scalar_registers']['input_width']['handoff_value']=106
ips['curve']['scalar_registers']['count']['handoff_value']=2747520
protocol=[rec(REPO/'fpga/docs/v1_fixed_point_protocol.md'),rec(REPO/'fpga/docs/v1_fixed_point_protocol.json')]
frozen=[rec(REPO/'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4/zero_dce_cnn_top.h'),rec(REPO/'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4/zero_dce_cnn_top.cpp')]
release=dict(revision=2114810448,vlnv=ips['cnn']['vlnv'],identity_sha256=manifest['identity_sha256'],component=rec(formal/'component.xml'),source_manifest=rec(formal/'source_manifest.json'),build_manifest=rec(formal/'build_manifest.json'),abi_canonical_sha256='95077dfd344f411d4bbf8004acee92e369f2e2bf46ae942ba391b41e6ff71598',frozen_sources=frozen)
mapping={
 'control':'PS M_AXI_HPM0_FPD -> axi_control; M00=CNN, M01=Bilinear, M02=Curve',
 'HP0':{'smartconnect':'cnn_data_sc','masters':['CNN/gmem_input','CNN/gmem_output','CNN/gmem_workspace']},
 'HP1':{'smartconnect':'cnn_model_sc','masters':['CNN/gmem8','CNN/gmem32','CNN/gmem_lut']},
 'HP2':{'smartconnect':'bilinear_ddr_sc','masters':['Bilinear/gmem_input','Bilinear/gmem_output']},
 'HP3':{'smartconnect':'curve_ddr_sc','masters':['Curve/gmem_input','Curve/gmem_parameter','Curve/gmem_output']}}
phase4f=dict(report=rec(REPO/'fpga/reports/v1_2_phase4f_short_multiframe.md'),analysis=rec(BASE/'phase4f_system_02/analysis.json'),frames=8,clock_MHz=100,max_steady_output_interval_cycles=3307317,raw_comparisons=44112960,raw_mismatch=0,guard=0,hazard=0,scope='RTL system with verified Phase4E scheduling overlay; later Phase4G packages the identical three writer bytes; no claim Phase4F used packaged revision 2114810448')
phase5=dict(report=rec(REPO/'fpga/reports/vivado_three_module_v1_2_implementation.md'),gate=rec(BASE/'phase5/implementation_01/implementation_gate.json'),routed_dcp=rec(BASE/'phase4g/integration_01/project/v12_wc.runs/impl_1/system_wrapper_routed.dcp'),timing=bitgate['timing'])
data=dict(schema_version=1,status='V1_2_HW_HANDOFF_READY',generated_at=stamp(),state=state,board='xilinx.com:kv260_som:part0:1.4',part='xck26-sfvc784-2LV-c',vivado_version='2025.2',project=(BASE/'phase4g/integration_01/project/v12_wc.xpr').as_posix(),clock=dict(name='clk_pl_0',source='PS/pl_clk0',nominal_frequency_hz=100000000,period_ns=10.0,hwh_frequency_hz=xsagate['hwh_clock_frequency_hz'],note='Nominal BD configuration/post-route constraint is 100MHz; protected HWH reports 99999001 Hz. No board clock measurement performed.'),reset=dict(instance='rst_ps_100m',source='PS/pl_resetn0',external_active_high=False,accelerators='peripheral_aresetn',smartconnects='interconnect_aresetn'),artifacts=dict(bitstream=bit,xsa=xsa,embedded_bitstream=xsagate['embedded_bitstream']),cnn_release=release,
 argument_register_access_note=old['argument_register_access_note'],ap_ctrl_hs=old['ap_ctrl_hs'],interrupt_register_bits=old['interrupt_register_bits'],ips=ips,ddr_connectivity=mapping,
 ddr=dict(byte_order='little_endian',image_tensor_order='RGB NCHW, C-contiguous planar',image_byte_offset='2*((c*H+y)*W+x)',row_padding_bytes=0,base_alignment_bytes_from_rtl_validation=16,board_physical_allocation='NOT_ASSIGNED; buffer_map.json physical addresses are BFM-only',workspace_slots=1,image_and_intermediate_slots=2,buffers=buffers,simulation_map=rec(BASE/'buffer_map.json'),buffer_lifetimes={'cnn_input':'host prepare through CNN done','a_low':'CNN start through Bilinear done','a_full':'Bilinear start through Curve done','model_input':'host prepare through Curve done','enhanced':'Curve start through host check/release','workspace':'one serialized CNN start through done'}),
 fixed_point_protocol=dict(references=protocol,v1_2_override='Preserve numeric arithmetic. Original protocol single CNN m_axi topology and 4,070,400-byte workspace are superseded by current six m_axi and 2,442,240-byte six-skip layout here; workspace fractions vary by slot.'),evidence=dict(phase4f=phase4f,phase5=phase5,phase6_gate=(OUT/'handoff_gate.json').as_posix()),next_step='WAIT MASTER. Only after physical KV260 arrival and separate authorization: PS software, real DDR/cache handling, actual 100+ frames, real FPS and final image.')
path=REPO/'fpga/docs/v1_2_hw_register_map.json'
assert not path.exists(), 'Do not overwrite an existing authoritative register map'
path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def link(p,label=None): return '['+(label or Path(p).name)+']('+str(p).replace('\\','/')+')'
def artifact_table():
    return '| Artifact | Path | Bytes | SHA-256 |\n| --- | --- | ---: | --- |\n'+''.join(f"| {label} | {link(a['path'])} | {a['bytes']:,} | `{a['sha256']}` |\n" for label,a in [('bitstream',bit),('XSA',xsa)])
def pointer_table():
    rows='| CNN pointer | Low / high offset | Payload bytes | Layout |\n| --- | --- | ---: | --- |\n'
    for n,r in ips['cnn']['pointer_registers'].items():
        p=buffers[n.upper()]; layout=p.get('layout',str(p.get('shape',''))+' Q'+str(p.get('fractional_bits','')))
        rows+=f"| {n.upper()} | 0x{r['offset_low']:02X} / 0x{r['offset_high']:02X} | {p['bytes']:,} | {layout} |\n"
    return rows
def state_table(): return '| State | Result |\n| --- | --- |\n'+''.join(f'| {k} | {v} |\n' for k,v in state.items())
def timing_table(): return '| Routed metric | Phase5 | Post-bitstream |\n| --- | --- | --- |\n| Setup WNS / TNS | +0.636 / 0.000 ns | +0.636 / 0.000 ns |\n| Hold WHS / THS | +0.010 / 0.000 ns | +0.010 / 0.000 ns |\n| Pulse WPWS / TPWS | +3.500 / 0.000 ns | +3.500 / 0.000 ns |\n| Failing setup / hold / pulse endpoints | 0 / 0 / 0 | 0 / 0 / 0 |\n| DRC Error / Critical Warning / Warning | 0 / 0 / 198 | 0 / 0 / 198 |\n'

handoff=f'''# V1.2 hardware handoff

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**V1_2_HW_HANDOFF_READY / WAIT_MASTER**。

{state_table()}

## Artifacts and fixed project

{artifact_table()}

Bitstream生成时间：`{bit['generated_at']}`；XSA导出时间：`{xsa['generated_at']}`。XSA使用 `write_hw_platform -fixed -include_bit` 自然成功；内部 `{xsagate['embedded_bitstream']['entry']}` 与外部 .bit 大小和SHA-256完全相同。所有ZIP成员CRC通过，HWH和driver实际内容均已审计。

Vivado **2025.2**；device **xck26-sfvc784-2LV-c**；board `xilinx.com:kv260_som:part0:1.4`。固定工程：{link(data['project'])}；top=`system_wrapper`。沿用Phase5 `impl_1` routed DCP；未重跑implementation。

100MHz / 10.000ns：PS `pl_clk0` 驱动三个accelerator、五个SmartConnect、PS HPM0及HP0–3；`rst_ps_100m` 接PS `pl_resetn0`，外部reset active-low，accelerator使用peripheral_aresetn，SmartConnect使用interconnect_aresetn。PS、clock/reset与所有BD/address配置受保护，未改。HWH导出频率字段为99,999,001Hz；BD nominal100MHz与routed10ns约束保持原样，metadata值如实记录，未进行板级时钟测量。

## Control and ABI

| IP | Control base | Range | Data path |
| --- | --- | --- | --- |
| Bilinear | 0xA0000000 | 64 KiB | HP2 |
| Curve | 0xA0010000 | 64 KiB | HP3 |
| Formal write-credit CNN | 0xA0020000 | 64 KiB | HP0 data/workspace；HP1 parameters |

三个IP共同CSR：AP_CTRL=0x00，GIE=0x04，IER=0x08，ISR=0x0C；ap_ctrl_hs握手。所有pointer均为64-bit DDR地址，拆成low/high两个32-bit word；driver setter先写low再写high。HWH把参数word标为write-only，正式driver/RTL有readback；调度只需要写入。

{pointer_table()}

Bilinear：parameters_lowres=0x10/0x14，parameters_fullres=0x1C/0x20；input_height=0x28（60），input_width=0x30（106）。Curve：input_r=0x10/0x14，parameter_r=0x1C/0x20，output_r=0x28/0x2C；count=0x34（2,747,520）。完整字段、width/access与证据在 {link(path)}。

## Formal CNN release

VLNV=`xilinx.com:hls:zero_dce_cnn_top:1.0`；coreRevision=**2114810448**；正式package={link(formal/'component.xml')}。Release identity SHA-256=`{release['identity_sha256']}`；component SHA-256=`{release['component']['sha256']}`；source manifest SHA-256=`{release['source_manifest']['sha256']}`；canonical ABI SHA-256=`{release['abi_canonical_sha256']}`。

正式CNN driver {link(drivers['cnn']['path'])} SHA-256=`{drivers['cnn']['sha256']}`，与project生成driver及XSA内driver完全相同。Bilinear/Curve headers也逐字匹配原正式package。三颗write-credit writer保持在实际routed hierarchy中，源payload、BD和routed DCP保持原hash；未回退旧CNN。见 {link(OUT/'reports/routed_writecredit_hierarchy.tsv')}。

六m_axi：gmem_input/output/workspace经cnn_data_sc→HP0；gmem8/gmem32/gmem_lut经cnn_model_sc→HP1。gmem8承载weights/weight_frac，gmem32承载bias，gmem_lut承载LUT。Bilinear两个masters经bilinear_ddr_sc→HP2；Curve三个masters经curve_ddr_sc→HP3。控制PS HPM0→axi_control，M00=CNN、M01=Bilinear、M02=Curve。

## DDR and fixed-point handoff

所有image tensor：RGB NCHW planar、C-contiguous、little-endian signed INT16 Q14；无row padding；byte offset=`2*((c*H+y)*W+x)`。CNN input与A_low各[1,3,60,106]、19,080 elements、38,160 bytes；A_full/model_input/enhanced各[1,3,720,1272]、2,747,520 elements、5,495,040 bytes。CNN下采样输入由外部准备；A_low→Bilinear→A_full→Curve保留原Fixed16 raw协议。

Workspace=**2,442,240 bytes / 1,221,120 INT16**，仅6个[32,60,106] ReLU skip tensors。每slot=407,040 bytes；byte offsets=0、407040、814080、1221120、1628160、2035200；fractional bits=[14,14,14,12,13,14]，不能把整个workspace标成Q14。卷积工作tile/model array在片上。

weights/bias/frac/LUT大小及当前payload SHA-256见机器可读map。参数按冻结14-layer表排列，weights为OIHW；bias与frac各486项；LUT为4097项Q15、Q8索引-2048至+2048。

现有RTL验证使用16-byte base alignment、单workspace和双image/intermediate slots；各slot生命周期及consumer完成后释放规则在map中。{link(BASE/'buffer_map.json')} 的物理地址、guard与35,621,632-byte分配仅属于BFM，未赋予板端物理分配。真实DDR/cache处理留待KV260到手后的独立批次。

数值协议引用：{link(protocol[0]['path'])}、{link(protocol[1]['path'])}。**仅沿用其数值算术；其中旧单m_axi topology与4,070,400-byte workspace描述由本交付的六m_axi与六skip layout取代。** 原协议文件未修改。冻结r4 sources及协议文件hash在map中。

## Evidence and boundary

{timing_table()}

Bitstream后的完整timing字段与Phase5相同，所有DRC类别/计数相同；197条details精确相同，RTSTAT-10的first15/20截断预览选择不同，完整20个对象集合未单独比较，差异如实归档；routing complete，78,288/78,288 fully routed、unrouted/partially routed/routing errors=0。原routed DCP SHA-256=`{phase5['routed_dcp']['sha256']}`；大小40,519,754 bytes。Phase5证据：{link(phase5['report']['path'])}、{link(phase5['gate']['path'])}。

Phase4F权威RTL证据：8帧、100MHz、44,112,960项完整raw比较，mismatch/guard/hazard=0；steady output max interval=3,307,317 cycles（约30.236 FPS）。{link(phase4f['report']['path'])}、{link(phase4f['analysis']['path'])}。Phase4F使用已验证overlay，后续Phase4G将相同三颗writer字节固化为正式IP；不声称Phase4F当时已使用revision2114810448。本批未重新运行system TB。

**BOARD_30FPS=NOT_TESTED**。仅交付硬件artifact与元数据，不代表真实KV260/DDR/FPS验证。

NEXT STEP — **WAIT MASTER**。本批结束。真实KV260到手且另行授权后才做PS软件、real DDR/cache、实际100+帧runtime、真实FPS与final image；当前没有板测、PS软件开发或Git add/commit/push。
'''
(REPO/'fpga/docs/v1_2_hardware_handoff.md').write_text(handoff,encoding='utf-8')

report=f'''# KV260 三模块 V1.2 Phase 6：Bitstream、XSA 与 hardware handoff

日期：2026-10-03（Asia/Shanghai）。结论：**V1_2_HW_HANDOFF_READY**。仅从已通过Phase5 gate的正式routed工程继续write_bitstream，XSA含同一bitstream，artifact SHA/size、实际HWH/driver和交付文档完整。BOARD_30FPS=**NOT_TESTED**。

{state_table()}

## Fixed project and protection audit

工程：{link(data['project'])}；Vivado **2025.2**；device **xck26-sfvc784-2LV-c**；clock **100MHz / 10.000ns**。impl_1起始状态=`route_design Complete!`、100%、NEEDS_REFRESH=0；route checkpoint40,519,754 bytes、SHA-256=`{phase5['routed_dcp']['sha256']}`。正式CNN revision=2114810448；release identity=`{release['identity_sha256']}`。

开始前只读核对Phase5 gate绑定的全部证据SHA、15,762项受保护文件、完整正式/stable IP文件树、project source/gen树、XPR Configuration/FileSets、BD/address/PS/clock/reset、三writer routed primitive hierarchy，PASS。Phase5批准的11个旧generated synthesis index hash作为已审计基线；本批保留其launch前XML字节。初始byte-only审计因synth_1/gen_run.xml named BlockFileSet引用顺序变化报FAIL，原FAIL已归档；仅该引用集合排列改变，其他XML字节、源/综合/route证据不变，独立复核后窄范围语义审计PASS。最终保护核对见 {link(OUT/'protection_after.json')}，source drift=0；原route/opt/place/phys_opt阶段end marker的hash及mtime未改变，原routed/其他DCP hash未变。

CNN、Bilinear、Curve、PS、SmartConnect、clock/reset、address map与fixed-point protocol均未修改；未新建/切换分支，未继续性能优化、HLS、system TB、implementation或板测。

## Natural Generate Bitstream result

| Evidence | Actual result |
| --- | --- |
| Vivado batch process exit | 0；natural=True；forced_termination=False |
| Run status / progress | write_bitstream Complete! / 100% |
| Log success | Bitgen Completed Successfully；write_bitstream completed successfully |
| Natural markers | .write_bitstream.end.rst + .vivado.end.rst；无error marker |
| write_bitstream run counters | 75 Info / 0 Warning / 0 Critical Warning / 0 Error |
| write_bitstream elapsed | 65秒 |
| Generation timestamp | {bit['generated_at']} |
| Batch start / end | {bitgate['natural_exit']['started_at']} / {bitgate['natural_exit']['ended_at']} |
| Implementation rerun | False；run Tcl只open routed DCP并write_bitstream |

{artifact_table()}

成功由run status、自然end markers、success log和exit共同证明，不只依赖.bit文件存在。Vivado向原runme.log追加日志；Phase5原字节前缀与备份完全一致，仅新增bitstream段用于本批run审计。实际脚本/launcher、完整console/Vivado/impl logs以及route前日志备份留在 {link(OUT,'Phase6 evidence directory')}。{link(OUT/'bitstream_gate.json')}。

批处理preflight有普通Warning：未安装的其他board catalog条目，以及get_files -all中部分对象不适用USED_IN_*属性的报告提示。该TSV中的这些属性为空，不用于证明source membership；源保护由实际全文件树/既有gate与正式CNN catalog/BD身份审计完成。未隐藏或改计日志级别；batch与run均无新Error/Critical Warning，实际各log Warning计数见bitstream_gate。实际write_bitstream run为0 Warning。

## Post-bitstream timing / DRC

{timing_table()}

与Phase5 routed timing所有12个summary字段、clock和tool clean状态完全一致；DRC rules/计数相同，仍198条普通Warning；197条details精确相同，RTSTAT-10的first15/20截断预览选择不同，完整20个对象集合未单独比较；未变DCP与差异记录见drc_detail_comparison.json。最终routing=78,288/78,288 complete，unrouted/partially routed/routing errors=0。详见 {link(OUT/'reports/postbit_timing_summary.rpt')}、{link(OUT/'reports/postbit_drc.rpt')}、{link(OUT/'reports/postbit_route_status.rpt')}。Phase5原timing/DRC证据hash未变。

## XSA export and content audit

`write_hw_platform -fixed -include_bit`自然成功，Vivado export exit=0；导出时间={xsa['generated_at']}。ZIP全成员CRC完整性PASS；唯一embedded bitstream `{xsagate['embedded_bitstream']['entry']}` 大小/SHA-256与外部.bit相同。XSA/HWH实际包含Zynq UltraScale+ PS、formal write-credit CNN、Bilinear、Curve、五个SmartConnect、reset、clock、三段control address map及bitstream；formalCNN hierarchy由同一未变routed DCP验证，CNN release revision2114810448在XSA实际HWH COREREVISION中确认，并与正式package/同源BD/XCI一致。XSA内三个driver header与对应正式packaged IP逐字相同。{link(OUT/'xsa_gate.json')}。

| Control map | Base | Range |
| --- | --- | --- |
| Bilinear | 0xA0000000 | 64KiB |
| Curve | 0xA0010000 | 64KiB |
| CNN | 0xA0020000 | 64KiB |

{pointer_table()}

CNN driver SHA-256=`{drivers['cnn']['sha256']}`，canonical ABI=`{release['abi_canonical_sha256']}`。七pointer的low/high、三模块全部CSR/参数offset均与XSA实际HWH及正式headers核对；完整width/access、DDR payload/layout、当前六m_axi→HP0/1与Bilinear HP2/Curve HP3、协议引用及release/source/parameter hashes在 {link(path)} 与 {link(REPO/'fpga/docs/v1_2_hardware_handoff.md')}。

旧fixed-point协议数值规则保留；旧单m_axi与4,070,400-byte workspace描述已由新handoff明确替换为六m_axi、2,442,240-byte六skip tensors（frac=[14,14,14,12,13,14]）。未修改原协议文件，未把BFM地址写成板端分配。

## Historical RTL and physical evidence

Phase4F原system RTL证据：8 frames、100MHz、44,112,960 full raw comparisons，raw mismatch/guard/hazard=0；steady max interval=3,307,317 cycles、约30.236 FPS。原报告/analysis保护hash未变，未重跑。Phase4F先验证overlay，Phase4G后将相同三writer固化；本批不混淆这两段来源。{link(phase4f['report']['path'])}。

Phase5 post-route evidence：{link(phase5['report']['path'])}；100MHz setup/hold/pulse与最终DRC如上。本批硬件交付不增加真实DDR、cache、板级runtime/FPS或final image证据。

## Changes, validation and Git review

| File | Reason / key difference |
| --- | --- |
| fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md | 正式Phase6自然完成、artifact identity、post-bit timing/DRC与XSA审计 |
| fpga/docs/v1_2_hw_register_map.json | 新V1.2机器可读ABI/地址/DDR/release与artifact hashes；替代旧map来源 |
| fpga/docs/v1_2_hardware_handoff.md | 硬件交付说明、准确workspace/六AXI与板测边界 |
| fpga/reports/v1_2_phase4_checkpoint.md | 当前handoff ready与bit/XSA/hash/NEXT STEP，保留旧Phase4G/5历史 |

已执行：现场只读与全量SHA保护；从现有route自然write_bitstream；自然exit/status/markers/log核对；post-bit实际timing/DRC/route审计及Phase5精确对照；include-bit XSA导出；ZIP CRC/embedded SHA/HWH拓扑地址/CSR/driver ABI审计；机器可读map与文档一致性核验。最终独立审计见 {link(OUT/'handoff_gate.json')}。

未执行：RTL/IP/数学/互连/clock/reset/地址/协议修改，性能优化，新system TB，HLS或implementation重跑，板测，PS软件，real DDR/cache，100+ frame runtime，真实FPS/final image，git add/commit/push/PR，分支操作。外部artifact/log/DCP/backup留E:/HLS，不上传。

建议Commit Message：`docs(fpga): deliver V1.2 bitstream XSA and hardware handoff`。Branch=`{git('branch','--show-current')}`，HEAD=`{git('rev-parse','HEAD')}`；tracked/staged diff均为空；既有untracked保留，本批4份文档未暂存，详见 {link(OUT/'git_review.json')}。

NEXT STEP — **WAIT MASTER**。到hardware handoff结束立即停止。真实KV260到手且另行授权后才进行PS software、real DDR/cache、actual 100+ frames、real FPS和final image。**BOARD_30FPS=NOT_TESTED**。
'''
(REPO/'fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md').write_text(report,encoding='utf-8')

checkpoint=(OUT/'checkpoint_before.md').read_text(encoding='utf-8')
checkpoint=checkpoint.replace('# V1.2 Phase 5 Checkpoint','# V1.2 Phase 6 Checkpoint',1)
checkpoint=checkpoint.replace('CURRENT STATUS：**POST_ROUTE_100MHZ_PASS / WAIT_MASTER**。','CURRENT STATUS：**V1_2_HW_HANDOFF_READY / WAIT_MASTER**。',1)
checkpoint=checkpoint.replace('正式Phase4G工程完成implementation/route与post-route审计。','正式Phase4G工程现已完成Phase6 bitstream/XSA及hardware handoff。Phase5历史：正式工程完成implementation/route与post-route审计。',1)
checkpoint=checkpoint.replace('| BOARD_30FPS | NOT_TESTED |','| BITSTREAM_XSA | PASS |\n| BOARD_30FPS | NOT_TESTED |',1)
phase6=f'''## Phase6当前结果

**V1_2_HW_HANDOFF_READY**：bitstream PASS、XSA PASS、embedded bitstream与外部bit SHA/size一致、hashes完整、交付文档完整。{link(REPO/'fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md','完整Phase6报告')}；{link(REPO/'fpga/docs/v1_2_hardware_handoff.md','硬件handoff')}；{link(path,'机器可读register/DDR map')}。

{artifact_table()}

Vivado2025.2，device xck26-sfvc784-2LV-c，100MHz/10ns；正式CNN revision2114810448，release identity=`{release['identity_sha256']}`。write_bitstream Complete!/100%，自然exit0/end marker，生成时间{bit['generated_at']}；XSA自然exit0/include_bit，导出时间{xsa['generated_at']}。

Post-bit setup/hold/pulse=+0.636/+0.010/+3.500ns，TNS/THS/TPWS=0、失败端点0，与Phase5 routed完整summary相同。DRC Error0/Critical0/Warning198，类别/计数相同；197条details相同、RTSTAT-10截断预览选择不同且已记录。15,762项保护与完整IP/source树PASS，routed DCP SHA=`{phase5['routed_dcp']['sha256']}`未变，implementation未重跑。

控制Bilinear/Curve/CNN=0xA0000000/0xA0010000/0xA0020000；七64-bit pointer offsets=0x10/0x1C/0x28/0x34/0x40/0x4C/0x58；driver/XSA ABI与正式package相同。DDR workspace=2,442,240B、六skip tensors，当前六m_axi topology明确；数值协议文件保持原hash。BOARD_30FPS仍**NOT_TESTED**。

未运行新system TB、性能优化、RTL/IP修改、板测、PS软件或Git写操作。Phase4F 8-frame RTL与Phase5 routed证据原hash保持，下面Phase4G/5段落仅是历史；其中“本批/未生成/下一批”不覆盖当前Phase6状态。

'''
checkpoint=checkpoint.replace('## Phase5当前结果',phase6+'## Phase5历史结果',1)
start=checkpoint.index('## 当前NEXT STEP与Git review')
checkpoint=checkpoint[:start]+f'''## 当前NEXT STEP与Git review

NEXT STEP — **WAIT MASTER**：本批到hardware handoff立即停止。真实KV260到手且另行授权后才做PS software、real DDR、cache handling、actual 100+ frame runtime、real FPS与final image。BOARD_30FPS=NOT_TESTED。当前不自动板测或PS软件开发。

Branch=`{git('branch','--show-current')}`，HEAD=`{git('rev-parse','HEAD')}`；tracked diff=empty，staged diff=empty；既有untracked保留，本批4份handoff/checkpoint文档未暂存。文件变化、原因、差异、执行/未执行验证见完整Phase6报告。未执行git add/commit/push；建议Commit Message：`docs(fpga): deliver V1.2 bitstream XSA and hardware handoff`。
'''
(REPO/'fpga/reports/v1_2_phase4_checkpoint.md').write_text(checkpoint,encoding='utf-8')
save('git_review.json',{k:git(*a) for k,a in [('branch',('branch','--show-current')),('head',('rev-parse','HEAD')),('tracked_diff',('diff','--stat')),('staged_diff',('diff','--cached','--stat')),('status',('status','--short','--untracked-files=all'))]})
save('documents_written.json',dict(status='WRITTEN_PENDING_FINAL_AUDIT',generated_at=stamp(),files=[rec(REPO/p) for p in ['fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md','fpga/docs/v1_2_hw_register_map.json','fpga/docs/v1_2_hardware_handoff.md','fpga/reports/v1_2_phase4_checkpoint.md']]))
print('PHASE6_DOCUMENTS_WRITTEN=4',flush=True)
