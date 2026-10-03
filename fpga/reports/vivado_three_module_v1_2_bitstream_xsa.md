# KV260 三模块 V1.2 Phase 6：Bitstream、XSA 与 hardware handoff

日期：2026-10-03（Asia/Shanghai）。结论：**V1_2_HW_HANDOFF_READY**。仅从已通过Phase5 gate的正式routed工程继续write_bitstream，XSA含同一bitstream，artifact SHA/size、实际HWH/driver和交付文档完整。BOARD_30FPS=**NOT_TESTED**。

| State | Result |
| --- | --- |
| CNN_RTL_30FPS | PASS |
| SHORT_MULTI_FRAME_30FPS | PASS |
| IMPLEMENTABLE_CNN_IP | PASS |
| POST_ROUTE_100MHZ | PASS |
| BITSTREAM_XSA | PASS |
| BOARD_30FPS | NOT_TESTED |


## Fixed project and protection audit

工程：[v12_wc.xpr](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.xpr)；Vivado **2025.2**；device **xck26-sfvc784-2LV-c**；clock **100MHz / 10.000ns**。impl_1起始状态=`route_design Complete!`、100%、NEEDS_REFRESH=0；route checkpoint40,519,754 bytes、SHA-256=`d2cf0ba7105da8cd1c51b0def1a64985232fbfea0c6b5119f817a9f8acd8e78d`。正式CNN revision=2114810448；release identity=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`。

开始前只读核对Phase5 gate绑定的全部证据SHA、15,762项受保护文件、完整正式/stable IP文件树、project source/gen树、XPR Configuration/FileSets、BD/address/PS/clock/reset、三writer routed primitive hierarchy，PASS。Phase5批准的11个旧generated synthesis index hash作为已审计基线；本批保留其launch前XML字节。初始byte-only审计因synth_1/gen_run.xml named BlockFileSet引用顺序变化报FAIL，原FAIL已归档；仅该引用集合排列改变，其他XML字节、源/综合/route证据不变，独立复核后窄范围语义审计PASS。最终保护核对见 [protection_after.json](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/protection_after.json)，source drift=0；原route/opt/place/phys_opt阶段end marker的hash及mtime未改变，原routed/其他DCP hash未变。

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
| Generation timestamp | 2026-10-03T13:40:28.338031+08:00 |
| Batch start / end | 2026-10-03T13:36:10.279295+08:00 / 2026-10-03T13:42:14.899008+08:00 |
| Implementation rerun | False；run Tcl只open routed DCP并write_bitstream |

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| bitstream | [system_wrapper.bit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.runs/impl_1/system_wrapper.bit) | 7,797,826 | `8a6c315b50799fb22cb8bfb6f376e3e6992ac41da0abe9c87a8ffc9ced85c915` |
| XSA | [kv260_three_module_v1_2_writecredit.xsa](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/kv260_three_module_v1_2_writecredit.xsa) | 3,068,574 | `09661c4822f05b8c54b000d2fc13893fac3356a970acb4c70a8ca89fb2693ead` |


成功由run status、自然end markers、success log和exit共同证明，不只依赖.bit文件存在。Vivado向原runme.log追加日志；Phase5原字节前缀与备份完全一致，仅新增bitstream段用于本批run审计。实际脚本/launcher、完整console/Vivado/impl logs以及route前日志备份留在 [Phase6 evidence directory](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01)。[bitstream_gate.json](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/bitstream_gate.json)。

批处理preflight有普通Warning：未安装的其他board catalog条目，以及get_files -all中部分对象不适用USED_IN_*属性的报告提示。该TSV中的这些属性为空，不用于证明source membership；源保护由实际全文件树/既有gate与正式CNN catalog/BD身份审计完成。未隐藏或改计日志级别；batch与run均无新Error/Critical Warning，实际各log Warning计数见bitstream_gate。实际write_bitstream run为0 Warning。

## Post-bitstream timing / DRC

| Routed metric | Phase5 | Post-bitstream |
| --- | --- | --- |
| Setup WNS / TNS | +0.636 / 0.000 ns | +0.636 / 0.000 ns |
| Hold WHS / THS | +0.010 / 0.000 ns | +0.010 / 0.000 ns |
| Pulse WPWS / TPWS | +3.500 / 0.000 ns | +3.500 / 0.000 ns |
| Failing setup / hold / pulse endpoints | 0 / 0 / 0 | 0 / 0 / 0 |
| DRC Error / Critical Warning / Warning | 0 / 0 / 198 | 0 / 0 / 198 |


与Phase5 routed timing所有12个summary字段、clock和tool clean状态完全一致；DRC rules/计数相同，仍198条普通Warning；197条details精确相同，RTSTAT-10的first15/20截断预览选择不同，完整20个对象集合未单独比较；未变DCP与差异记录见drc_detail_comparison.json。最终routing=78,288/78,288 complete，unrouted/partially routed/routing errors=0。详见 [postbit_timing_summary.rpt](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/reports/postbit_timing_summary.rpt)、[postbit_drc.rpt](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/reports/postbit_drc.rpt)、[postbit_route_status.rpt](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/reports/postbit_route_status.rpt)。Phase5原timing/DRC证据hash未变。

## XSA export and content audit

`write_hw_platform -fixed -include_bit`自然成功，Vivado export exit=0；导出时间=2026-10-03T13:52:48.034775+08:00。ZIP全成员CRC完整性PASS；唯一embedded bitstream `kv260_three_module_v1_2_writecredit.bit` 大小/SHA-256与外部.bit相同。XSA/HWH实际包含Zynq UltraScale+ PS、formal write-credit CNN、Bilinear、Curve、五个SmartConnect、reset、clock、三段control address map及bitstream；formalCNN hierarchy由同一未变routed DCP验证，CNN release revision2114810448在XSA实际HWH COREREVISION中确认，并与正式package/同源BD/XCI一致。XSA内三个driver header与对应正式packaged IP逐字相同。[xsa_gate.json](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/xsa_gate.json)。

| Control map | Base | Range |
| --- | --- | --- |
| Bilinear | 0xA0000000 | 64KiB |
| Curve | 0xA0010000 | 64KiB |
| CNN | 0xA0020000 | 64KiB |

| CNN pointer | Low / high offset | Payload bytes | Layout |
| --- | --- | ---: | --- |
| INPUT_Q14 | 0x10 / 0x14 | 38,160 | [1, 3, 60, 106] Q14 |
| WEIGHTS_INT8 | 0x1C / 0x20 | 10,075 | packed OIHW in kZeroDceLayers[14] order |
| BIAS_INT32 | 0x28 / 0x2C | 1,944 | one per output channel in layer order; fraction follows frozen quantization protocol |
| WEIGHT_FRAC | 0x34 / 0x38 | 486 | one fractional-bit value per output channel in layer order |
| TANH_LUT_Q15 | 0x40 / 0x44 | 8,194 | Q8 indices -2048 through +2048 |
| A_LOW_Q14 | 0x4C / 0x50 | 38,160 | [1, 3, 60, 106] Q14 |
| WORKSPACE_INT16 | 0x58 / 0x5C | 2,442,240 | six ReLU skip tensors only; convolution working tiles are on chip |


CNN driver SHA-256=`3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362`，canonical ABI=`95077dfd344f411d4bbf8004acee92e369f2e2bf46ae942ba391b41e6ff71598`。七pointer的low/high、三模块全部CSR/参数offset均与XSA实际HWH及正式headers核对；完整width/access、DDR payload/layout、当前六m_axi→HP0/1与Bilinear HP2/Curve HP3、协议引用及release/source/parameter hashes在 [v1_2_hw_register_map.json](E:/github/-/fpga/docs/v1_2_hw_register_map.json) 与 [v1_2_hardware_handoff.md](E:/github/-/fpga/docs/v1_2_hardware_handoff.md)。

旧fixed-point协议数值规则保留；旧单m_axi与4,070,400-byte workspace描述已由新handoff明确替换为六m_axi、2,442,240-byte六skip tensors（frac=[14,14,14,12,13,14]）。未修改原协议文件，未把BFM地址写成板端分配。

## Historical RTL and physical evidence

Phase4F原system RTL证据：8 frames、100MHz、44,112,960 full raw comparisons，raw mismatch/guard/hazard=0；steady max interval=3,307,317 cycles、约30.236 FPS。原报告/analysis保护hash未变，未重跑。Phase4F先验证overlay，Phase4G后将相同三writer固化；本批不混淆这两段来源。[v1_2_phase4f_short_multiframe.md](E:/github/-/fpga/reports/v1_2_phase4f_short_multiframe.md)。

Phase5 post-route evidence：[vivado_three_module_v1_2_implementation.md](E:/github/-/fpga/reports/vivado_three_module_v1_2_implementation.md)；100MHz setup/hold/pulse与最终DRC如上。本批硬件交付不增加真实DDR、cache、板级runtime/FPS或final image证据。

## Changes, validation and Git review

| File | Reason / key difference |
| --- | --- |
| fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md | 正式Phase6自然完成、artifact identity、post-bit timing/DRC与XSA审计 |
| fpga/docs/v1_2_hw_register_map.json | 新V1.2机器可读ABI/地址/DDR/release与artifact hashes；替代旧map来源 |
| fpga/docs/v1_2_hardware_handoff.md | 硬件交付说明、准确workspace/六AXI与板测边界 |
| fpga/reports/v1_2_phase4_checkpoint.md | 当前handoff ready与bit/XSA/hash/NEXT STEP，保留旧Phase4G/5历史 |

已执行：现场只读与全量SHA保护；从现有route自然write_bitstream；自然exit/status/markers/log核对；post-bit实际timing/DRC/route审计及Phase5精确对照；include-bit XSA导出；ZIP CRC/embedded SHA/HWH拓扑地址/CSR/driver ABI审计；机器可读map与文档一致性核验。最终独立审计见 [handoff_gate.json](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/handoff_gate.json)。

未执行：RTL/IP/数学/互连/clock/reset/地址/协议修改，性能优化，新system TB，HLS或implementation重跑，板测，PS软件，real DDR/cache，100+ frame runtime，真实FPS/final image，git add/commit/push/PR，分支操作。外部artifact/log/DCP/backup留E:/HLS，不上传。

建议Commit Message：`docs(fpga): deliver V1.2 bitstream XSA and hardware handoff`。Branch=`codex/curve-fp32-baseline`，HEAD=`660010bfea9f43c99623ee2ba99662292783a02e`；tracked/staged diff均为空；既有untracked保留，本批4份文档未暂存，详见 [git_review.json](E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01/git_review.json)。

NEXT STEP — **WAIT MASTER**。到hardware handoff结束立即停止。真实KV260到手且另行授权后才进行PS software、real DDR/cache、actual 100+ frames、real FPS和final image。**BOARD_30FPS=NOT_TESTED**。
