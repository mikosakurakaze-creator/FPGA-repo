# V1.2 Phase 6 Checkpoint

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**V1_2_HW_HANDOFF_READY / WAIT_MASTER**。

正式Phase4G工程现已完成Phase6 bitstream/XSA及hardware handoff。Phase5历史：正式工程完成implementation/route与post-route审计。[完整Phase5报告](E:/github/-/fpga/reports/vivado_three_module_v1_2_implementation.md)；[独立implementation gate](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/implementation_gate.json)。

| 总状态 | 结果 |
| --- | --- |
| CNN_RTL_30FPS | PASS |
| SHORT_MULTI_FRAME_30FPS | PASS |
| IMPLEMENTABLE_CNN_IP | PASS |
| POST_ROUTE_100MHZ | PASS |
| BITSTREAM_XSA | PASS |
| BOARD_30FPS | NOT_TESTED |

## Phase6当前结果

**V1_2_HW_HANDOFF_READY**：bitstream PASS、XSA PASS、embedded bitstream与外部bit SHA/size一致、hashes完整、交付文档完整。[完整Phase6报告](E:/github/-/fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md)；[硬件handoff](E:/github/-/fpga/docs/v1_2_hardware_handoff.md)；[机器可读register/DDR map](E:/github/-/fpga/docs/v1_2_hw_register_map.json)。

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| bitstream | [system_wrapper.bit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.runs/impl_1/system_wrapper.bit) | 7,797,826 | `8a6c315b50799fb22cb8bfb6f376e3e6992ac41da0abe9c87a8ffc9ced85c915` |
| XSA | [kv260_three_module_v1_2_writecredit.xsa](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/kv260_three_module_v1_2_writecredit.xsa) | 3,068,574 | `09661c4822f05b8c54b000d2fc13893fac3356a970acb4c70a8ca89fb2693ead` |


Vivado2025.2，device xck26-sfvc784-2LV-c，100MHz/10ns；正式CNN revision2114810448，release identity=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`。write_bitstream Complete!/100%，自然exit0/end marker，生成时间2026-10-03T13:40:28.338031+08:00；XSA自然exit0/include_bit，导出时间2026-10-03T13:52:48.034775+08:00。

Post-bit setup/hold/pulse=+0.636/+0.010/+3.500ns，TNS/THS/TPWS=0、失败端点0，与Phase5 routed完整summary相同。DRC Error0/Critical0/Warning198，类别/计数相同；197条details相同、RTSTAT-10截断预览选择不同且已记录。15,762项保护与完整IP/source树PASS，routed DCP SHA=`d2cf0ba7105da8cd1c51b0def1a64985232fbfea0c6b5119f817a9f8acd8e78d`未变，implementation未重跑。

控制Bilinear/Curve/CNN=0xA0000000/0xA0010000/0xA0020000；七64-bit pointer offsets=0x10/0x1C/0x28/0x34/0x40/0x4C/0x58；driver/XSA ABI与正式package相同。DDR workspace=2,442,240B、六skip tensors，当前六m_axi topology明确；数值协议文件保持原hash。BOARD_30FPS仍**NOT_TESTED**。

未运行新system TB、性能优化、RTL/IP修改、板测、PS软件或Git写操作。Phase4F 8-frame RTL与Phase5 routed证据原hash保持，下面Phase4G/5段落仅是历史；其中“本批/未生成/下一批”不覆盖当前Phase6状态。

## Phase5历史结果

| 100 MHz post-route指标 | 实际值 | 失败 / 总端点 | Gate |
| --- | --- | --- | --- |
| Setup WNS / TNS (ns) | +0.636 / 0.000 | 0 / 170914 | PASS |
| Hold WHS / THS (ns) | +0.010 / 0.000 | 0 / 170914 | PASS |
| Pulse WPWS / TPWS (ns) | +3.500 / 0.000 | 0 / 54198 | PASS |

Routing：78288/78288 fully routed，unrouted=0，partially routed=0，routing errors=0。自然run=`route_design Complete!`，Vivado batch exit=0。

| Post-route资源 | 实际值 |
| --- | --- |
| LUT | 37864 |
| FF | 45326 |
| RAMB36 | 29 |
| RAMB18 | 72 |
| BRAM_tiles | 65.0 |
| URAM | 18 |
| DSP | 146 |

DRC：Error=0，Critical Warning=0，Warning=198；逐条类别/对象分析见完整报告。最差setup=CNN，最差hold=SmartConnect。

保护审计最终PASS：15,687项逐字未变，11个自动生成run索引变化经独立语义审计确认；初始byte-only FAIL与每项原/new SHA完整保留，详见Phase5报告。报告命令另有2条-nets弃用Critical Warning，路径数据完整且slack一致，与DRC 0 Critical分开记录。配置与正式IP完整文件树PASS。未修改RTL、CNN/Bilinear/Curve、PS/互连/地址/协议；未生成bitstream/XSA，未运行system TB、板测或Git写操作。BOARD_30FPS=NOT_TESTED，不自动标记HW_READY。

## Phase4G权威交付与历史保留

以下保留Phase4G交付时的正式identity、cycles、source/ABI与synthesis证据。其“本批/停止点”指Phase4G历史；当前状态和下一步以本checkpoint的Phase6段落为准。Phase4G原字节备份：[checkpoint_before.md](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/checkpoint_before.md)。

### 权威历史与本批结果

- Phase 4E isolated CNN：**3,301,639 cycles**；A_low 19,080/19,080 mismatch0、guard0、hazard0、responses drain PASS。
- Phase 4F 8-frame steady-state output max interval：**3,307,317 cycles**；**SHORT_MULTI_FRAME_30FPS_PASS**。原证据未改，本批没有重跑8帧。
- Phase 4G 正式 packaged IP CNN 单帧：ap_start=396、ap_done=3,302,035、**3,301,639 cycles**；完整raw/guard/hazard/IRQ、7blocks与4HP final drain PASS。
- Base r4/export、原 Phase4E overlay、Bilinear/Curve、DDR/fixed-point/V1.1/Phase4F 前后保护hash PASS。

### 正式交付

IP：`E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05`；[build_manifest](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/build_manifest.json)。Identity=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`。与 `E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_rebuild_06` 独立复建305项payload逐字相同。

仅三颗 writer/caller Verilog 的SHA改变，完全等于Phase4E verified overlay。VLNV/top、7pointer/6m_axi、CSR/register offsets、driver/接口ABI不变；coreRevision固定2114810448。Active VHDL入口移除，原VHDL仅归档；综合/仿真共用139V+2VH+9ROM=150项同path/hash。最终CNN06的头文件搜索也只指向正式包。

工程：[fresh V1.2 v12_wc.xpr](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.xpr)，基于原saved V1.2 BD创建；原XPR/runs及V1.1不变。正式catalog唯一解析、BD Validate、Generate Output Products、实际CNN及全系统synthesis、三writer primitive hierarchy全部PASS；cache disabled。

| Resource | CNN OOC | V1.2 system |
| --- | --- | --- |
| LUT | 20210 | 40993 |
| FF | 17498 | 47653 |
| BRAM tiles | 62.5 | 65.0 |
| URAM | 18 | 18 |
| DSP | 82 | 146 |

100MHz：CNN OOC setup estimate **+3.212ns**；system WNS/TNS **+2.613 / 0.000ns**，setup失败端点0。System pre-route WHS/THS **-0.093 / -1863.689ns**，hold失败端点58257。**Hold只是pre-route记录，不是最终结论**；OOC未指定HD.CLK_SRC，估计有相应限制。

### 证据与停止点

[release gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/release_gate.json)；[OOC](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/ooc_summary.json)；[writer local](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/writer_probe_05/writer_probe_gate.json)；[CNN06 single](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06/analysis.json)；[system synthesis gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/integration_gate.json)；[after protection](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/protection_after.json)；[Phase4F原checkpoint备份](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/checkpoint_before.md)。

CNN05记录至350,000 cycles后因旧include目录的来源审计中止，无DONE/数值完成，不用于gate；最终CNN06在搜索路径修正后完整自然完成。全部尝试证据保留，不把prepared/aborted/superseded结果当PASS。

## 当前NEXT STEP与Git review

NEXT STEP — **WAIT MASTER**：本批到hardware handoff立即停止。真实KV260到手且另行授权后才做PS software、real DDR、cache handling、actual 100+ frame runtime、real FPS与final image。BOARD_30FPS=NOT_TESTED。当前不自动板测或PS软件开发。

Branch=`codex/curve-fp32-baseline`，HEAD=`660010bfea9f43c99623ee2ba99662292783a02e`；tracked diff=empty，staged diff=empty；既有untracked保留，本批4份handoff/checkpoint文档未暂存。文件变化、原因、差异、执行/未执行验证见完整Phase6报告。未执行git add/commit/push；建议Commit Message：`docs(fpga): deliver V1.2 bitstream XSA and hardware handoff`。
