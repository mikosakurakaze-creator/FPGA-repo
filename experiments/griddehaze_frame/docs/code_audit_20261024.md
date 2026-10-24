# GridDehazeNet 代码、数据依据与运行证据审查

审查时间：2026-10-24 16:07，Asia/Shanghai。复查包括已结束的 implementation 报告和仍在运行的 33×47 RTL 测试。

范围：`competing/griddehaze_fpga` 的 HLS 算术与整图调度、参数生成、DDR 测试模型、系统构建和导出检查。参考仓库 `github clone/weather_fpga_integration` 只读。

## 结论

没有发现用临时编造的权重、尺度或 Golden 替代 A 冻结数据的证据。小图捕获结果一致。审查发现的地址冲突已修复；跨 tile 和时序门禁已补上强制校验。33×47 新 harness 回归仍待运行，因此目前还不能宣布整版通过验收，也不能导出 bit/XSA。

## 1. 大图仿真地址重叠，被独立 RAM 模型掩盖（P2）

位置：`tools/ddr_fixture.py`、`tools/frame_rtl_trial.py`、`system/frame_axi_test.sv`。

旧脚本把特征内存基址固定为 `0x10000000`、参数内存基址固定为 `0x20000000`，并实例化两块各自独立的 RAM。实际系统的两条 HP 路径均映射同一低 DDR 地址空间，不能把相同物理地址当作两份存储。

已新增模拟 DDR 地址规划器：先放 input/output/scratch，再将参数与 layout 区域放到完整 feature aperture 之后，并检查五个整段 slot 在 HP0/HP3 共用的物理地址空间中互不重叠且位于低 2 GiB。重新按冻结图的实际内存规划计算：

| 尺寸 | feature aperture 大小 | 参数区基址 | 区域重叠 |
|---|---|---|---|
| 4×4 | 20,480 B | `0x20000000` | 否 |
| 33×47 | 823,296 B | `0x20000000` | 否 |
| 675×1280 | 452,743,168 B | `0x2afd0000` | 否 |
| 720×1280 | 482,922,496 B | `0x2cc90000` | 否 |

影响：新的仿真 fixture 会显式检查共享 DDR 地址区间，不会把大图 scratch 与参数区的物理别名藏在独立 RAM 后端中。它仍是仿真地址规划，不是板端 CMA/DDR 分配证明。正在运行的 `_02` 是修复前启动的测试，结果不会用作新门禁的跨 tile 证据。

验证：对 4×4、33×47、675×1280、720×1280 按冻结图重算，所有五个区域均无重叠并在低 2 GiB。地址仍明确标记为 simulation-only。

## 2. 自动导出未绑定跨 tile 回归（P1，交付验收缺口）

位置：`tools/continue_grid_system.py`、`tools/build_grid_system.py`、`tools/release_gates.py`。

已修复：自动流程新增 33×47 全图逐节点测试；bit/XSA 导出会验证 shape、320 个 Golden 节点文件、冷/暖两帧、负对照、仿真日志、当前冻结包身份、全部 RTL 文件哈希和模拟 DDR fixture。只传 `--cross-tile-test` 路径但证据不匹配不再能放行。

原 `_02` 测试正在运行，但它在新地址 harness 和证据校验加入前启动，因此不能满足新门禁。修复后的新 33×47 回归尚未完成。

影响：旧自动流程可能把 4×4 通过误当成覆盖跨 tile。新导出现在硬性要求 33×47 测试；即使该测试通过，也只证明该 shape 的 exported RTL + 模拟 AXI RAM 数值一致，不等于 720p PL、真板或持续帧通过。没有发现已生成并交付的错误宣称产物。

## 3. Routed 时序通过；DRC 警告仍需留意（P2）

位置：`system/impl.tcl`、`system/export.tcl`、`tools/release_gates.py`。

已新增 routed signoff 解析与导出门禁：要求 check_timing 分类计数全为 0、100 MHz 时钟、WNS/WHS/WPWS 非负且无失败端点、全部 routable nets 完成且无 route error；DRC Error 或 Critical Warning 会阻止导出。实现阶段的 Python 检查会解析报告；导出阶段重新解析，并要求 signoff marker；`export.tcl` 也拒绝没有 marker 的直接调用。

已完成的 routed 报告复查结果：12 类 `check_timing` 项均为 0；`no_clock`、`constant_clock`、`multiple clocks` 和 `generated clocks` 详细项均为 0。`clk_pl_0` 和 `clk_pl_1` 均为 10 ns/100 MHz。WNS `+0.729 ns`、WHS `+0.010 ns`、WPWS `+3.500 ns`；三类失败端点均为 0。191,089/191,089 个 routable nets 完成路由，routing errors 为 0。

DRC 有 1,102 条 Warning、0 条 Error/Critical Warning：DPIP-2 572 项、DPOP-3 233 项、DPOP-4 277 项、DPREG-7 19 项、RTSTAT-10 1 项。DPIP/DPOP 是 DSP 流水寄存器的性能建议；DPREG-7 提醒动态 OPMODE 在特定 P feedback 组合下可能出现未寄存反馈路径；RTSTAT-10 涉及无可布线负载的网。对实际 routed 网表和 Vivado 2025.2 DSP 模型枚举 19 个 DPREG-7 单元的稳定二值组合后，未发现稳定 P 反馈选择，详见 `docs/dpreg_opmode_audit_20261024.md`。该审计不覆盖物理转换毛刺、SDF 行为或其他 Warning，时序报告 clean 也不能自动消除普通 DRC Warning。新门禁会阻止 Error/Critical Warning，但会保留并记录普通 Warning。

`tools/release_gates.py` 对本次实测 timing、route 和 DRC 报告解析通过，并通过负 slack、未完全布线及 Critical Warning 负对照。

因此初审里的 8 个综合期 no_clock 对象已由 routed 报告明确消除，不构成功能时钟接错证据。DPREG-7 等 DRC 警告仍是单独的待复核项。

后续每次 implementation 和 export 都会要求同样的 routed signoff 门禁；signed-DSP 保护不变。

## 4. 工作流记录的是结束时脚本哈希（P2，证据溯源问题）

位置：`tools/continue_grid_system.py`、`tools/build_grid_system.py`、`tools/frame_rtl_trial.py`。

已修复新流程：构建与自动工作流记录执行前后脚本及相关依赖哈希；源文件运行期间发生变化时该阶段失败。RTL 回归记录 testbench、DDR fixture、运行脚本、Golden/RTL 身份，并拒绝不稳定源码快照。

历史实现运行启动时 `tools/build_grid_system.py` 在运行期间被编辑，因此历史 implementation wrapper 的启动哈希没有留存。不能伪补这个版本号。实际被 Vivado 执行的 `impl.tcl` 哈希、综合/布线 checkpoint、route 后网表和报告均有独立哈希，可核查硬件实现输入与产物；修复后的后续阶段会额外记录 wrapper 前后哈希。

该问题不等于 IP/HLS 内容被替换：本轮另外核对当前 8 份 HLS/测试台源文件与综合快照哈希，均一致；构建目录内 Tcl 和 IP 也有独立记录。

限制：本次已完成 implementation 不为补记 wrapper 哈希而重复跑 Vivado；签核材料会保留“历史 wrapper 哈希未记录”说明。

## 已核实的数据依据

本轮使用 Python 标准库以 `-B` 运行只读包审计/内存规划和报告门禁检查；没有编译或执行 `test_frame.exe`，没有新启动 HLS 或 Vivado。

| 项目 | 实际复核结果 |
|---|---|
| 冻结 bundle | `5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710` |
| 参数 | 1,933,120 B、243 tensors；blob、逐参数与图哈希校验通过 |
| 图结构 | 320 节点：105 conv、6 deconv、93 ReLU、68 cat、27 add、20 mulcoef、1 input |
| 格式 | signed INT16；输入 F14、输出 F13；逐节点尺度来自图 |
| 累加界 | 使用实际量化权重/bias 重算为 286,417,368,313，至少 signed 40 位；INT32 不安全，HLS 48 位有依据 |
| tile 缓存 | 当前图计算的最大需求 36,288 个元素，小于声明的 41,472 个槽 |
| 当前源码与综合版本 | `frame_top`、`conv_tile_top`、`elementwise_top` 的 cpp/hpp，加 `tb_frame.cpp`、`generated_model.hpp`，8 份哈希均一致 |
| 实际 RTL 捕获复查 | 4×4 的 rtl05/rtl06 和 5×7 的 odd02：三组冷暖最终输出与 Golden 哈希相同；各组实际暖态 320 份节点文件匹配；原 simulation.log 哈希未变 |

450 MiB scratch 是由图及生存期规划得出的容量，不是已经从板端成功分配的连续内存。100 MHz 是系统配置，仿真周期预算不是实测时延；HLS 7.300 ns 是综合估算，不是 routed signoff。新模型没有已测 34 FPS 结果。

物理指针合法性、跨 buffer 别名、可信独占 DMA 内存仍由调用方按合同保证。当前硬件没有 AXI 错误诊断及独立 abort/drain/reset 恢复。这些限制在 `docs/frame_interface.md` 中已明示，不能当作已经实现的功能。

## 实际运行失误与当前状态

- 历史 `grid_system01` 误用了旧 tile 系统来源，已被 signed-DSP 保护阻止；当前 `grid_system02` 已改用流水旧核来源，保留失败记录，未把旧目录作为交付依据。
- 旧 33×47 测试的全局 watchdog 比单帧预算更短，已修正测试台并另启 `_02`；旧 `_01` 保持失败/中止。不能因厂商仿真器返回 0 就报告完整回归通过。
- 历史 `xelab -O 3`、重复 glbl、复位锁定常量遗漏等运行/适配错误已在跟进文档中记录。旧 odd02 报告的 `case` 名误写 size_4x4，但实际 shape=5×7、原始捕获及 Golden 复核匹配；标签修正不覆盖历史结果。
- 原生 EXE 曾被安全软件拦截；后来有实际运行日志和输出，保留原失败与 recovered 记录。不能据此断言告警误报或程序绝对安全，本轮没有重试 EXE 或改动安全设置。
- Routed Vivado 报告已完整生成并经新 signoff parser 实测通过，见上文的 slack、时钟、检查计数和 route 数量。
- 33×47 `_02` 在修复前启动，目前仍在跑，最新观察约 145,000,000 周期，首帧已过半。它不是修复后门禁证据；待其结束后需按新 harness 重跑 33×47。
- 33×47 新回归、完整系统 post-route 新核/旧核回归和 bit/XSA 导出尚未完成。本地仍只有 pre-implementation XSA；没有新的最终 bit/XSA，也没有真板验证。

## 本轮变更、验证和 Git 状态

- 修改：新增 `tools/ddr_fixture.py` 和 `tools/release_gates.py`；更新 `tools/frame_rtl_trial.py`、`tools/build_grid_system.py`、`tools/continue_grid_system.py`、`system/frame_axi_test.sv`、`system/export.tcl` 与本报告。
- 原因：消除模拟 DDR 共享地址重叠，阻止缺少跨 tile 数值证据或 routed timing signoff 的导出，并保存执行源码身份。
- 实际执行：Python 语法编译；验证真实 routed timing/route 报告通过；负对照确认负 slack 和未完全布线会被拒绝；以冻结图重算 4×4、33×47、675×1280、720×1280 地址并验证不重叠；确认 4×4 证据会被 33×47 门禁拒绝。
- 未执行：修复后完整 33×47 RTL 回归、post-route 新核/旧核回归、bitstream/XSA、板测。没有重跑 HLS 或 implementation，没有运行 `test_frame.exe`，没有 Git 写操作。
- 当前 `griddehaze_fpga` 没有 `.git`；只读参考仓库处于 `weather_fpga_integration` 分支，工作区干净。
- 建议 Commit Message：`fix(griddehaze): gate export on verified DDR and RTL evidence`。本轮未暂存、提交、推送或切换分支，等待用户审查。
