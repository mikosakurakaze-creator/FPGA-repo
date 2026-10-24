# 继续实施与核查记录

更新至 2026-10-24 15:42（Asia/Shanghai）。本页只记录已经取得的证据；长时流程的后续状态以 `D:/weather_builds/grid_system02/workflow.json` 和 `build.json` 为准。

## 数值与边界复核

- `work/frame_rtl05`：4×4，冷暖各一帧，全部 320 节点逐值一致；仿真分别 6,529,321、6,530,839 周期。
- `work/frame_rtl_odd02`：5×7，冷暖各一帧，全部 320 节点逐值一致；仿真分别 10,174,501、10,175,689 周期。其旧报告 `case` 标签未随显式 Golden 更新，真实尺寸和来源字段正确；代码已修正，不覆盖历史报告。
- 两次回归均完成错误 model 拒绝、延迟写响应排空、实际 SV 错误 Golden 检出及 AXI 内存边界检查。新增的“错误 model 不得产生 DDR 流量”断言稍后加入，将由当前系统网表回归实际执行；不倒签为上述旧快照已验证。
- 使用 A 原始 `griddehaze_fixed.compare_fpga`，分别对上述四份原始最终输出再次比较，四次均 `exact=true`、零差异、输入 SHA 一致。报告为 `work/a_compare_rtl4_{cold,warm}01.json`、`work/a_compare_rtl5x7_{cold,warm}01.json`。
- 随后将 4×4、5×7 各自实际暖态的 320 份节点捕获按 A 文件名复制到新的本地目录，再由 A 比较器逐元素独立核查，均 `compared_nodes=320`、`exact=true`。报告位于 `work/a_compare_nodes_4x4_warm01/comparison.json`、`work/a_compare_nodes_5x7_warm01/comparison.json`；各自 `mapping.json` 记录原始捕获路径和哈希，不重新计算或改写节点数值。冷态的全节点检查仍由 SV 测试台完成，没有声称 A 比较器复核了未独立保存的冷态中间值。
- 上述周期含测试内存背压及 MMIO，不是实板帧率；所有记录均非真板验证。

## 正确五核系统综合

`D:/weather_builds/grid_system02` 已通过 create 和 synth；旧核来源及保护见 `system_seed_correction_20261024.md`。综合阶段真实退出码为 0，完整标记为 `GRID_SYSTEM_SYNTH_PASS`。

| 资源 | 实际综合使用量 | 可用量 | 占比 |
|---|---:|---:|---:|
| LUT | 92,602 | 117,120 | 79.07% |
| FF | 96,134 | 234,240 | 41.04% |
| BRAM tile | 116 | 144 | 80.56% |
| DSP | 1,009 | 1,248 | 80.85% |
| URAM | 47 | 64 | 73.44% |

来源：`synthesis_utilization_summary.rpt`，状态 `Synthesized`。资源尚未超过器件容量，但余量不能证明布线和时序一定通过。不能沿用旧三模块或误选候选的百分比。

`compiled_sources_audit.json` 检查实际综合生成的五核全部 524 份 Verilog/ROM；529 项核查通过、失败 0。同时检查每核综合完成与 ROM 加载记录，不仅检查 VLNV 或输入 IP 文件。

已进入 implementation，保留原 signed-DSP PRE/POST 精确保护。其后流程为当前完整系统布线后新核冷暖回归、旧核 0/0/1/0 四帧回归、最终 bit/XSA 导出及本地同版文件收集。任一步失败就停止，不跳过门禁。

截至 15:29，signed-DSP PRE、POST 精确连接/OPMODE 核查均已输出 `WEATHER_SIGNED_C_SOURCE_AND_OPMODE_PRESERVED`，已进入实际布局；布线结果仍待执行。

截至 15:41，`system_wrapper_placed.dcp` 已生成，实际完成布局并进入 `phys_opt_design`。日志中的 `Post Placement Timing Summary WNS=1.194` 仅为布局阶段 setup 估算，不是最终 routed timing，也没有据此生成交付结论。

## 大向量测试预算修正

在核查 `work/frame_rtl_33x47_01` 时发现：测试台原全局延迟为 `#600000000`，在 10 ns 时钟下仅允许总计 60,000,000 周期，却比单帧 200,000,000 周期 watchdog 更短。小图冷暖回归不受影响，但该预算不能用于原始 33×47 跨 tile 用例。

已精确核对可执行路径，仅停止该 33×47 的 xsimk，未停止 Vivado 或其他程序。其原 `result.json` 保持失败，`interruption.json` 记录中止原因、最后进度及替代目录；没有将部分节点通过写成整图通过。

`system/frame_axi_test.sv` 改用周期条件等待；`tools/frame_rtl_trial.py` 新增可显式配置的 `--max-frame-cycles`，并使全局预算为两帧预算加 1,000,000 周期，检查范围不超过 signed32 计数器。预算是测试配置，不是实测延迟，也不改变 HLS、IP、时钟或算术。

已重新启动 A 原包用例 `work/frame_rtl_33x47_02`，每帧上限 500,000,000 周期，目前仍运行中。

`work/frame_rtl06` 已完成最新测试台的 4×4 冷暖两帧，全部 320 节点精确一致，错误 model 禁止 DDR 流量断言、延迟 B 排空及 SV 错误 Golden 检出均通过。实际两帧周期仍为 6,529,321 / 6,530,839，说明改变的是测试 watchdog，而非计算核或计算结果。

## 导出前证据保护

`tools/build_grid_system.py` 在导出前重新检查新核两帧实际输出的长度和 SHA、仿真日志 SHA/退出码及负对照记录。`work/release_evidence_guard01/result.json` 使用已通过 RTL 的真实捕获文件验证该检查：正常文件通过；1 LSB 输出篡改、日志篡改均被拒绝。该用例是发布检查逻辑测试，不是布线后 DUT 测试。

## 当前未完成与 Git 状态

当前完整数值回归、板端 DDR 分配和真板验收仍未执行。按用户要求已采用 reduced gate 导出本地 bit/XSA，完整门禁结果不能由该导出替代。

修改位于独立 `griddehaze_fpga`；该目录没有 `.git`。本轮未暂存、提交、推送或切换分支，旧参考仓库只读。建议后续审核后的 Commit Message：`feat(griddehaze): add full graph core and verify preserved legacy system`。

## 本次继续工作的文件变更

| 文件 | 原因及关键差异 |
|---|---|
| `tools/build_grid_system.py` | 导出前重读实际两帧捕获、日志和负对照证据，拒绝输出或日志已改变的陈旧 PASS |
| `tools/frame_rtl_trial.py` | 显式 Golden 的用例标签取真实目录名；新增单帧周期预算，生成覆盖冷暖两帧的总预算并检查计数器范围 |
| `system/frame_axi_test.sv` | 全局 watchdog 从固定小图时间改为周期条件，采用同一配置的单帧上限 |
| `README.md` | 更新正确系统综合、RTL 和 A 比较器复核状态，链接本次跟进记录 |
| `docs/hardware_execution_20261024.md` | 更正当前构建目录，记录真实整机综合资源及源码来源核查 |
| `docs/frame_change_review_20261024.md` | 补充实际源码审计、自动流程、发布门禁和本轮测试台问题 |
| `docs/reproduce_frame_system.md` | 增加最新小图回归证据及 33×47 周期预算复现命令 |
| `docs/execution_followup_20261024.md`（新增） | 记录本次实际执行、来源纠正后的物理阶段、已修问题与未完成事项 |

已执行 Python 全部工具源码语法检查、中文 Markdown UTF-8 检查、发布证据篡改负测、A 比较器独立复核及最新小图 RTL 回归；未把运行中的 33×47、routed 回归、bit/XSA 或真板工作列为通过。只读参考仓库仍在 `weather_fpga_integration` 分支，工作区干净。

## 17:00 后继续执行

- 将已完成的 `frame_synth01`（1,237 文件）和 `frame_csim01`（2,637 文件）完整复制到本目录 `work/`，逐文件 SHA-256、文件数和总字节数复核一致；没有覆盖已有目录。
- 在本目录重新执行 `tools/preflight.py --out work/preflight_local03`，INT16/INT8 参数包、320 节点图和 4×4 至 720p 地址规划全部通过。
- 以实际 `grid_system02` routed 网表、DRC 和 Vivado 2025.2 `DSP48E2.v` 运行 19 个 DPREG-7 单元的稳定 OPMODE 组合审计，结果 `pass_no_stable_binary_p_feedback=true`。该结果不等于物理转换或真板验证；原始 DRC Warning 仍保留。
- 重新运行 `tools/audit_grid_system.py` 对 `grid_system02` 的 BD 结构、四个旧核、PS 参数、HP0/HP3 128-bit 窗口和新核 `0xA0040000` 控制区做审计，结果通过；报告为 `work/grid_system02_audit_local.json`，仍仅是结构配置证据。
- 用当前目录的源码、Golden 和共享 DDR fixture 启动新的 33×47 RTL 冷暖两帧回归：`work/frame_rtl_33x47_03`。本日志会显示逐节点进度；整个冷暖两帧和负向检查未完成前不记为通过。
- 已增强 `tools/continue_grid_system.py`，允许在等待模式下接收已有运行的跨 tile 目录，但只在 `validate_cross_tile` 校验源码、Golden、所有节点文件、两帧日志、fixture 和实际综合网表身份全通过后，才记录该门禁并继续；失败证据会停止流程。
- 使用上一版 `_02` 的实际 PASS 结果做负向门禁检查，新门禁以“没有稳定源码快照”拒绝该旧结果，没有拿它冒充新 harness 证据。
- 已启动续跑工作流等待上述回归：workflow scope 仍明确禁止 Git 与真板操作。若跨 tile 通过，它将继续完整 routed 网表新核回归、旧天气链路回归、bit/XSA 导出和本地板端文件收集；工作流状态在 `D:/weather_builds/grid_system02/workflow.json`。

## 18:54 Reduced export update

按用户要求，为尽快给下游上板，停止仍在运行的 33×47 严格跨 tile 仿真，并采用必要门禁导出：实际源码/ROM 审计、综合、布局布线、100 MHz routed timing、route status 和 bitstream 前 DRC。Vivado 2025.2 写 bitstream 成功，DRC 为 0 Errors，XSA 创建成功；bit 与 XSA 内嵌 bit 已逐字节核对。

发布文件在 `board/releases/k26_weather_griddehaze_reduced_20261024/`。该发布明确标记跨 tile 双帧、routed 数值回归、旧核连续帧和真板验收为 deferred，不能把 reduced export 当作完整数值 release。
