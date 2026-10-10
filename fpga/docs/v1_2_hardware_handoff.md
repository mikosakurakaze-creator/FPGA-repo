# V1.2 hardware handoff

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**V1_2_HW_HANDOFF_READY / WAIT_MASTER**。

| State | Result |
| --- | --- |
| CNN_RTL_30FPS | PASS |
| SHORT_MULTI_FRAME_30FPS | PASS |
| IMPLEMENTABLE_CNN_IP | PASS |
| POST_ROUTE_100MHZ | PASS |
| BITSTREAM_XSA | PASS |
| BOARD_30FPS | NOT_TESTED |


## Artifacts and fixed project

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| bitstream | [system_wrapper.bit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.runs/impl_1/system_wrapper.bit) | 7,797,826 | `8a6c315b50799fb22cb8bfb6f376e3e6992ac41da0abe9c87a8ffc9ced85c915` |
| XSA | [kv260_three_module_v1_2_writecredit.xsa](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/kv260_three_module_v1_2_writecredit.xsa) | 3,068,574 | `09661c4822f05b8c54b000d2fc13893fac3356a970acb4c70a8ca89fb2693ead` |


Bitstream生成时间：`2026-10-03T13:40:28.338031+08:00`；XSA导出时间：`2026-10-03T13:52:48.034775+08:00`。XSA使用 `write_hw_platform -fixed -include_bit` 自然成功；内部 `kv260_three_module_v1_2_writecredit.bit` 与外部 .bit 大小和SHA-256完全相同。所有ZIP成员CRC通过，HWH和driver实际内容均已审计。

Vivado **2025.2**；device **xck26-sfvc784-2LV-c**；board `xilinx.com:kv260_som:part0:1.4`。固定工程：[v12_wc.xpr](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.xpr)；top=`system_wrapper`。沿用Phase5 `impl_1` routed DCP；未重跑implementation。

100MHz / 10.000ns：PS `pl_clk0` 驱动三个accelerator、五个SmartConnect、PS HPM0及HP0–3；`rst_ps_100m` 接PS `pl_resetn0`，外部reset active-low，accelerator使用peripheral_aresetn，SmartConnect使用interconnect_aresetn。PS、clock/reset与所有BD/address配置受保护，未改。HWH导出频率字段为99,999,001Hz；BD nominal100MHz与routed10ns约束保持原样，metadata值如实记录，未进行板级时钟测量。

## Control and ABI

| IP | Control base | Range | Data path |
| --- | --- | --- | --- |
| Bilinear | 0xA0000000 | 64 KiB | HP2 |
| Curve | 0xA0010000 | 64 KiB | HP3 |
| Formal write-credit CNN | 0xA0020000 | 64 KiB | HP0 data/workspace；HP1 parameters |

三个IP共同CSR：AP_CTRL=0x00，GIE=0x04，IER=0x08，ISR=0x0C；ap_ctrl_hs握手。所有pointer均为64-bit DDR地址，拆成low/high两个32-bit word；driver setter先写low再写high。HWH把参数word标为write-only，正式driver/RTL有readback；调度只需要写入。

| CNN pointer | Low / high offset | Payload bytes | Layout |
| --- | --- | ---: | --- |
| INPUT_Q14 | 0x10 / 0x14 | 38,160 | [1, 3, 60, 106] Q14 |
| WEIGHTS_INT8 | 0x1C / 0x20 | 10,075 | packed OIHW in kZeroDceLayers[14] order |
| BIAS_INT32 | 0x28 / 0x2C | 1,944 | one per output channel in layer order; fraction follows frozen quantization protocol |
| WEIGHT_FRAC | 0x34 / 0x38 | 486 | one fractional-bit value per output channel in layer order |
| TANH_LUT_Q15 | 0x40 / 0x44 | 8,194 | Q8 indices -2048 through +2048 |
| A_LOW_Q14 | 0x4C / 0x50 | 38,160 | [1, 3, 60, 106] Q14 |
| WORKSPACE_INT16 | 0x58 / 0x5C | 2,442,240 | six ReLU skip tensors only; convolution working tiles are on chip |


Bilinear：parameters_lowres=0x10/0x14，parameters_fullres=0x1C/0x20；input_height=0x28（60），input_width=0x30（106）。Curve：input_r=0x10/0x14，parameter_r=0x1C/0x20，output_r=0x28/0x2C；count=0x34（2,747,520）。完整字段、width/access与证据在 [v1_2_hw_register_map.json](E:/github/-/fpga/docs/v1_2_hw_register_map.json)。

## Formal CNN release

VLNV=`xilinx.com:hls:zero_dce_cnn_top:1.0`；coreRevision=**2114810448**；正式package=[component.xml](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/component.xml)。Release identity SHA-256=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`；component SHA-256=`7e046bd557997e8a8b55b466ee9a76b8c3c321f1435df2879a8bf92a45f54ecd`；source manifest SHA-256=`8bb4fc1ee4786b4e89f4ff37b867b529dcfd97ff10970ac405ffecafe4cead3c`；canonical ABI SHA-256=`95077dfd344f411d4bbf8004acee92e369f2e2bf46ae942ba391b41e6ff71598`。

正式CNN driver [xzero_dce_cnn_top_hw.h](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/drivers/zero_dce_cnn_top_v1_0/src/xzero_dce_cnn_top_hw.h) SHA-256=`3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362`，与project生成driver及XSA内driver完全相同。Bilinear/Curve headers也逐字匹配原正式package。三颗write-credit writer保持在实际routed hierarchy中，源payload、BD和routed DCP保持原hash；未回退旧CNN。见 [routed_writecredit_hierarchy.tsv](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/reports/routed_writecredit_hierarchy.tsv)。

六m_axi：gmem_input/output/workspace经cnn_data_sc→HP0；gmem8/gmem32/gmem_lut经cnn_model_sc→HP1。gmem8承载weights/weight_frac，gmem32承载bias，gmem_lut承载LUT。Bilinear两个masters经bilinear_ddr_sc→HP2；Curve三个masters经curve_ddr_sc→HP3。控制PS HPM0→axi_control，M00=CNN、M01=Bilinear、M02=Curve。

## DDR and fixed-point handoff

所有image tensor：RGB NCHW planar、C-contiguous、little-endian signed INT16 Q14；无row padding；byte offset=`2*((c*H+y)*W+x)`。CNN input与A_low各[1,3,60,106]、19,080 elements、38,160 bytes；A_full/model_input/enhanced各[1,3,720,1272]、2,747,520 elements、5,495,040 bytes。CNN下采样输入由外部准备；A_low→Bilinear→A_full→Curve保留原Fixed16 raw协议。

Workspace=**2,442,240 bytes / 1,221,120 INT16**，仅6个[32,60,106] ReLU skip tensors。每slot=407,040 bytes；byte offsets=0、407040、814080、1221120、1628160、2035200；fractional bits=[14,14,14,12,13,14]，不能把整个workspace标成Q14。卷积工作tile/model array在片上。

weights/bias/frac/LUT大小及当前payload SHA-256见机器可读map。参数按冻结14-layer表排列，weights为OIHW；bias与frac各486项；LUT为4097项Q15、Q8索引-2048至+2048。

现有RTL验证使用16-byte base alignment、单workspace和双image/intermediate slots；各slot生命周期及consumer完成后释放规则在map中。[buffer_map.json](E:/HLS/kv260_three_module_v1_2_phase4/buffer_map.json) 的物理地址、guard与35,621,632-byte分配仅属于BFM，未赋予板端物理分配。真实DDR/cache处理留待KV260到手后的独立批次。

数值协议引用：[v1_fixed_point_protocol.md](E:/github/-/fpga/docs/v1_fixed_point_protocol.md)、[v1_fixed_point_protocol.json](E:/github/-/fpga/docs/v1_fixed_point_protocol.json)。**仅沿用其数值算术；其中旧单m_axi topology与4,070,400-byte workspace描述由本交付的六m_axi与六skip layout取代。** 原协议文件未修改。冻结r4 sources及协议文件hash在map中。

## Evidence and boundary

| Routed metric | Phase5 | Post-bitstream |
| --- | --- | --- |
| Setup WNS / TNS | +0.636 / 0.000 ns | +0.636 / 0.000 ns |
| Hold WHS / THS | +0.010 / 0.000 ns | +0.010 / 0.000 ns |
| Pulse WPWS / TPWS | +3.500 / 0.000 ns | +3.500 / 0.000 ns |
| Failing setup / hold / pulse endpoints | 0 / 0 / 0 | 0 / 0 / 0 |
| DRC Error / Critical Warning / Warning | 0 / 0 / 198 | 0 / 0 / 198 |


Bitstream后的完整timing字段与Phase5相同，所有DRC类别/计数相同；197条details精确相同，RTSTAT-10的first15/20截断预览选择不同，完整20个对象集合未单独比较，差异如实归档；routing complete，78,288/78,288 fully routed、unrouted/partially routed/routing errors=0。原routed DCP SHA-256=`d2cf0ba7105da8cd1c51b0def1a64985232fbfea0c6b5119f817a9f8acd8e78d`；大小40,519,754 bytes。Phase5证据：[vivado_three_module_v1_2_implementation.md](E:/github/-/fpga/reports/vivado_three_module_v1_2_implementation.md)、[implementation_gate.json](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/implementation_gate.json)。

Phase4F权威RTL证据：8帧、100MHz、44,112,960项完整raw比较，mismatch/guard/hazard=0；steady output max interval=3,307,317 cycles（约30.236 FPS）。[v1_2_phase4f_short_multiframe.md](E:/github/-/fpga/reports/v1_2_phase4f_short_multiframe.md)、[analysis.json](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/analysis.json)。Phase4F使用已验证overlay，后续Phase4G将相同三颗writer字节固化为正式IP；不声称Phase4F当时已使用revision2114810448。本批未重新运行system TB。

**BOARD_30FPS=NOT_TESTED**。仅交付硬件artifact与元数据，不代表真实KV260/DDR/FPS验证。

NEXT STEP — **WAIT MASTER**。本批结束。真实KV260到手且另行授权后才做PS软件、real DDR/cache、实际100+帧runtime、真实FPS与final image；当前没有板测、PS软件开发或Git add/commit/push。
