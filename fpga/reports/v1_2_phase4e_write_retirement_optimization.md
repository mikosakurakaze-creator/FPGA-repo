# V1.2 Phase 4E — CNN workspace row-write retirement optimization

日期：2026-10-02（Asia/Shanghai）。CURRENT STATUS：**WRITE_RETIREMENT_FIX_SUFFICIENT / WAIT_MASTER**。

结论 **A**：**WRITE_RETIREMENT_FIX_SUFFICIENT**。固定 O=2 下 CNN 从 **3,421,992 → 3,301,639 cycles**，实际节省 **120,353**；30FPS budget=3,333,333，剩余 gap=0，预算余量=31,694。A_low **19,080/19,080 raw mismatch=0**、guard=0、hazard=0，七个 block 的所有写响应 drain PASS。单阶段 gate：**CNN_SYSTEM_STAGE_30FPS_PASS**。达到 CNN 单阶段预算；没有验证系统 steady-state 30FPS。

## 权威基线、执行顺序与限制

先读取 [Phase 4D checkpoint 备份](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_checkpoint_before.md) 和 [Phase 4D residual profile](E:/github/-/fpga/reports/v1_2_phase4d_cnn_residual_profile.md)；旧完整帧来自 [Phase 4C O=2 stage_events.csv](E:/HLS/kv260_three_module_v1_2_phase4/phase4c_01/single_o2/results/stage_events.csv)，CNN ap_start=396、ap_done=3,422,388。poll 不在 hardware latency 内；旧完整帧未重跑。

实际顺序：独立候选 → 8 次有界 writer RTL old/new 验证 → 局部 actual-data overlap gate PASS → 完整 CNN 单帧 system TB → 19080 raw/guard/hazard/drain 检查 → 独立分析及保护审计 → 报告。局部证明成功后才启动完整 CNN；[完整运行记录](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_system_02/exit_status.json)记录使用的不可变局部 gate SHA256。参数 **FRAMES=1、READ_OUTSTANDING=WRITE_OUTSTANDING=2、DDR_DELAY=16、SERVICE_PERIOD=1、POLL_PERIOD=128、100MHz**；实际 runtime 参数也核对。

没有 short multi-frame、FRAMES=8/100、implementation、route、bitstream/XSA、板测、git add/commit/push 或分支切换。原 Bilinear/Curve/DDR model v2/Vivado V1.2 BD、fixed-point protocol、DW/PW MAC lanes、rowstream主体和 CNN 数学不变。完整 system 环境仅完成 CNN 原 BFM 检查后停止，未启动 Bilinear/Curve；其 Phase 4C 成绩保持为历史结果。

## 独立候选与关键差异

[candidate_b_rowstream_r4_writecredit](E:/github/-/fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4_writecredit/README.md) 是 **RTL scheduling overlay**，不是新 HLS 综合/export 或可实施的硬件发布。三个 C++/header/TB 文件仅为逐字一致的 frozen 数学参考；重综合这些 C++ 不会生成 credit 调度，本批没有 HLS 重综合。frozen `candidate_b_rowstream_r4` 未修改。

旧 writer：每行 HLS request → 106 个 INT16 数据 → 本行 B → helper done → 下一行。Phase 4D 首块 source physical WLAST→B 为37–39 cycles，row interval 中位数161，writer最后完成。

新 writer：保留原地址计算、106-scalar数据 pipeline 和控制开销；helper数据发送完成即可 done/ready，不再等待本行 B。2-bit `credit_count` 在 accepted **logical HLS row request** 时加1、在 coalesced logical B 时减1；满2禁止发出新行，B可独立退休；同拍 request+B 不改变计数。每个 block 末端的 done latch、ap_done、ap_ready和FSM出口都等待 workspace/output 两侧 credit=0，终点FSM等待 drain 后才进入下一 block。

Credit 是整行请求，非4KB拆分后的 physical burst数。原 m_axi adapter保持16 outstanding接口配置、原packing/WSTRB/WLAST/4KB split和每行合并 B；system memory boundary始终O=2。source端允许两行的拆分burst同时排队（实测max3），HP0队列max2；没有扩大任何outstanding配置。Helper send done只表示数据被原adapter接受；block done才保证外部AW/W/B全部完成。

仅三个 RTL module 不同：workspace `row_axi_writer`、output `row_axi_writer_2`、caller `p_anonymous_namespace_output_writer`。七pointer ABI、六m_axi bundle、row地址/顺序、workspace/A_low layout和Q14数据不变；build manifest和原source保护见后节。

## 局部 RTL 证据

[不可变局部 gate](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_writer_probe_03/comparison.json)；[独立扩展统计](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_writer_probe_03/comparison_final.json)；各scenario的 `timeline.csv`、`evidence.json`、`actual.hex`、`run.log` 保留同目录。

实际 XSIM 使用原 output_writer、两侧原 HLS AXI32 adapter及未修改DDR v2；O=2、B delay=16、service=1。Probe使用testbench lane placement连接AXI32与DDR128，**没有SmartConnect**；完整system测试补上原SmartConnect路径。workspace block1用2 channels/120 rows，A_low block7用3 channels/180 rows，base residue=0和4090覆盖aligned、半字对齐、4KB拆分及partial WSTRB。

| Probe | Old cycles | New cycles | 节省 | 平均 row interval | 实际 W overlap rows |
| --- | --- | --- | --- | --- | --- |
| b1_r0 | 17135 | 14515 | 2620 | 142.72269 → 120.72269 | 90 |
| b1_r4090 | 17136 | 14515 | 2621 | 142.73109 → 120.72269 | 104 |
| b7_r0 | 25685 | 21745 | 3940 | 142.64804 → 120.64804 | 135 |
| b7_r4090 | 25686 | 21745 | 3941 | 142.65363 → 120.64804 | 164 |

row interval 中位数 **142 → 120**，范围 **142–146 → 120–124**；均值差约22cycles。Old credit peak1，新peak2，全部final0。Aligned workspace physical AW=WLAST=B=126（6个split rows），stress=127（7个split）；A_low aligned189（9split），stress190（10split）。半字对齐每行首尾WSTRB为c/3，中间f；旧/新每个AXI channel的请求、数据、WSTRB和顺序完全相同。

**Aligned workspace 前三行时间线（probe cycle；ROW_AW为HLS整行请求，AW/WLAST/B为真实AXI32）：**

| Row | Old ROW_AW / AW / WLAST / B / logical B | New ROW_AW / AW / WLAST / B / logical B |
| --- | --- | --- |
| 0 | 22 / 31 / 137 / 155 / 158 | 22 / 31 / 137 / 155 / 158 |
| 1 | 164 / 173 / 279 / 297 / 300 | 142 / 151 / 257 / 275 / 278 |
| 2 | 306 / 315 / 421 / 439 / 442 | 262 / 271 / 377 / 395 / 398 |

New row1 **first physical W=153 < row0 final physical B=155**，已经开始发送下一行实际数据；不是仅提早排AW。row1 WLAST257不早于B155，本批证明的是发送开始 overlap，不夸称整行发完。新credit在22→1、142→2、158→1、262→2、278→1，最终0。4KB stress第一行AW31=0x10000ff8/2beats、AW35=0x10001000/52beats，WLAST34/137、B52/155，整行logical B158；每笔burst4KB内、WLAST逐笔正确。

局部逐字数据一致；整个4096×128-bit RAM与独立expected图逐字比较，同时核对允许写入byte mask，guard=0；WSTRB按行字节范围独立推导；旧/新AW和W channel分别比较，允许其合法交织变化。每笔AW/WLAST/B一一对应，DDR队列和logical credit最终完全排空。两套source manifest共280条项在8次成功运行后重新hash PASS。

前两次局部工具尝试未形成有效数值/overlap证据：portable Verilator的C++链接兼容问题；XSIM Windows路径plusarg引号问题。换为修复后的独立probe03，8次全部自然完成exit0；没有改DUT/model来绕过错误。system01仅prepared未执行；修正observer对HLS内部metadata/未对齐HP beat的解释后，system02 elaboration和唯一完整CNN运行成功；这是验证代码修正，非功能或模型放宽。

## 完整 CNN gate 与 block drain

[完整 system 分析](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_system_02/analysis.json)；[stage events](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_system_02/results/stage_events.csv)；[原日志](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_system_02/system.log)；[block drains](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_system_02/results/block_drains.csv)。

| 指标 | Old | New |
| --- | ---: | ---: |
| CNN internal ap_start→ap_done | 3,421,992 | 3,301,639 |
| 实际节省 | — | 120,353 |
| 要求节省 | — | ≥88,659 |
| 30FPS单阶段budget | 3,333,333 | CNN_SYSTEM_STAGE_30FPS_PASS |
| 剩余gap / 预算余量 | 88,659 / -88,659 | 0 / 31,694 |
| A_low raw mismatch | 0（历史） | 0 / 19,080 |
| Workspace guard / hazard | 0 / 0（历史） | 0 / 0 |

实际内部 ap_start=396、ap_done=3,302,035，差值=3,301,639；未拿软件轮询观察点制造收益。原BFM比较19,080项raw并检查全部region guard、ownership/hazard及IRQ；检查后在CNN阶段停止。writer done、group done以及下一group start均核对logical credit0、source及HP AW=WLAST=B、DDRwrite queue0；七个writer/group边界全部PASS，最后所有response drain。

| Block | Group start | Group done | Elapsed | PW done | Writer done | PW→writer tail |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 18040 | 258517 | 240477 | 229993 | 258517 | 28524 |
| 2 | 258520 | 607313 | 348793 | 591503 | 607313 | 15810 |
| 3 | 607316 | 956109 | 348793 | 940299 | 956109 | 15810 |
| 4 | 956112 | 1304905 | 348793 | 1289095 | 1304905 | 15810 |
| 5 | 1304908 | 1984229 | 679321 | 1968419 | 1984229 | 15810 |
| 6 | 1984232 | 2663553 | 679321 | 2647743 | 2663553 | 15810 |
| 7 | 2663556 | 3302033 | 638477 | 3300481 | 3302033 | 1552 |

首block group18040→258517=240477，旧319164，局部前缀改善78687；PW compute done229993，writer尾部28524（旧39104）。Actor elapsed含stream backpressure，不是纯MAC compute。整帧节省使用最终stage差值，没有将各actor或Btail积分叠加冒充节省。

完整system首block的逻辑row请求interval中位数为 **120 cycles**，对比Phase 4D旧row start interval中位数161；新首block均值125.22355（含producer间歇）。全workspace逻辑row interval中位数同为120、均值229.67344；后块producer等待不能视为退休屏障。新source physical WLAST→B仍为37–39、median37，DDR和SmartConnect响应路径未被缩短，收益来自隐藏逐行响应等待。

| 层级 | AW / data-end / B | Max pending | Final pending |
| --- | --- | --- | --- |
| workspace | 12104 / 12104 / 12104 | 3 | 0 |
| output | 189 / 189 / 189 | 3 | 0 |
| hp0 | 12293 / 12293 / 12293 | 2 | 0 |
| logical_workspace | 11520 / 11520 / 11520 | 2 | 0 |
| logical_output | 180 / 180 / 180 | 2 | 0 |

完整logical workspace11,520行、A_low180行；physical workspace12,104 bursts、A_low189。地址/长度/顺序逐笔与独立冻结row schedule枚举严格一致；HP0逐笔首地址和upsized长度与source配对。WSTRB/WLAST/4KB/BRESP assertion及原DDR模型检查PASS。workspace和A_low source WSTRB均f，logical scalar WSTRB3。Logical内部WLAST为0且AWSIZE无需按AXI解释，106 accepted scalar W推导ROW_DATA_END；不混淆内部HLS协议与真正AXI。

## Writer residual barrier 占比

Writer active elapsed sum=3,283,940。等待计数来自实际RTL：满credit时行请求准入等待、所有行发完后的terminal drain等待。

| 观察 | Cycles | 占 writer active elapsed | 占 CNN cycles |
| --- | --- | --- | --- |
| credit=2 导致行请求准入等待 | 0 | 0.000000% | 0.000000% |
| 七个 block 终点等待 drain | 273 | 0.008313% | 0.008269% |

Credit占用为2的累计周期workspace397,163、output6,150；它们是占用时间，实测准入等待仍为0，不能把占用当成stall。以上是观察占比，含与其他actor并行的时间，不是可直接追加的因果节省；source WLAST→B、queue integral也不能直接累加。达到 CNN 单阶段预算；没有验证系统 steady-state 30FPS。没有自动修改reader、rowstream、MAC、DDR或其他stage。

## 验证范围、文件与 Git 状态

保护审计：[执行前](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_protection_before.json)、[执行后](E:/HLS/kv260_three_module_v1_2_phase4/phase4e_protection_after.json)；恢复manifest原 **5,235文件** hash全部一致，changed=[]。frozen4个直接C++/config文件和原3writer RTL hash保持一致，候选3个math reference字节一致，3个overlay按生成器重现一致。完整snapshot的原363source、3overlay、16份PL/DDR/hex/ROM/options copy分别hash PASS；运行kernel与启动记录一致，局部gate SHA与启动记录一致。

新增文件/原因：

- `fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4_writecredit/`：3个writer RTL overlay、3个冻结C++/header/TB参考、README、candidate_manifest；隔离候选，保留数据与ABI。
- `fpga/perf/v1_2_phase4e/build_writecredit_candidate.py`：只从frozen生成3个调度overlay，拒绝覆盖已有candidate。
- `fpga/perf/v1_2_phase4e/run_writer_probe.py`：有界old/new RTL时间线、数据/guard/协议及实际W overlap检查。
- `fpga/perf/v1_2_phase4e/prepare_system.py`：仅替换3writer source并增加passive observer，保留原system/DDR/BD/数值oracle。
- `fpga/perf/v1_2_phase4e/run_system.py`：局部gate核对后只运行规定CNN单帧。
- `fpga/perf/v1_2_phase4e/analyze_system.py`：独立核对cycles、row footprint、完整数值、7block drain、credit及barrier统计。
- `fpga/perf/v1_2_phase4e/verify_protection.py`：原5,235项和独立候选hash保护。
- 本报告：完整本批证据；`v1_2_phase4_checkpoint.md`：更新交接状态，旧checkpoint在外部备份。

已执行：8有界局部XSIM、一次完整CNN system XSIM、原raw/guard/hazard/IRQ检查、各层response/credit drain及footprint、独立分析和前后hash保护。未执行：新的HLS csim/synthesis/export、Bilinear/Curve运行、short multi-frame/steady interval/pipeline overlap、implementation/route、bitstream/XSA、板测或任何Git写操作。

Branch=`codex/curve-fp32-baseline`，HEAD=`660010bfea9f43c99623ee2ba99662292783a02e`；tracked/staged diff为空，既有untracked保留，本批candidate/scripts/report/checkpoint未跟踪。未创建/切换/删除分支。外部仿真build/日志/hex/备份保留E:/HLS，不上传GitHub。建议Commit Message：`perf(fpga): decouple CNN row writes from response retirement`。

## NEXT STEP — WAIT MASTER

本批验证及报告完成后立即停止，等待Master审核 **WRITE_RETIREMENT_FIX_SUFFICIENT**。不自动进入short multi-frame、implementation、route或bitstream/XSA，不执行git add/commit/push。单阶段结论不等同系统steady-state30FPS；RTL overlay也未成为新HLS/IP或实施结果。
