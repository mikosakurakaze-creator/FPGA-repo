# V1.2 Phase 4G — Implementable write-credit CNN IP

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**IMPLEMENTABLE_CNN_IP_READY / WAIT_MASTER**。报告生成时间：2026-10-03T03:02:22.842568+08:00。

正式 IP 的确定性构建、完整 ABI、综合/仿真源一致性、四组 writer local RTL probe、CNN 单帧、100MHz OOC、独立 V1.2 BD Validate / Output Products / 全系统 synthesis 全部 PASS。本批在 synthesis 停止；不是 post-route timing 或板测结果。

正式 repository entry：[component.xml](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/component.xml)；[build_manifest.json](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/build_manifest.json)；独立 V1.2 工程：[v12_wc.xpr](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.xpr)。

## 固化原因与权威历史

Phase 4E 已验证 write-credit 行为只存在于三颗 generated RTL overlay。原 frozen C++ 是数值参考，重跑 HLS 不会产生该 credit scheduling；临时仿真替换也不能证明 Vivado 综合使用同一实现。本批建立 **frozen r4 export → 输入 SHA gate → 原 generator 确定性三模块替换 → Vivado package → 同源 sanity/OOC → 新 V1.2 工程综合**。

Phase 4E isolated CNN **3,301,639 cycles**；Phase 4F 8-frame steady-state output max interval **3,307,317 cycles**、**SHORT_MULTI_FRAME_30FPS_PASS** 继续保留为权威历史，原日志/分析未改，本批没有重跑 8 帧。[旧 checkpoint](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/checkpoint_before.md)、[Phase 4E](E:/github/-/fpga/reports/v1_2_phase4e_write_retirement_optimization.md)、[Phase 4F](E:/github/-/fpga/reports/v1_2_phase4f_short_multiframe.md)。

## Frozen identity 与三模块差异

Base export：`E:/HLS/kv260_three_module_v1_2_phase4/cnn_r4_export/hls/impl/ip`；base r4 payload identity SHA-256=`1f5dfe5abc335c678198982c0cbb86c2031962ebb6f57570453176da27362c30`，覆盖 **305** 个实际 IP payload 文件。原 HLS pack launcher、日志和旧未补丁 ZIP 不进入正式 entry，原文件仍保留并受保护。

Frozen C++：`candidate_b_rowstream_r4`，未修改。原 Phase 4E generator SHA-256=`520ee47f783c78fe4918f961266c793a2c0a6901539ae62734f595f4575e5823`；overlay manifest SHA-256=`0d98d61cd09b4a216f891ae0115919d414dfaa59b662d8c0fff4865ace451c85`。三个 base RTL SHA 同时与 fresh export 和 Phase 4E 原 syn/verilog 一致。

| Patched Verilog module | Base SHA-256 | Final / verified overlay SHA-256 |
| --- | --- | --- |
| zero_dce_cnn_top_row_axi_writer.v | 16df9195eb8c40234ea42241b8a22f7dfe70767ded33e5c6014c0fed7c35d01e | 4535bf94f686dc5e71f9a55dda9792c03aa8b57d998b902b1e596979dcb08611 |
| zero_dce_cnn_top_row_axi_writer_2.v | d0286ebe5026c4e307aa899a37315c0679f22410350f0cfea70eac818e843862 | 5fb901f88917777169a6327bb27eed4e2171df4e2e17d3b3cb435e17fc4ebf0d |
| zero_dce_cnn_top_p_anonymous_namespace_output_writer.v | 9263f63adaae48237883bfeaf98a63946071742fd46108d2968a3366dd3ffe3f | ed13125479a3892cfbfc2df20f5b4c010c6d2198503231afe7fbfca4ef543dc5 |

仅三颗 RTL 改变：workspace row writer、output row writer、caller/output_writer 控制。原数值算法、地址/顺序、fixed-point、AXI adapters 和 credit=2 行为未变。其余 **301** 个原 payload 文件逐字一致；其中其他 **136** 个 Verilog 源文件及全部归档 VHDL hash 保持原样。唯一非 RTL 修改为 `component.xml` 的打包内部 metadata。

## ABI 与 package metadata

Top=`zero_dce_cnn_top`，VLNV=`xilinx.com:hls:zero_dce_cnn_top:1.0`。全部 top ports、bus/port maps、address spaces、memory/register maps、model parameters、driver、xgui 对 frozen export 严格相等。六 m_axi：`gmem_input/gmem_output/gmem_workspace/gmem8/gmem32/gmem_lut`；`s_axi_control`、`interrupt`、`ap_clk/ap_rst_n` 保持。driver header SHA-256=`3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362`；ABI canonical SHA-256=`95077dfd344f411d4bbf8004acee92e369f2e2bf46ae942ba391b41e6ff71598`。

| 64-bit pointer register | Offset |
| --- | --- |
| INPUT_Q14 | 0x10 |
| WEIGHTS_INT8 | 0x1c |
| BIAS_INT32 | 0x28 |
| WEIGHT_FRAC | 0x34 |
| TANH_LUT_Q15 | 0x40 |
| A_LOW_Q14 | 0x4c |
| WORKSPACE_INT16 | 0x58 |

固定 coreRevision：**2114810447 → 2114810448**，VLNV 不变，用于识别正式替换。原 VHDL synthesis/simulation 两套 view/fileset 含旧 writer，正式 metadata 删除这两个 active 入口；**138** 个 VHDL 文件仅原样归档，不参与源搜索或编译。

Vivado 2025.2 实际执行 open_core/update_checksums/check_integrity/save_core；随后仅规范化可选 address range 格式属性/相应原 checksum，并固定内部 coreCreationDateTime 为 base export 日期；实际构建 timestamp/path 独立记录在 manifest。规范化后再次只读 open_core/check_integrity PASS。所有外部 ABI 值及 XML ABI 子结构保持精确一致。

## 综合源 / 仿真源一致性

正式 Verilog synthesis / behavioral simulation view 共用 **150** 项：**139 Verilog + 2 VH headers + 9 ROM dat**，path/hash 完全相同；综合额外引用原 10ns OOC XDC。独立解析确认 **229** 个 module 定义无重复。每颗 patched writer 仅出现一次，无旧 writer active view、重复 module 或未引用 Verilog shadow。[完整 source manifest](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/source_manifest.json)、[package ABI/fileset audit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/abi_fileset_audit.json)、[独立 byte/ABI/全150项审计](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/independent_package_audit_full.json)。

CNN system sanity 的所有 **139** 个 CNN Verilog 源文件均来自正式 package，其他原 system sources 保持 hash。新 xelab options 只把唯一旧 CNN include 目录替换为正式 package 目录，其余 options 逐字一致；两个 header 只解析到正式路径，旧 CNN include/module search 入口为零。9 ROM data 的运行副本与正式包相同。[header/include audit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06/header_include_audit.json)。

## 正式 IP 功能 sanity

实际 XSIM 四组局部 probe 均自然 exit0；完整数据、地址、WSTRB、WLAST、AW/B 排空及 timing evidence 与 Phase 4E new 原证据完全相等。credit peak2、最终0；全 RAM/guard mismatch0。[local gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/writer_probe_05/writer_probe_gate.json)。

| Scenario | Writer cycles | Actual W overlap rows | Physical AW / WLAST / B |
| --- | --- | --- | --- |
| b1_r0 | 14515 | 90 | 126 / 126 / 126 |
| b1_r4090 | 14515 | 104 | 127 / 127 / 127 |
| b7_r0 | 21745 | 135 | 189 / 189 / 189 |
| b7_r4090 | 21745 | 164 | 190 / 190 / 190 |

最终完整 CNN 单帧：**FRAMES=1、READ/WRITE_OUTSTANDING=2、DDR_DELAY=16、SERVICE_PERIOD=1、POLL_PERIOD=128、100MHz**。真实内部 ap_start=396 → ap_done=3,302,035，**3,301,639 cycles**，与 Phase 4E 精确相等。A_low **19,080/19,080 raw mismatch=0、guard=0、hazard=0**，IRQ gate PASS；7 writer/group block drains、两侧 final credit0、最终 4HP 的 RC/WC/WP/RVALID/BVALID 全0。原 BFM 主体逐字恢复一致，Bilinear/Curve 没有启动。[完整分析](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06/analysis.json)、[自然退出](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06/exit_status.json)、[原始日志](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06/system.log)。

## 实际 OOC / 全系统 synthesis

Vivado **2025.2**，K26 `xck26-sfvc784-2LV-c`，**10ns / 100MHz**。OOC 从正式 synthesis fileset 读取 139 Verilog 和所有 header/ROM，actual compile order 全量核对；三颗 writer 本体 REF_NAME 及 14 个 credit nets 留在实际 synthesis hierarchy。OOC 自然 exit0，生成新 DCP。[OOC gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/ooc_summary.json)、[OOC utilization](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/utilization.rpt)、[OOC hierarchy](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/hierarchy.tsv)。

只有 release 的 ABI/filesets/rebuild/probe/CNN/OOC 全 PASS 后才启动工程替换。使用原 saved V1.2 `system.bd` 新建独立工程，正式 CNN catalog 唯一解析，upgrade/refresh、BD Validate、Generate Output Products、Wrapper、actual full synthesis 全 PASS。Bilinear/Curve 为原 IP 的逐字相同隔离副本；ip cache disabled，不复用旧 CNN DCP。原 BD nets/interface_nets/addressing/design_tree 及所有原配置保持一致；CNN revision 为2114810448。控制地址仍为 Bilinear 0xA0000000 / Curve 0xA0010000 / CNN 0xA0020000，11 DDR masters 与 HP0–HP3/100MHz 拓扑不变。

新 BD 唯一非 CNN 差异为 PS 显式增加 `PSU_MIO_22_INPUT_TYPE=cmos`。原 V1.2 PS XCI/解析 XML 已是同一值；新工程只是把既有解析值写入 BD。审计仅允许这一项且核验原/新有效配置，不放宽其他配置或 cell 字段。第一轮严格逐字 cell 审计因此拒绝；实际 Vivado create/synthesis 均自然 exit0，定位后仅重新执行只读审计，没有重跑综合。除这一显式记录外，非 CNN cells 保持精确一致。

系统实际读取全部 **139** 个正式 CNN Verilog，以及 headers/ROM 共 **150** 项的 hash 与 synth/sim 使用属性，无旧路径或版本；CNN 自身新 synthesis run 成功日志、新 CNN DCP、系统三 writer primitive hierarchy 均核对。[release gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/release_gate.json)、[系统 integration gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/integration_gate.json)、[系统层级证据](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/reports/writecredit_hierarchy.tsv)。

| Actual post-synthesis resource | CNN OOC | Whole V1.2 system |
| --- | --- | --- |
| LUT | 20210 | 40993 |
| FF | 17498 | 47653 |
| RAMB36 | 29 | 29 |
| RAMB18 | 67 | 72 |
| BRAM tiles | 62.5 | 65.0 |
| Equivalent BRAM18 | 125 | 130 |
| URAM | 18 | 18 |
| DSP | 82 | 146 |

资源采用实际 Vivado utilization 实报。OOC `metrics.tsv` 的粗 REF_NAME 计数包括层级/macro，仅诊断，不当作物理资源；[计数来源审计](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/resource_counter_audit.json) 解释差异。OOC 与系统不同综合上下文，不与 HLS area estimate 简单相减。

| Timing / synthesis estimate | CNN OOC | Whole V1.2 system |
| --- | --- | --- |
| Clock period | 10.000 ns | 10.000 ns |
| Setup slack / WNS | +3.212 ns | +2.613 ns |
| TNS / failing setup endpoints | See OOC timing report | 0.0 ns / 0 |
| Pre-route hold slack / WHS | +0.038 ns | -0.093 ns |
| THS / failing hold endpoints | See OOC timing report | -1863.689 ns / 58257 |

100MHz setup estimate 无失败。系统原 timing summary 标记 `Timing constraints are not met`，对应上述 pre-route hold 失败估计。**Hold 仅为未放置、pre-route 估计，不是最终 hold 结论。** OOC ap_clk 未指定 HD.CLK_SRC，时钟 skew 估计有限；本批没有 place/route。[OOC timing](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/timing_summary.rpt)、[系统 timing](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/reports/system_timing_summary.rpt)。

## 可复现构建

两份干净目录 `ip_primary_05` / `ip_rebuild_06` 从同一 frozen export/锁及原 generator 独立执行 base hash → patch → package → 只读 integrity。**全部305项 payload、component.xml、source manifest、ABI audit、driver/三颗RTL逐字相同**。[deterministic rebuild](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/deterministic_rebuild.json)。Manifest identity SHA-256=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`。

Raw component SHA-256=`7e046bd557997e8a8b55b466ee9a76b8c3c321f1435df2879a8bf92a45f54ecd`；raw source manifest SHA-256=`8bb4fc1ee4786b4e89f4ff37b867b529dcfd97ff10970ac405ffecafe4cead3c`；canonical source manifest SHA-256=`834264165a18af1aee973d02dcd2cc5b3a2c28fe33a2731e40ffccbb8568cdcb`；build recipe SHA-256=`7c22e0a24bd5495cd36ed06cc1b275e03e583e436e12c8fb1dd8a43afb5cdab9`；input lock raw SHA-256=`2f9557b96753204ac71cf56fd4df711161c6d95a07d1467a43e064c4c94675bf`。实际 timestamp、输出路径和工作路径仅 execution 字段不同，不参与 release identity。[构建配方](E:/github/-/fpga/ip/cnn_v1_2_writecredit/README.md)、[完整 gate 执行方法](E:/github/-/fpga/perf/v1_2_phase4g/README.md)。

## 保护与尝试记录

原 recovery 审计 **5,235** 项与补充审计集 **3,146** 项前后 hash PASS，changed=[]。覆盖 frozen r4/export、原 overlay/generator、Bilinear/Curve、fixed-point protocol、DDR、V1.1 及原 Phase 4E/F 证据。[before audit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/protection_before.json)、[after audit](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/protection_after.json)。旧 checkpoint 原字节备份保留。

构建候选目录保留真实尝试：loader 缺 ARCH 的启动失败、工具初始化失败及元数据格式/创建时间不确定性均解决后才选最终_05/_06。早期初版 local 自然通过但标为 superseded，不进入 release；CNN05 记录至350,000 cycles后因旧 include 目录的来源审计中止，没有 DONE/全量数值结果，不用于 gate。最终 CNN06 只替换搜索路径后完整自然运行；算法、DUT 字节和 DDR 未更改。未运行的 prepared 目录也不当作验证结果。

## 文件变更、验证与 Git review

| File(s) | Reason / key difference |
| --- | --- |
| fpga/ip/cnn_v1_2_writecredit/build_ip.py | 锁定原export，原generator重现仅3RTL，Vivado package及内部metadata确定性规范化 |
| fpga/ip/cnn_v1_2_writecredit/input_lock.json | 记录所有base payload、原generator/overlay/frozen输入SHA，拒绝漂移 |
| fpga/ip/cnn_v1_2_writecredit/run_ooc.py | 从正式fileset实际OOC，记录clock/resource/timing/compile/hierarchy |
| fpga/ip/cnn_v1_2_writecredit/README.md | 发布配方、ABI/source metadata选择、复建与停止条件 |
| fpga/perf/v1_2_phase4g/protection.py | 原5235项与r4/4E/4F额外证据前后hash、checkpoint备份 |
| fpga/perf/v1_2_phase4g/audit_release.py | 独立核对三RTL差异、完整外ABI、全150项synth/sim及逐byte复建 |
| fpga/perf/v1_2_phase4g/sanity_sources.py | 严格解析正式源与实际compile list，拒绝旧module/source drift |
| fpga/perf/v1_2_phase4g/prepare_sanity.py | 复用原BFM/probe，新来源清单与唯一include路径替换 |
| fpga/perf/v1_2_phase4g/run_sanity.py | 4有界probe及1完整CNN单帧，绑定kernel/manifest/实际exit |
| fpga/perf/v1_2_phase4g/analyze_sanity.py | 原独立analyzer及Phase4E精确匹配、原BFM恢复、全HP drain |
| fpga/perf/v1_2_phase4g/make_release_gate.py | 全部正式IP gate通过后才生成绑定证据SHA的integration release |
| fpga/perf/v1_2_phase4g/run_integration.py | fresh V1.2项目/隔离稳定IP、source+BD+resource+timing实际gate |
| fpga/scripts/vivado_three_module_v1_2_phase4g_create.tcl | 只解析正式CNN catalog并替换原CNN revision，fresh BD validate |
| fpga/scripts/vivado_three_module_v1_2_phase4g_synth.tcl | output products/actual synthesis，明确writer hierarchy及禁implementation |
| fpga/perf/v1_2_phase4g/finalize_reports.py / README.md | 只有完整release/system/protection PASS才写报告与checkpoint，记录执行方法 |
| fpga/reports/v1_2_phase4g_implementable_cnn_ip.md | 本批事实、完整证据与review |
| fpga/reports/v1_2_phase4_checkpoint.md | 当前ready状态与下一批交接，Phase4F权威历史保留 |

已执行：SHA保护、原generator确定性重现、Vivado package/只读 integrity、全 ABI/driver/source views 审计、干净复建、最终四local、CNN06完整单帧、实际OOC、fresh catalog/upgrade/BD validate/output products/system synthesis、source/hierarchy/resource/setup估计/hold如实记录。

未执行：性能优化、新 HLS csim/synthesis/export、8/100-frame、implementation/route、post-route timing/DRC、bitstream/XSA、板测、git add/commit/push、PR、创建/切换/删除分支。仅进行了综合后的 DRC 报告，不等同下一批 post-route DRC。

Branch=`codex/curve-fp32-baseline`，HEAD=`660010bfea9f43c99623ee2ba99662292783a02e`；tracked diff=empty，staged diff=empty。既有 untracked 保留，本批源/报告均未暂存。[完整 Git review 状态](E:/HLS/kv260_three_module_v1_2_phase4/phase4g/git_review.json)。外部 E:/HLS IP/build/log/DCP/数据/备份不自动上传。

建议 Commit Message：`build(fpga): freeze write-credit CNN IP and validate V1.2 synthesis`。本批修改完成后停止等待 Master 审核，没有任何 Git 写操作。

## IMPLEMENTABLE_CNN_IP_READY 与 NEXT STEP

**IMPLEMENTABLE_CNN_IP_READY**。正式 IP+可复现性+同源功能/OOC+独立 V1.2 BD/system synthesis 均 PASS；到此立即停止。下一批仅在 Master 明确授权后进行 Vivado implementation/route、post-route setup/hold timing 与 DRC。本批不自动进入后续流程。
