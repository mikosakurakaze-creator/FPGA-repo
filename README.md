# 天气图像恢复 FPGA 集成项目

> 2026-10-23：已收到 KV260 的 8×8、task=0 真板不匹配证据（171/192 标量）。`k26_weather_v2_20261022` 保留为可追溯的故障版本，当前暂停作为通过验收的上板版本使用。诊断进展见 [真板不匹配调查](docs/board_mismatch_20261023.md)。原时序和仿真通过记录不代表真板数值正确。

本轮已定位并修正实现阶段的DSP截断/符号扩展变化：[2026-10-23修正候选](board/releases/k26_weather_v2_signedfix_20261023/README.md) 已重新布局布线，实际新routed网表四帧task=0、0、1、0全部逐值通过；100 MHz setup +0.638 ns、hold +0.010 ns。包含原生Vivado导出的新bit/XSA和匹配BIN，仍需真板复测。代码中未经确认的假设、已补的检查与未覆盖边界见 [代码假设自审](docs/implementation_assumptions_audit_20261023.md)。

当前验证结果和构建文件位置见 [流水版修正报告](docs/stream_revision_20261020.md)，更新日期为 2026-10-21。

上板硬件文件已集中发布到 [K26 硬件目录](board/releases/k26_weather_v2_20261022/README.md)（2026-10-22）：包含匹配的 bit、bit.bin、XSA、HWH、PS 初始化文件、生成驱动和布线后报告。该目录是经用户授权纳入 Git 的硬件输出例外；原文件保留以供故障复现。2026-10-23 的板端最小数值测试失败，当前不能把该版本视为已通过上板验收。

本目录由 B 侧独立集成工作目录复制而来，已于 2026-10-21 绑定到 `https://github.com/mikosakurakaze-creator/FPGA-repo.git` 的 `weather_fpga_integration` 分支，跟踪 `origin/weather_fpga_integration`。绑定时保留了已有天气项目文件，并补齐远端基线文件；原 `competing/weather_fpga_integration` 仍独立保留。绑定操作没有暂存、提交或推送天气修改。此前报告中的 Git 状态指对应操作当时的状态，当前以 Git 记录为准，详见 [Git 绑定记录](docs/git_binding_20261021.md)。

## 当前实现

- `experiments/stream_frame/src/weather_frame.cpp` 中的 `weather_frame_top` 包含两套固定 C8 模型：`task=0` 去雨，`task=1` 去雾。
- 整帧输入输出采用 RGB NCHW、有符号 INT16 Q14，支持 `H<=720`、`W<=1280`，使用独立 DDR 缓冲区，无外部特征工作区或 AXI Stream 接口。
- 整帧 DATAFLOW 让 stem、五个空间残差块和 tail 同时工作。每个空间阶段使用两行缓存和一个 3×3 窗口。按平面组织的行读写器每帧只读一次输入、写一次输出，无 tile halo 重复读取。
- 组合系统沿用原低照度 CNN/Bilinear/Curve 和 PS 配置。天气核控制基址为 `0xA0030000`，输入共享 HP0、输出共享 HP3；首次上板采用串行、互斥的工作模式。
- 天气核直接输出增强 RGB，不进入低照度 `A_low -> Bilinear -> Curve` 参数图路径。

## 已实际完成的验证

- `work/stream_host02`：两任务合计 60 个官方 Golden 节点、边界、负对照，以及 720x1272/720x1280 整帧主机比较全部通过。
- `work/stream02`：两任务 Vitis 2025.2 CSim、HLS 综合、8x8 RTL 联合仿真和 IP 导出通过。两任务每次 8x8 vendor RTL 均为 1,343 拍，六个空间循环实际达到 II=1。
- `work/stream_sequence01`：连续五次 vendor RTL 调用通过，包含任务和尺寸切换。
- `work/stream_rtl01`：九次独立 AXI-Lite/DDR RTL 调用通过，包括七次带停顿的小图/尺寸切换和两张完整 720x1280 图像；能够正确拒绝被篡改 1 LSB 的 Golden。
- 两任务完整 720p 在文档规定的独立 DDR 模型下均为 3,009,677 拍，按 100 MHz 折算为 30.09677 ms，低于 3,333,333 拍预算。该结果属于仿真周期证据，不是真板帧率。
- `work/stream_driver01`：C11 控制器在模拟 MMIO/DMA 下调用真实新 C++ 核，验证通过。
- `D:/weather_builds/stream_system01`：组合系统 Vivado 综合和布局布线通过。100 MHz 下 WNS +1.018 ns、WHS +0.010 ns、WPWS +3.500 ns；169,908 条需布线网络全部完成。布线后资源占用：LUT 63.49%、FF 33.96%、BRAM 50.00%、URAM 73.44%、DSP 77.00%。
- 新 bitstream 和含 bit 的 XSA 已生成，最终 32 项接口/编译 RTL/ROM/XSA 核查全部通过。`evidence/stream_system_verification_20261021.json` 记录最终文件与源码、测试、构建证据的对应身份。布线后 DRC 没有 Error/Critical Warning，保留 832 条非阻断 Warning。

当前硬件构建位于 `D:/weather_builds/stream_system01/`，本地副本为 `work/system_stream01/`，包含 bit/XSA、工程、布线后 DCP/报告、IP 输入和构建记录。按用户要求不另做交付 ZIP。Embedded 工具链和上板待办见 [上板联调说明](docs/board_bringup.md)。

历史 `frame04/system02` 和 `build/weather_system_k26_v1_1/` 保存串行 tile/层调度功能基线及详细 HLS 报告。该基线在 100 MHz 下无法达到 720p30，其时序、bitstream 和报告不能替代新流水核的验证。

更早的 `frame03/system01` 候选已因复现窄行 DDR 写回死锁而取消交付资格，详见 [故障与回归证据](docs/ddr_writeback_deadlock.md)。

真板 8×8、task=0 数值测试已执行且失败，定位见 [调查记录](docs/board_mismatch_20261023.md)，验证与代码假设审查见 [代码审查](docs/implementation_assumptions_audit_20261023.md)。持续帧率、摄像头和显示尚未验收。100 MHz 时序通过不等于已达到 720p30。A53 standalone 后端和最小测试源码已提供，本机尚未生成 ELF。仓库内 Linux DMA 后端未交付；本次板端驱动由下游提供，已纳入静态审查。

## 文档导航

- [当前报告与修改清单](docs/stream_revision_20261020.md)
- [历史串行基线集成记录](docs/system_integration_20261020.md)
- [整帧 ABI v2 接口合同](docs/weather_frame_v2_contract.md)
- [上板联调说明](docs/board_bringup.md)
- [待完成事项与验收条件](docs/open_items.md)
- [PS 控制器与平台后端](deployment/README.md)
- [当前整帧核源码与复现入口](experiments/stream_frame/README.md)
- [Vitis 启动故障修复与桌面启动器](docs/vitis_windows_startup.md)
- [A 组交付核查及证据范围](docs/a_compute_handoff.md)
- [性能预算](docs/performance_optimization.md)

## A 组原始输入

A 组交付解压目录只读保存在 `C:/Users/wzh16/Desktop/competing/weather A/weather_A_C8_delivery/`。清单内 3,179 份文件的大小和 SHA-256 全部一致，143 项 A 组审查检查通过。最外层交付 ZIP 本机缺失，因此没有重新计算该归档的哈希。

`ip_archives/`、`ip_repo/derain_top` 和 `ip_repo/dehaze_top` 保存原始 A 组 ABI v1 tile IP。它们用于参考或回退，当前组合 v2 系统没有实例化这两个旧 IP。v1 使用 input/output/scratch，两个任务各有固定 IP，tile 最大为 140x140；`deployment/weather_tiled.c` 是经主机验证的 CPU 数据收集/裁剪回写路径。

`work/`、`build/`、日志、缓存、数据和运行输出均为本地产物。厂商工具通过 `tools/run_windows_desktop.py` 启动，每次使用新的输出目录；这些产物和数据集不自动上传。

当前副本位于 `C:/Users/wzh16/Desktop/github clone/weather_fpga_integration/`，没有复制历史 `build/` 交付包。历史验证日志中的绝对路径用于记录原执行位置，重新构建应使用新输出路径。`work/` 和完整硬件工程、缓存继续由 Git 忽略；本次上板发布目录中的指定输出文件已明确放行。
