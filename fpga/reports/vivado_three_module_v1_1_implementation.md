# KV260 三模块 V1.1：Vivado Implementation 与 post-route 审计

日期：2026-09-29。**结论：现有 V1.1 工程以 Vivado 默认策略完成 `opt_design → place_design → phys_opt_design → route_design`；57,441/57,441 条需路由 net 已全部布通，100 MHz post-route setup、hold、pulse width 均满足。综合后的 53,770 个 hold 违例在本次物理实现后降为 0。** 没有生成 bitstream/XSA，也没有运行 PS 软件或板测。

## 1. 目标、版本与受保护基线

本次仅基于已完成的三模块 `synth_1` 启动完整 Vivado Implementation 到 `route_design`，随后从 routed checkpoint 实际运行 timing、utilization、route status、DRC、clock 和 timing constraint 检查。没有重新建立 BD，没有修改 CNN/Bilinear/Curve core、Fixed16/Q14、AXI 四 HP 拓扑、100 MHz 时钟、复位或实施策略。

| 项目 | 实际值 |
|---|---|
| Git branch / HEAD | `codex/curve-fp32-baseline` / `503537cf2e084d22b6e6856b0cb0ffff64f211e0` |
| Vivado | 2025.2，SW Build 6299465，IP Build 6300035 |
| KV260 board / part | `xilinx.com:kv260_som:part0:1.4` / `xck26-sfvc784-2LV-c` |
| V1.1 工程 | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.xpr` |
| Synthesis top | `system_wrapper` |
| Implementation strategy / flow | `Vivado Implementation Defaults` / `Vivado Implementation 2025`；未修改 |
| 固定 CNN 源码提交 | `72b21138ce87a16eb3d3d6163675936b82ceadbc`，未更新 WZH branch HEAD 或更换 IP |
| 旧稳定 V1 | `fpga/vivado/fixed16_integration_v1/`，前后 `git status --short -- fpga/vivado/fixed16_integration_v1` 为空；未打开、重保存或重跑旧工程 |

三颗 IP 仍为 `zero_dce_cnn_top_0`、`bilinear_fixed16_buffered_0`、`curve_image_fixed16_0`。本次脚本先严格确认 `synth_1=synth_design Complete!`、progress `100%`、`system_wrapper.dcp` 存在、board/part/top 正确，再核对保存 BD 的 100 MHz 同网时钟和 PS→Processor System Reset→三颗 HLS/五个 SmartConnect 复位连接，得到 `PREFLIGHT_BD_CLOCK_RESET=PASS`，之后才 launch `impl_1`。

实现前正式 post-synthesis baseline（来自 `fpga/reports/vivado_three_module_v1_1_synthesis.md`）：LUT 29,728、FF 41,819、RAMB36 24、RAMB18 10、BRAM tile 29/144、DSP 76；setup WNS +2.613 ns/TNS 0/fail 0；hold WHS −0.093 ns/THS −1,745.213 ns/fail 53,770；pulse width WPWS +3.500 ns。

## 2. 实际命令、Implementation 阶段与时长

新增 `fpga/scripts/vivado_three_module_v1_1_impl.tcl`，从**已有工程**打开并检查已完成综合，执行 `launch_runs impl_1 -to_step route_design -jobs 4`、`wait_on_run impl_1`，确认 `route_design Complete!` / 100% 和 routed DCP，然后 `open_run impl_1` 生成只读报告。实际在 PowerShell 运行：

```powershell
& E:\HLS\vivado_three_module_v1_1_impl.cmd
```

该外部 `.cmd` 先 `call E:\Xilinx\2025.2\data\settings64.bat`，再 `call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_three_module_v1_1_impl.tcl -log E:\HLS\vivado_three_module_v1_1_impl_driver.log -journal E:\HLS\vivado_three_module_v1_1_impl_driver.jou -notrace`。Run 实际于 **09:59:46 +08:00** 启动，**10:09:23 +08:00** 完成，等待时间 **577 秒（9 分 37 秒）**；`impl_1/runme.log` 实现 worker 的最高报告内存 **4500.949 MB**。随后打开 routed checkpoint 的审计于 10:10:42 完成。状态为 **`impl_1=route_design Complete!`、progress `100%`**；`system_wrapper_routed.dcp` 已存在。没有执行 `write_bitstream`，`impl_1` 目录没有 `.bit`。

| 阶段 | 实际结果 | 工具报告 elapsed / peak memory | Error / Critical Warning / Warning |
|---|---|---:|---|
| `opt_design` | PASS，生成 `system_wrapper_opt.dcp` | 56 s / 3743.879 MB | 累计 0 / 0 / 1 |
| `place_design` | PASS，生成 `system_wrapper_placed.dcp` | 3 min 42 s / 4402.188 MB | 累计 0 / 0 / 1 |
| `phys_opt_design` | PASS，生成 `system_wrapper_physopt.dcp` | 11 s / 4402.188 MB | 累计 0 / 0 / 1 |
| `route_design` | PASS，`Router Completed Successfully`，生成 `system_wrapper_routed.dcp` | 1 min 41 s / 4500.949 MB | 累计 0 / 0 / 1 |

阶段 warning 计数是**同一个 run 的累计计数**，不能把四行相加；唯一 `runme.log` WARNING 为 `[IP_Flow 19-4995]` Windows IP cache 路径较长，未影响 checkpoint 或路由。opt/place/phys_opt/route 无新 Error 或 Critical Warning。`place_design` 期间执行了等价驱动/LUT 组合优化，日志记载“combined 588 existing LUTs and moved 0 existing LUT”；物理优化的 retime 统计为 0。`phys_opt_design` 实际调用，但因 setup 已满足，日志明确“all physical synthesis setup optimizations will be skipped / netlist was not modified”。Placement 为 `rst_ps_100m` 的 `peripheral_aresetn[0]`（9,592 loads）插入 BUFG，并复制一处 reset 驱动；还为 Curve 内部高扇出控制 net（1,398 loads）插入 BUFG。Router 执行了 `Phase 7 Post Hold Fix`；未修改 HLS/RTL 源码。

## 3. Post-route timing：100 MHz 物理收敛

`report_timing_summary`、`report_timing` 均在 **Fully Routed** checkpoint 上实际运行。对照中的 post-synthesis 是未放置网表估计，post-route 是本次布线后结果；端点数可能因物理优化不同。

| 指标 | Post-synthesis | Post-route |
|---|---:|---:|
| Setup WNS | +2.613 ns | **+1.720 ns** |
| Setup TNS | 0.000 ns | **0.000 ns** |
| Setup failing / total endpoints | 0 / 147,675 | **0 / 142,410** |
| Hold WHS | −0.093 ns | **+0.010 ns** |
| Hold THS | −1,745.213 ns | **0.000 ns** |
| Hold failing / total endpoints | 53,770 / 147,675 | **0 / 142,410** |
| Pulse width WPWS / TPWS | +3.500 / 0.000 ns | **+3.500 / 0.000 ns** |
| Pulse width failing / total endpoints | 0 / 49,810 | **0 / 47,303** |
| Vivado 综合/实现时序判断 | `Timing constraints are not met`（hold） | **`All user specified timing constraints are met`** |

**明确回答 hold 问题：V1.1 综合后的 53,770 个 hold violation 已在本次 route 完成后全部消除。** Router 中间值从 WHS −0.118 ns / THS −445.895 ns，改善至 −0.044 ns / −2.681 ns，经过 `Post Hold Fix` 后到 +0.010 ns / 0。这个过程有真实物理路由/修复证据；没有为了消除违例修改算法或架构。100 MHz setup、hold、pulse width 同时满足，标记 **`POST_ROUTE_TIMING_CLEAN`**。这不等于 DDR/FPS/板级功能验证。

### 最差 setup 与 hold 路径

Post-route 最差 setup **仍在 Bilinear 数学核心**，前十条最差 setup 路径也都在 Bilinear；四 HP/11 master 互连、CNN、AXI width converter/FIFO、PS 接口均未成为当前 100 MHz 全系统最差 setup 路径。

| Setup 路径字段 | 实际值 |
|---|---|
| 起点 | `system_i/bilinear_fixed16_buffered_0/inst/zext_ln52_reg_1261_reg[7]/C` |
| 终点 | `system_i/bilinear_fixed16_buffered_0/inst/mul_ln62_reg_1419_reg/DSP_A_B_DATA_INST/A[14]` |
| 时钟 / group | `clk_pl_0` / `clk_pl_0` |
| Requirement / slack | **10.000 ns / +1.720 ns** |
| Data Path Delay | **7.469 ns**，logic **4.562 ns**、route **2.907 ns** |
| Logic Levels | **20**；DSP、CARRY8、LUT 组合 |

Post-route 最差 hold **已经满足**：CNN `gmem_output_m_axi` 的写请求寄存器 `.../data_p1_reg[67]/C` → `cnn_data_sc/s01_entry_pipeline/s01_mmu/.../skid_buffer_reg[1128]/D`，group=`clk_pl_0`，slack **+0.010 ns**；Data Path Delay **0.236 ns**（logic 0.112 ns、route 0.124 ns），logic levels 0。它与综合时最差的 `bilinear_ddr_sc` XPM FIFO 写地址→分布式 RAM 地址路径不同；旧最差 hold 路径不再是违例。CNN→SmartConnect 的新最短路径只有 0.010 ns 正裕量，后续若改动设计须重新实现与审计。

## 4. Routing、Clock 与 Reset 审计

`report_route_status`：**153,617 logical nets**；其中 96,176 不需路由（含 85,618 internally routed、10,558 no loads）；**57,441 routable nets 全部 fully routed**，routing errors **0**。`runme.log` 的最终 Routable Net Status 还明确 **failed nets 0、unrouted nets 0、partially routed nets 0、node overlaps 0**。早期 router intermediate 的未布通/overlap 值不代表最终状态；`Router Completed Successfully` 与最终报告一致。未见独立 antenna/illegal-route error。

`report_clocks`：PS8 `PLCLK[0]`→`clk_pl_0` 为 **10.000 ns / 100 MHz**。报告另列 PS8 `PLCLK[1]` 的 `clk_pl_1`，但 `report_clock_interaction` 只有 `clk_pl_0→clk_pl_0` 一行，classification `Clean / Partial False Path`；无跨时钟数据路径。保存 BD 的 CNN/Bilinear/Curve、五 SmartConnect、HPM0、HP0～HP3 都由同一 `pl_clk0` 网驱动。`check_timing -verbose`：`no_clock=0`、`unconstrained_internal_endpoints=0`、`multiple_clock=0`、断源 generated clock=0、组合环=0、latch loop=0。综合时 8 个未用 PS EMIO `no_clock` 项在 post-route 为 0。`report_exceptions -summary` 有 125 条 False Path 约束、影响 6 个 setup/6 个 hold endpoints；无 Clock Groups、Multicycle、Max/Min Delay。没有独立运行 `report_cdc`，所以不宣称完成全面 CDC 分析。

保存 BD 的 `pl_resetn0 → rst_ps_100m/ext_reset_in`、`peripheral_aresetn → 三颗 HLS ap_rst_n`、`interconnect_aresetn → 五 SmartConnect aresetn` 在 launch 前逐 pin 核对通过；reset IP `C_EXT_RESET_HIGH=0`，保持 ACTIVE_LOW 语义。物理放置对高扇出 `peripheral_aresetn[0]` 插入 BUFG（9,592 loads）并复制一处驱动，属于 Vivado 自动物理优化。Post-route DRC 的 RTSTAT-10 涉及 `axi_control` 内 20 条 `mi_handler_m_sc_areset_pipe` 等**无可路由负载**的 net；它不是 `report_route_status` 的 unrouted net（unrouted=0），也未升级为 Critical Warning。仅凭本阶段不能证明 PS 软件触发复位及 AXI 事务在板上正确，后续系统测试仍需复核。

## 5. Post-route 资源与 SmartConnect 成本

资源来自 routed checkpoint 的 `report_utilization`。BRAM tile=`RAMB36 + RAMB18/2`；等效 BRAM18=`2×RAMB36 + RAMB18`。

| 资源 | Post-synth | Post-route | 变化 | K26 可用 / post-route 利用率 |
|---|---:|---:|---:|---:|
| CLB LUT | 29,728 | **27,045** | −2,683 | 117,120 / 23.09% |
| LUT as Logic | 24,689 | 22,847 | −1,842 | 117,120 / 19.51% |
| LUT as Memory | 5,039 | 4,198 | −841 | 57,600 / 7.29% |
| 其中 LUTRAM | 2,858 | 2,812 | −46 | — |
| 其中 SRL | 2,181 | 1,386 | −795 | — |
| FF | 41,819 | **39,451** | −2,368 | 234,240 / 16.84% |
| RAMB36 / RAMB18 | 24 / 10 | **24 / 10** | 0 / 0 | 144 / 16.67%；288 / 3.47% |
| BRAM tile / 等效 BRAM18 | 29 / 58 | **29 / 58** | 0 / 0 | 144 / 20.14%；288 / 20.14% |
| DSP | 76 | **76** | 0 | 1,248 / 6.09% |
| URAM | 0 | **0** | 0 | 64 / 0% |
| BUFG_PS / BUFGCE | 2 / 0 | **1 / 2** | 物理插入/优化 | 96 / 1.04%；112 / 1.79% |
| Bonded IOB | 0 | 0 | 0 | 189 / 0% |

| Routed hierarchy | LUT | FF | LUTRAM | SRL | RAMB36 | RAMB18 | DSP |
|---|---:|---:|---:|---:|---:|---:|---:|
| CNN | 8,295 | 9,651 | 0 | 592 | 24 | 5 | 19 |
| Bilinear | 3,937 | 4,912 | 0 | 205 | 0 | 3 | 33 |
| Curve | 2,900 | 4,641 | 0 | 494 | 0 | 2 | 24 |
| `axi_control` | 946 | 996 | 0 | 1 | 0 | 0 | 0 |
| `cnn_data_sc` | 3,721 | 6,250 | 898 | 34 | 0 | 0 | 0 |
| `cnn_model_sc` | 2,264 | 3,760 | 588 | 12 | 0 | 0 | 0 |
| `bilinear_ddr_sc` | 2,184 | 4,157 | 588 | 23 | 0 | 0 | 0 |
| `curve_ddr_sc` | 2,791 | 5,046 | 738 | 24 | 0 | 0 | 0 |
| `rst_ps_100m` | 17 | 38 | 0 | 1 | 0 | 0 | 0 |
| **全系统** | **27,045** | **39,451** | **2,812** | **1,386** | **24** | **10** | **76** |

五个 SmartConnect 从 post-synth **13,295 LUT / 22,532 FF / 2,858 LUTRAM** 到 post-route **11,906 LUT / 20,209 FF / 2,812 LUTRAM**，没有因四 HP 分流出现资源异常膨胀；四组 DDR SmartConnect post-route 合计 10,960 LUT / 19,213 FF。LUT、FF、SRL 降低是 Vivado 自动优化/映射的资源变化，不表示算法/格式变化，也不能据此推算 DDR 实际吞吐。当前系统 BRAM 29/144 tile、DSP 76/1248、LUT 27,045/117,120，容量仍安全。层级行是归属统计，边界优化后逐项相加不一定严格等于顶层总数。

## 6. Post-route DRC、AXI 与其他 warning

`report_drc` 于 Fully Routed 状态：**0 Error、0 Critical Warning、136 Warning**。

| DRC rule | 数量 | 判断 |
|---|---:|---|
| `DPIP-2` | 40 | DSP 输入流水线性能建议；本阶段未修改 HLS pragma |
| `DPOP-3` | 43 | DSP PREG 输出流水线建议 |
| `DPOP-4` | 52 | DSP MREG 输出流水线建议 |
| `RTSTAT-10` | 1 | `axi_control` 内 20 条复位管道相关 net 无可路由负载；不是 routing error；保留为后续 reset/AXI 系统验证关注项 |

前次 post-synth DRC 为 `DPIP-2` 40、`DPOP-3` 51、`DPOP-4` 60，合计 151；本次 DSP 建议降为 135，另有 1 条 RTSTAT。Vivado 在 route run 中实际执行的 `report_methodology` 为 **0 checks found**。Routed 资源报告 Black Boxes 栏为空、latch=0，`check_timing` 没有组合环；没有发现 multiple-driver、CDC、clock、address decode 的 Critical DRC。

实现 `runme.log` 只有一条前述 IP cache 路径长度 Warning，0 Error、0 Critical Warning。打开工程的 driver 另有本机其他板型扫描 `[Board 49-26]` 73 行及 `report_clock_interaction` 的 `[Timing 38-164]` 多时钟通用提示；目标 KV260 board/part 正常，实际时序路径仍仅在 `clk_pl_0`。上一阶段的 HLS `AWLOCK/ARLOCK` 2→1 bit、PS HP AWUSER/ARUSER width 和 SmartConnect 参数推断提示在本次 Implementation log **未重新出现，也未升级成错误**。已生成的 `sc_si_converter` 继续承担 DDR 32→128 bit 和控制 AXI4→AXI4-Lite 适配；本阶段没有运行协议仿真或 DDR 实际事务，因此只能说 **Implementation 未发现 AXI/clock/reset 结构 blocker，不能宣称 AXI 事务正确**。

## 7. 当前结论、文件与后续边界

本次满足任务等级 **A**：`route_design` PASS、setup WNS≥0/TNS=0、hold WHS≥0/THS=0、pulse width PASS、0 unrouted、0 routing error、0 DRC Error、0 Critical Warning blocker。**V1.1 已达到 100 MHz post-route physical timing closure**，可建议 Master 审核后进入 Bitstream/XSA 阶段；本次没有自行继续。

本次任务新增 `fpga/scripts/vivado_three_module_v1_1_impl.tcl` 与本报告。Vivado 的可再生 `.runs/impl_1` 中保存 `system_wrapper_opt.dcp`、`system_wrapper_placed.dcp`、`system_wrapper_physopt.dcp`、`system_wrapper_routed.dcp`；外部原始日志/报告在 `E:/HLS/vivado_three_module_v1_1_impl_driver.log`、`E:/HLS/vivado_three_module_v1_1_implementation/` 和 V1.1 `impl_1/runme.log`。旧 V1 未改动，之前已有的未跟踪文件保留。建议审核后的 commit message：`feat(fpga): audit routed KV260 three-module V1.1`；**本次未执行 `git add`、commit、push**。

明确未运行/未验证：Bitstream、XSA、RTL Co-sim、PS 软件、KV260 板测、实际 DDR transaction/吞吐、30 FPS、CNN 整帧 latency、PS cache/coherency、三模块板上最终图像数值链。`POST_ROUTE_TIMING_CLEAN` 只覆盖本次当前设计和约束下的物理时序。
