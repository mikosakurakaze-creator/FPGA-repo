# Weather 审查问题修正记录

更新日期：2026-10-21。当前正式流水实现为 `stream02/stream_system01`，下面将实际执行、历史基线和待上板事项分别说明。

## 范围与版本

本轮修正三个问题：旧串行核不满足 720p30、交付包遗漏详细 HLS 报告、性能文档过期。所有文件位于独立非 Git 工作目录，旧 `frame04/system02` 和 `build/weather_system_k26_v1` 保留，不修改队友源码或 Git 分支。

`build/weather_system_k26_v1_1` 是旧功能硬件的报告补充版：bit/XSA 身份不变，增加两任务逐函数 `csynth.xml/rpt` 与 co-sim 报告，共 812 份 payload，重新生成 manifest、ZIP 与 SHA-256。该版仍不满足 720p30，不与新流水核混称。

## 新流水计算架构

新候选在 `experiments/stream_frame`。外部继续使用 signed16 Q14、RGB NCHW、两路 DDR 和原 AXI-Lite CSR。模型、参数、层数、节点 RNE/饱和顺序均保持 A 交付的整数规则。

内部使用读行 burst → RGB 重排 → stem → 五个独立残差块 → tail → NCHW 重排 → 写行 burst 的 DATAFLOW。每个空间阶段持有两行特征缓存和 3×3 窗口；原 RGB 随中心像素向后传递，避免在尾层设置整帧大小的旁路 FIFO。边缘 padding 在每个空间层独立执行。行缓存利用首行 padding 覆写旧状态，支持任务和尺寸变化而不要求中途 reset。

输入输出的三个颜色 FIFO 各 2048 个 INT16，覆盖最大 1280 像素行。普通主机 C++ 用顺序队列验证数值，不能证明有限 FIFO 无死锁；实际 RTL 必须验证反压、持续调用、窄图和整帧。

## 当前验证

- `work/stream_host02`：两任务 60 个官方节点、边界、负对照、720×1272/720×1280 全部逐位一致。
- `work/stream_driver01`：C11 控制器、错误路径和真实新核主机集成通过。
- `work/stream01`：首次架构 HLS 探索；发现编译期未选分支的负下标警告和 DATAFLOW 实参表达式提示，已在后续源码中清除，不作为正式交付版本。
- `work/stream02`：两任务 CSim、HLS 综合、8×8 RTL 和 IP 导出通过；两任务 8×8 vendor RTL 都为 1,343 拍。HLS 估算 LUT 78,083、FF 67,203、BRAM18K 95、URAM 36、DSP 822，7.300 ns；六个空间阶段请求/实际 II=1。该估算不是布局布线结果。
- `work/stream_sequence01`：连续五次任务/尺寸切换的 vendor RTL 通过。
- `work/stream_rtl01`：九次独立 AXI-Lite/DDR RTL 通过，包括七次反压用例、两任务完整 720×1280；1-LSB 负对照正确拒绝错误 Golden。
- 两任务完整帧各为 **3,009,677 拍**，低于 3,333,333 拍预算；按 100 MHz 折算 **30.09677 ms/帧**。每帧各读、写 1,382,400 个 32-bit beat，实际数据流量 11,059,200 字节，符合只读写各一次的设计。余量约 3.237 ms/帧，尚需板测 DDR 仲裁、PS 缓存、采集显示开销。
- `D:/weather_builds/stream_system01`：25 项预实现接口核查通过；最终导出 IP 的 254 份 RTL/ROM 与系统输入完全一致；组合系统综合及布局布线通过。任何旧系统的时序或 bit 不能替代新版本验证。

最终离线核验另区分两套工具输入：vendor 连续调用 co-sim 使用的 253 份原始综合 RTL/ROM 与 `stream02` 完全相同；IP 导出后增加仿真用死锁检测模块，并在 top 的 `synthesis translate_off` 段加入 detector include。254 份导出 RTL/ROM 与独立 AXI RTL 测试和系统输入完全相同。核验脚本原先把 vendor 综合输入与导出后文件直接比较，会误拒绝这处检测代码差异；现改为分别与实际输入逐字节、逐文件集合比较，不忽略算术 RTL 或 ROM 差异。

组合系统综合资源为 LUT 79,393、FF 82,113、BRAM 35×36K + 74×18K（72 个 36K tile 等效）、URAM 47、DSP 961。Vivado 对天气核 OOC 综合得到 LUT 36,720、FF 32,352、BRAM 7 tile、URAM 29、DSP 815。不同阶段会执行常量折叠、资源优化和层次处理，HLS 估算与最终实现数值不能相加或混用。

## 新系统布局布线结果

组合系统为 K26 `xck26-sfvc784-2LV-c`，保留低照度 CNN/Bilinear/Curve、原 PS 配置与各控制地址，新天气核使用 HP0 读、HP3 写。最终 post-route 结果如下。

| 指标 | 实际结果 |
|---|---:|
| PL 名义时钟 | 100 MHz / 10 ns |
| Setup WNS / TNS / 失败端点 | +1.018 ns / 0 / 0 |
| Hold WHS / THS / 失败端点 | +0.010 ns / 0 / 0 |
| Pulse width WPWS / 失败端点 | +3.500 ns / 0 |
| check_timing | 12 类均为 0 |
| 完成布线 / 需要布线网络 | 169,908 / 169,908 |
| 布线错误 | 0 |
| LUT | 74,354 / 117,120（63.49%） |
| FF | 79,552 / 234,240（33.96%） |
| BRAM tile | 72 / 144（50.00%） |
| URAM | 47 / 64（73.44%） |
| DSP | 961 / 1,248（77.00%） |

DRC 没有 Error 或 Critical Warning，但有 832 条非阻断 Warning：DPIP-2 393、DPOP-3 189、DPOP-4 231、DPREG-7 18、RTSTAT-10 1。主要为 DSP 输入/输出寄存建议及无负载网络，原始报告完整保留；不能称作零警告。未关闭 DRC 或修改其严重级别。DSP 和 URAM 余量已有限，后续并行增加功能需要重新评估。

首次组合综合在 Curve OOC 的 Tcl 扩展加载阶段报 `Could not open 'C' for writing`，尚未进入该核综合。Curve IP 和 XCI 与此前成功基线完全一致；重新使用构建脚本重置失败子运行后，在相同输入上 OOC 和顶层综合通过。没有修改 Curve 算法或 IP，不能据此宣称已确定该工具启动错误的根因。

新增整帧 RTL 性能门禁为同一实例两种任务各一张 720×1280，分别与原 A 核独立分块参考比较，100 MHz 下每次不超过 3,333,333 拍。性能用例使用不主动注入停顿的独立 DDR 模型；此前七次小图/变尺寸用例保留总线反压。即使该门禁通过，也只是规定模型下的计算/DDR 周期证据，真实视频吞吐仍需板测。

完整帧模型每两拍最多返回一个 32-bit 读 beat、每方向一个在途 burst。相当于模型下约 33.23 FPS；这不是 PS DDR 控制器、全系统仲裁或连续视频的实测值。

## 构建文件与本地整理

用户明确要求不再制作交付包，因此本轮不执行新流水版的交付收集/ZIP 归档。旧 `build/` 中已经存在的历史包保留。当前 `stream_system01` 的 bitstream 和含 bit 的 XSA 已成功生成，最终 32 项 ABI/编译 RTL/ROM/XSA 核查全部通过，XSA 内嵌 bit 与外部 bit 完全一致。

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `weather_system.bit` | 7,797,826 | `2ab43415c981ef8a3d8f46a4e211befc61fc98766614eed49bd459fd7148a4c8` |
| `weather_system.xsa` | 4,581,236 | `b16b6aa93ca9850e767aefa5db2283ae9e88f6c77ef2b6f251ef02d83b0794a5` |

最终交叉核验记录为 `evidence/stream_system_verification_20261021.json`，295 项全部通过：冻结构建输入、四阶段实际 Tcl/日志、当前主机/HLS/控制器/测试源码身份、原始 A fixture、vendor 与独立 RTL 的文件身份、双任务完整帧周期、完整时序/布线/DRC 与 32 项接口核验；其中 252 项是逐文件功能 RTL/ROM 比较，不能把此检查项总数理解成 295 次独立硬件实验。Python 19 个脚本语法检查通过。完整 vendor/RTL 仿真已执行过，此次最终整理仅重新核对其证据和身份，没有重复运行整帧仿真。

完整工作文件夹的复制目标为 `C:/Users/wzh16/Desktop/github clone/weather_fpga_integration`。不复制旧 `build/` 交付包；源码、文档、主机/HLS/RTL 原始记录保留，当前完整 Vivado 构建另放 `work/system_stream01/`。复制完成时为新独立目录；后续按用户明确要求绑定现有同名远端分支，见 [Git 绑定记录](git_binding_20261021.md)。根 `.gitignore` 忽略 `work/`、`build/`、数据、缓存和日志，便于后续用户自行选择需提交的源码与文档。复制结果以旁边的 `weather_fpga_integration_copy_verification.json` 为准，记录绑定前逐文件 SHA-256 和大小，不把复制等同于 Git 提交。

生成报告中的绝对路径记录原执行位置；复制不会重写历史日志或 manifest。需要重建时用当前 `system_seed.bd`、IP 与源码，在新空目录运行构建脚本。原始 A 参考包仍保留在 `competing/weather A`，没有更改或自动上传。

## PS 工具链阻塞

已确认本机 `D:/vivado/2025.2/gnu` 只有 MicroBlaze/RISC-V，无 AArch64 编译器；Vitis 标记为 HLS 安装。对已保存 AMD 安装器执行只读 `--help`，实际返回 “Administrative permissions are not available”。因此当前会话不能补装 Embedded SDK，也没有生成 ELF 或连接真板。

本机已有安装入口 `D:/vivado/.xinstall/2025.2/bin/xsetup.bat`，原始安装器在 Downloads。需要从管理员环境使用 AMD 安装器补齐相同 2025.2 版本的 Vitis Embedded/AArch64 工具，再执行 `docs/board_bringup.md` 中的 BSP/ELF 命令。未绕过安装器权限，也未修改现有厂商安装。

## 修改清单与 Git

| 文件组 | 修改原因 |
|---|---|
| `experiments/stream_frame/` | 独立新核、主机/HLS 验证入口与冻结 A 参数 |
| `tools/package_release.py` | 要求并收集详细 HLS/RTL 报告；流水版要求双任务完整帧周期证据；vendor 回归与原始综合输入严格比较，独立 AXI 回归与导出 IP 严格比较。本轮依用户要求不执行新包收集 |
| `tools/archive_release.py` | 校验全部 payload 后生成新 ZIP 和 SHA-256，不覆盖既有归档 |
| `tools/run_sequence_cosim.py` | 指定不同实验核，保持连续任务/尺寸回归 |
| `tools/run_rtl_memory_test.py`、`system/rtl_memory_test.sv`、`system/make_rtl_vectors.cpp` | 保留原七次有停顿测试，增加两任务 720p 原参考输出与周期门禁 |
| `deployment/tests/verify_driver.py` | 选择新核执行同一控制器测试，不将旧核报告当作新核验证 |
| `README.md`、`docs/open_items.md`、`docs/performance_optimization.md`、本文 | 清理过期状态，明确旧串行核的计算瓶颈、新核实测证据及边界 |
| `docs/weather_frame_v2_contract.md`、`deployment/README.md`、`experiments/stream_frame/README.md` | 同步当前核、验证记录、接口和模型下周期，不改外部 ABI |
| `docs/board_bringup.md`、`docs/system_integration_20261020.md` | 联调入口改用新 XSA，历史记录增加明确指向当前版本的说明 |
| `evidence/stream_system_verification_20261021.json` | 固定最终实际构建、测试和 bit/XSA 身份，便于后续核查 |

本工作目录不是 Git 仓库，未执行 add/commit/push、切换或修改成员分支。建议 Commit Message：`feat: pipeline weather frames and verify K26 system implementation`。
