# KV260 Fixed16 V1：Vivado 系统综合

## 目标、基线与范围

从磁盘重新打开已保存的 `system.bd`，核对两只 Fixed16 HLS IP、PS、复位、AXI 互连及 100 MHz 时钟；生成完整 Block Design output products 和 Vivado 管理的 HDL wrapper；运行完整工程 Vivado Synthesis，并记录系统资源、综合后时序及警告。

本次只验证系统**可综合**及综合后的资源/时序估计。没有修改 Bilinear/Curve 算法、Fixed16 格式或 HLS IP 包；没有运行 Implementation、Bitstream、PS 软件、AXI DDR 事务或板上测试，也没有连接 CNN 或做性能优化。

| 项目 | 实际值 |
| --- | --- |
| Git 分支 / HEAD | `codex/curve-fp32-baseline` / `5b1f54a380e5bd1e2cf0b892c303a94a089a47af` |
| Vivado | 2025.2，SW Build 6299465，IP Build 6300035 |
| Board / part | Kria KV260 Vision AI Starter Kit SOM / `xck26-sfvc784-2LV-c` |
| 工程 | `E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr` |
| BD | `E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd` |
| HLS IP repositories | `E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip`；`E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip` |
| HLS 数值格式 | 外部 `ap_fixed<16,2,AP_RND,AP_SAT>`；本次未重新做数值验证 |

## 磁盘设计核对与拓扑

独立 batch Vivado 重新打开工程与磁盘上的 `system.bd`，核对到 `bilinear_fixed16_buffered_0`、`curve_image_fixed16_0`、`axi_control`、`axi_ddr`、`rst_ps_100m`、`zynq_ultra_ps_e_0` 均存在。PS `M_AXI_HPM0_FPD=1`、`S_AXI_HP0_FPD=1`、`M_AXI_HPM1_FPD=0`，`pl_clk0=100 MHz`；复位配置为 `ACTIVE_LOW` / `C_EXT_RESET_HIGH=0`。原保存设计 `Validate Design=PASS`，本次 `validate_bd_design` 也成功。

控制路径为 PS HPM0 → `axi_control`（1 SI / 2 MI）→ Bilinear/Curve 的 `s_axi_control`。数据路径为 Bilinear 的输入、输出和 Curve 的输入、参数、输出这 5 路 `m_axi` → `axi_ddr`（5 SI / 1 MI）→ PS HP0 → DDR。`pl_clk0` 给 HLS、SmartConnect 和 PS AXI 端口供 100 MHz；PS `pl_resetn0` 经 `rst_ps_100m` 分别生成互连与 HLS 的低有效复位。两 IP 之间经 DDR 中转，尚无 PS 软件配置缓冲区地址或启动顺序。

## Output products 与 HDL wrapper

对 `system.bd` 实际执行 `generate_target all`，**PASS**；两只外部 HLS IP VLNV 各解析到一个 IP。IP 状态报告显示两只均为 `Up-to-date / No changes required`，没有 missing/locked IP；常量 IP `system_const_locked_0` 显示 `Up-to-date (discontinued)`，本次未迁移。生成了 BD 的综合/仿真产物及各 IP OOC 工件。首次运行时报告目录尚不存在，Vivado 对指定日志/日志簿报 `[Common 17-183] Failed to open handle`；脚本内随即建目录并完成生成。随后在已存在的目录重新执行，命令退出码为 0、输出产物与 IP 状态均确认正常。第二次生成因产物已是最新而没有重新构建。

使用 `make_wrapper -top -add` 建立 Vivado 管理的 wrapper：

`E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.gen/sources_1/bd/system/hdl/system_wrapper.v`

工程 `sources_1` 的 synthesis top 是 `system_wrapper`。Wrapper 实际为 `module system_wrapper (); system system_i (); endmodule`，没有未连接的外部顶层端口；PS DDR/MIO 等属于 PS 内部接口。综合资源表的 Black Boxes 栏为空，未发现 black box。

## 实际运行命令和产物

三个批处理命令均从 `E:\HLS` 目录执行，并通过 `E:\Xilinx\2025.2\data\settings64.bat` 加载环境。脚本分别执行磁盘核对、产物生成/ wrapper、`launch_runs synth_1 -jobs 4` / `wait_on_run synth_1` / `open_run synth_1`、综合后报告，以及只读的时序补查。实际命令格式如下（`SCRIPT` 和 `LOG` 依次取下表值）：

```cmd
cmd /c "set PROCESSOR_ARCHITECTURE=AMD64&& call E:\Xilinx\2025.2\data\settings64.bat && call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\SCRIPT -log E:\HLS\vivado_fixed16_synthesis_v1\LOG.log -journal E:\HLS\vivado_fixed16_synthesis_v1\LOG.jou -notrace"
```

| 阶段 | `SCRIPT` | `LOG` | 实际结果 |
| --- | --- | --- | --- |
| 磁盘预检查 | `vivado_fixed16_verify.tcl` | `E:/HLS/vivado_fixed16_synth_preflight.log`（独立 log 路径） | 保存设计检查和 Validate PASS |
| Output products + wrapper | `vivado_fixed16_output_products_v1.tcl` | `output_products` | PASS；首次日志目录问题后重跑成功 |
| 工程综合 + 报告 | `vivado_fixed16_synthesis_v1.tcl` | `synthesis_driver` | `synth_design Complete!`，进度 `100%` |
| 综合后时序补查 | `vivado_fixed16_timing_audit_v1.tcl` | `timing_audit` | PASS，未重跑综合 |

预检查调用的脚本路径是 `E:/github/-/fpga/scripts/vivado_fixed16_verify.tcl`；其他三个脚本亦在该目录。本次新增的三个脚本为 output products、synthesis、timing audit。主结果和原始日志在 `E:/HLS/vivado_fixed16_synthesis_v1/`：`system_utilization.rpt`、`system_utilization_hierarchical.rpt`、`system_timing_summary.rpt`、`system_timing_paths.rpt`、`system_hold_paths.rpt`、`system_check_timing_verbose.rpt`、`system_drc.rpt`、两份 IP 状态报告及 batch 日志。工程 OOC/顶层日志在 `fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.runs/*/runme.log`。

预检查实际使用同一 `cmd /c` 环境和 Vivado 调用方式，`-source E:\github\-\fpga\scripts\vivado_fixed16_verify.tcl -log E:\HLS\vivado_fixed16_synth_preflight.log -journal E:\HLS\vivado_fixed16_synth_preflight.jou -notrace`；其日志路径独立于上表目录。

**Vivado Synthesis PASS**：顶层 `synth_1` 与 Bilinear、Curve、PS、两只 SmartConnect、reset 的 6 个 OOC 综合运行均完成，并生成 DCP。没有启动 implementation run。

## 系统资源

以下来自 Vivado `report_utilization`，是 **post-synthesis** 数值，不是 HLS 单 IP 估计，也不是布局布线后的最终资源。

| 资源 | 已用 | 器件可用 | 利用率 |
| --- | ---: | ---: | ---: |
| CLB LUT | 13,490 | 117,120 | 11.52% |
| LUT as Logic | 11,252 | 117,120 | 9.61% |
| LUT as Memory（含 LUTRAM、SRL） | 2,238 | 57,600 | 3.89% |
| 其中分布式 LUTRAM / SRL | 1,068 / 1,170 | — | — |
| FF | 18,681 | 234,240 | 7.98% |
| RAMB18 | 5 | 288 | 1.74% |
| BRAM tile | 2.5 | 144 | 1.74% |
| RAMB36 | 0 | 144 | 0% |
| URAM | 0 | 64 | 0% |
| DSP | 57 | 1,248 | 4.57% |

| 综合 hierarchy | LUT | FF | LUTRAM | SRL | RAMB18 | DSP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Bilinear Fixed16 Buffered | 4,173 | 4,912 | 0 | 359 | 3 | 33 |
| Curve Fixed16 | 3,207 | 4,641 | 0 | 753 | 2 | 24 |
| `axi_control` | 958 | 1,024 | 0 | 1 | 0 | 0 |
| `axi_ddr` | 4,869 | 8,064 | 1,068 | 56 | 0 | 0 |
| `rst_ps_100m` | 19 | 40 | 0 | 1 | 0 | 0 |
| PS / constant / remaining glue | 264 | 0 | 0 | 0 | 0 | 0 |
| **全系统** | **13,490** | **18,681** | **1,068** | **1,170** | **5** | **57** |

上表底层行是 Vivado hierarchy 的直接实例归属；“PS / constant / remaining glue” 是总数减去列出的五项，不代表 PS 硬核本身消耗 264 个 PL LUT。`axi_ddr` 的 1,068 LUTRAM 和 8,064 FF 是本次系统资源中很显著的互连开销。

### 与既有 HLS 单 IP 估计对照

| IP | HLS DSP / LUT / FF / BRAM18 | 本次 Vivado hierarchy DSP / LUT / FF / RAMB18 |
| --- | --- | --- |
| Curve Fixed16 | 24 / 4,902 / 3,916 / 4 | 24 / 3,207 / 4,641 / 2 |
| Bilinear Fixed16 Buffered | 33 / 7,985 / 5,470 / 4 | 33 / 4,173 / 4,912 / 3 |

两种报告的综合范围、映射及资源口径不同，不能把 HLS 数值相加当作系统预测。此次 Vivado 两核 DSP 与 HLS 估计一致；Vivado 中两核 LUT 均较少，Curve FF 较多，BRAM18 均较少。系统还包含两只 SmartConnect、PS reset 和 glue logic，且 Vivado 会优化未使用逻辑。资源变化不代表算法或精度变化；没有重新做数值测试。

## 时钟与 post-synthesis timing

`clk_pl_0` 已识别为 **10.000 ns / 100.000 MHz**，全部 64,006 个已报告端点属于这个时钟域。时钟报告还列出 10 ns 的 `clk_pl_1`，但实际 Intra Clock Table 只有 `clk_pl_0`；`pl_clk1` 在顶层综合日志中报告未连接。

| 指标 | 实际结果 |
| --- | ---: |
| Setup WNS / TNS | +2.613 ns / 0.000 ns |
| Setup failing endpoints | 0 / 64,006 |
| Hold WHS / THS | **−0.093 ns / −688.756 ns** |
| Hold failing endpoints | **22,097 / 64,006** |
| Pulse-width WPWS / TPWS | +3.500 ns / 0.000 ns |

Vivado 的总体判断是 **`Timing constraints are not met`**：setup 满足 100 MHz 的综合网表估计，hold 尚未满足。Worst setup path 在 Bilinear 计算逻辑的寄存器 → DSP 输入，slack +2.613 ns。Worst hold path 在 `axi_ddr` 的 XPM FIFO 写地址寄存器 → 分布式 RAM 写地址，slack −0.093 ns；该路径显示 `unplaced` 时钟/数据网络。这是**未放置、未布线的综合后估计**，不能当作最终时序签核，也不能断言 Implementation 后一定会失败或一定修复。

`check_timing -verbose` 显示 8 个 `no_clock` 引脚，全部属于 PS8 未用于本 PL 数据路径的 EMIO MDIO、SDIO、SPI 时钟输出。`unconstrained_internal_endpoints=0`、缺失 I/O delay=0、multiple clock=0、generated clock 问题=0、combinational loops=0、latch loops=0。没有在当前已分析 PL 处理路径上发现未约束端点。实现前仍需复查真实约束、布线后时序及这些 PS EMIO 告警的适用性。

## Warning / error / DRC 复查

| 来源 | 实际现象 | 本阶段判断 |
| --- | --- | --- |
| 上次 BD `[BD 41-237]` | PS HP0 `AWUSER/ARUSER_WIDTH=1` 与 `axi_ddr/M00_AXI` USER width 0；本次产物/综合日志未再次打印 | 未升级为综合 error；AXI DDR 事务仍未实测，不能据此证明 sideband 兼容性 |
| 首次 output products | 指定日志目录不存在导致 `[Common 17-183]` 打开日志/日志簿失败 | 已建目录重跑成功；产物状态及 IP 状态正常 |
| BD 生成 | HLS 2 bit `AWLOCK/ARLOCK` 与 SmartConnect 1 bit 存在 `[BD 41-2384]` 宽度警告，低位相连；HLS 生成 RTL 对 LOCK 驱动为常量零 | 非独占访问场景下预期无功能影响；未做事务级验证 |
| IP 状态 | 两只 HLS IP 均 `Up-to-date`；`const_locked` 标为 discontinued；打开工程建议将 utility IP 迁到 inline HDL | 没有 locked/missing HLS IP；本次不改既有 BD |
| SmartConnect 生成/综合 | 曾有 `[IP_Flow 19-5611]` 两个 PS AXI 口无法找到关联 reset，工具创建默认关联；OOC log 中 reset 模块部分未用输出、`aresetn_out` 无 driver/被裁剪等 warning | 当前全系统 reset 接线通过 Validate 且综合成功；仍需后续实现或系统验证确认启动/复位行为 |
| 顶层综合 | 顶层 `runme.log` 中有 99 行 `WARNING:`，主要为 `Synth 8-7071/8-7023` 的未连接端口/连接数不匹配，涉及 HLS 只读输入的写通道、只写输出的读通道、可选 AXI sideband、reset 备用输出、HLS interrupt、PS `pl_clk1` 等；Vivado `synth_design` 结束摘要另显示 `0 errors, 0 critical warnings, 0 warnings` | 两个计数口径不一致，故保留原始日志及分类；与接口方向及未使用可选端口相符，但必须 AXI 通道仍需事务级测试 |
| Curve OOC 启动 | `runme.log` 行 15 有孤立的 `ERROR: [Common 17-1257] Failed to create directory 'C'.` | 原文保留；后续 OOC `synth_design` 完成、生成 DCP，顶层也完成。可能与 Windows 路径初始化有关，但未证实根因；没有修改核心或掩盖该日志 |
| 板卡库扫描 | 许多与目标 KV260 无关的 `[Board 49-26]` 无法加入其他 board part | 目标 KV260 part 成功打开且综合；无目标板缺失证据 |
| Post-synthesis DRC | **121 条 Warning**：DPIP-2 27、DPOP-3 45、DPOP-4 49，均为 DSP 输入/输出/乘法寄存器 pipeline 建议 | 无 Critical DRC；本阶段不改性能 pragma 或算法 |

本次综合资源表无 black box，FF 中 latch=0，`check_timing` 无组合环。检索主综合日志未发现 multiple-driver、CDC 或新的关键 AXI error；该结论仅限本次已运行的综合检查，未运行专门的 CDC 分析、RTL 仿真或 DDR 总线验证。OOC SmartConnect 还出现未使用 RAM/FIFO 被裁剪、局部约束提示；最终 hierarchy 保留了完整的控制/数据互连。

## 文件、Git 状态与结论

本次新增：

- `fpga/scripts/vivado_fixed16_output_products_v1.tcl`：核对磁盘 BD、生成产物与 managed wrapper。
- `fpga/scripts/vivado_fixed16_synthesis_v1.tcl`：只运行工程综合并输出系统资源、时序、DRC。
- `fpga/scripts/vivado_fixed16_timing_audit_v1.tcl`：对已综合 checkpoint 补查 hold 关键路径和无时钟引脚。
- `fpga/reports/vivado_fixed16_synthesis_v1.md`：本报告。
- `fpga/vivado/fixed16_integration_v1/` 内由 Vivado 管理的 wrapper、output products、OOC 和顶层综合产物；未改 HLS core。`E:/HLS/vivado_fixed16_synthesis_v1/` 是本机日志与报告输出目录。

执行后 Git 仍位于 `codex/curve-fp32-baseline`。上述脚本、报告和 Vivado 工程处于未跟踪状态；先前集成报告与脚本亦仍未跟踪。**未执行 `git add`、commit、push。**

结论：保存的 Fixed16 非 CNN V1 BD、output products、wrapper、Vivado 全系统 synthesis 均已验证成功；系统资源为 13,490 LUT、18,681 FF、5 RAMB18、57 DSP。100 MHz setup 的综合后估计通过，**总体时序未通过，因为 hold 有 22,097 个违例**。这些是未布局布线状态的数据；在 Master 审核后，后续最直接的验证是 Implementation 后重新检查 hold/setup、AXI reset/sideband 和实际 DDR 事务。本次未开展这些后续步骤。
