# KV260 三模块 V1.1：Vivado 全系统综合与综合后审计

日期：2026-09-29。**结论：已保存的 V1.1 Block Design 再次 Validate PASS；output products、`system_wrapper` 和完整工程 `synth_1` 均成功。100 MHz 综合后 setup WNS 为 +2.613 ns，资源占用低于 K26 容量。综合后 hold 仍有 53,770 个违例，必须等待后续物理实现判断最终时序。** 本次停止在 synthesis；没有运行 Implementation、bitstream、XSA 或板测。

## 1. 目标、版本与保护边界

本次从磁盘上的既有 V1.1 工程重新打开 `system.bd`，先确认三颗固定 HLS IP、控制/DDR 地址、100 MHz 时钟和复位并再次 Validate，然后生成全部 BD output products、Vivado 管理的 HDL wrapper，运行完整 `synth_1`，审计系统资源、时序、DRC 及 AXI/IP warning。没有修改 CNN、Bilinear、Curve 的算法、数值格式、HLS pragma 或 IP 包；没有更新 WZH 分支 HEAD。

| 项目 | 实际值 |
|---|---|
| Git branch / HEAD | `codex/curve-fp32-baseline` / `503537cf2e084d22b6e6856b0cb0ffff64f211e0` |
| Vivado | 2025.2，SW Build 6299465，IP Build 6300035 |
| Board / part | `xilinx.com:kv260_som:part0:1.4` / `xck26-sfvc784-2LV-c` |
| 工程 | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.xpr` |
| 保存的 BD | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.srcs/sources_1/bd/system/system.bd` |
| CNN 固定源码提交 | `72b21138ce87a16eb3d3d6163675936b82ceadbc`；本次复用已固定的 K26/10 ns IP，不重新 HLS 综合 |
| CNN IP | `xilinx.com:hls:zero_dce_cnn_top:1.0`，`E:/HLS/kv260_three_module_v1_1_ip_repo/cnn_72b2113_k26_10ns` |
| Bilinear IP | `xilinx.com:hls:bilinear_fixed16_buffered:1.0`，`E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip` |
| Curve IP | `xilinx.com:hls:curve_image_fixed16:1.0`，`E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip` |
| 旧稳定 V1 | `fpga/vivado/fixed16_integration_v1/`；执行前后 `git status --short -- fpga/vivado/fixed16_integration_v1` 均为空，本次没有打开、重保存或重跑旧工程 |

上述三个外部 IP repository 是脚本重放时必须存在的本机依赖；新 Tcl 不从浮动 WZH branch 取 IP。V1.1 的 Vivado `.runs/.gen/.cache` 为本次自动生成物，不作为手写设计输入。

## 2. 磁盘 BD 再确认与 Validate

重新打开现有 `.xpr` 与磁盘 `.bd` 后，脚本核对了 `zero_dce_cnn_top_0`、`bilinear_fixed16_buffered_0`、`curve_image_fixed16_0` 的精确 VLNV，以及 PS、`rst_ps_100m`、`axi_control`、`cnn_data_sc`、`cnn_model_sc`、`bilinear_ddr_sc`、`curve_ddr_sc`。三颗 HLS VLNV 在 IP Catalog 中均唯一可解析。PS HPM0=enabled、HPM1=disabled、HP0～HP3=enabled，`pl_clk0=100 MHz`。

控制路径仍为 **PS HPM0 → `axi_control` 1 SI/3 MI → 三颗 HLS `s_axi_control`**；地址分别为 Bilinear `0xA0000000`、Curve `0xA0010000`、CNN `0xA0020000`，每段 64 KiB。数据路径保留四组 HP：CNN input/output/workspace→HP0，CNN gmem8/gmem32/LUT→HP1，Bilinear input/output→HP2，Curve input/parameter/output→HP3。11 个 HLS m_axi 地址空间各有 DDR LOW 与 DDR HIGH 两段；没有已映射的 QSPI/OCM 段。

同一 `pl_clk0` BD net 接三颗 HLS、五个 SmartConnect、PS HPM0/HP0～HP3 的 AXI clock 和 `rst_ps_100m/slowest_sync_clk`。PS `pl_resetn0` 接 reset IP 的 `ext_reset_in`；重新 Validate 后确认输入极性 `ACTIVE_LOW`、`C_EXT_RESET_HIGH=0`。本次 **`validate_bd_design` PASS** 后才执行 `generate_target`。未新增 Clock Converter 或异步数据时钟域。

## 3. 实际执行命令、产物与运行时间

本次新增 `fpga/scripts/vivado_three_module_v1_1_synth.tcl`，从**现存工程**依次执行磁盘检查/Validate、`generate_target all`、`make_wrapper -top -add`（已有 wrapper 则复用）、`launch_runs synth_1 -jobs 4` / `wait_on_run synth_1`（已完成 run 则复用）、`open_run synth_1`、资源/时序/DRC 报告。实际在 PowerShell 运行三次同一个入口命令：

```powershell
& E:\HLS\vivado_three_module_v1_1_synth.cmd
```

外部 `.cmd` 实际先调用 `E:\Xilinx\2025.2\data\settings64.bat`，然后调用 `E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_three_module_v1_1_synth.tcl -log E:\HLS\vivado_three_module_v1_1_synthesis_driver.log -journal E:\HLS\vivado_three_module_v1_1_synthesis_driver.jou -notrace`。Vivado 自动保留了前两次 driver 日志 `E:/HLS/vivado_three_module_v1_1_synthesis_driver_55072.backup.log`、`..._56100.backup.log`；第三次当前日志为 `...synthesis_driver.log`。

第一次执行：Validate PASS；`generate_target all` 于 09:24:46～09:25:53 完成，**67 秒、无 ERROR / Critical Warning**；`system_wrapper` 已生成。随后启动 10 个 IP OOC run 和真正的顶层 `synth_1`。`SYNTH_START_EPOCH=1790645156`、`SYNTH_DONE_EPOCH=1790645602`，全 run 等待约 **446 秒（7 分 26 秒）**，`SYNTH_STATUS=synth_design Complete!`、`SYNTH_PROGRESS=100%`，顶层 DCP 存在；顶层 Vivado worker 的 `synth_design` 本身报告 elapsed **49 秒**、peak memory **3081.922 MB**。并行 OOC run 不能把单 worker 峰值简单相加。首次执行在**综合成功之后**，因报告阶段误用本机 Vivado 不支持的 Tcl `redirect` 命令而停止，故第一次未生成 DRC 文件；这不是 `synth_1` 失败。

仅将 Tcl 改成实际支持的 `check_timing -verbose -file` 后第二次执行：Validate 和 cached output products/wrapper 再次 PASS；日志明确为 `SYNTH_ALREADY_COMPLETE=synth_design Complete!`，没有重跑 HLS core 或完整综合；补齐 `check_timing`、clock interaction、DRC，`POST_SYNTHESIS_REPORTS=PASS`。第三次在 Tcl 中补充 `report_clocks` 与 `report_exceptions -summary`，再次复用已完成的 `synth_1`，最终报告全部 PASS。报告打开综合 checkpoint 的 driver 峰值约 **4255.973 MB**，不是综合 worker 的峰值。

| 产物 | 实际路径 / 状态 |
|---|---|
| BD output products | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.gen/sources_1/bd/system/`；生成 PASS |
| HDL wrapper | 同目录 `hdl/system_wrapper.v`；`module system_wrapper (); system system_i (); endmodule`，无外部未连接顶层端口；综合 top=`system_wrapper` |
| 顶层 DCP | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.runs/synth_1/system_wrapper.dcp`；完整 `synth_1` PASS |
| Vivado 报告 | `E:/HLS/vivado_three_module_v1_1_synthesis/` 内的 utilization、hierarchical utilization、setup/hold paths、timing summary、clock interaction、check_timing、DRC、IP status |

`report_ip_status` 在 output products 后列出 **178 个主/内部 IP 实例**，三颗 HLS、五个 SmartConnect、PS 等均为 `Up-to-date / No changes required`，未见 missing/locked。`system_const_locked_0` 为 `Up-to-date (discontinued)`，仍可用且没有替换。综合利用率表的 Black Boxes 栏为空，FF latch=0。

## 4. Post-synthesis 系统资源与 K26 容量

以下全部来自 **Vivado 全系统 post-synthesis `report_utilization`**。BRAM tile=RAMB36+RAMB18/2；等效 BRAM18=2×RAMB36+RAMB18。不能把只有 RAMB18=10 误当成全部 BRAM。

| 资源 | 已用 | K26 可用 | 利用率 |
|---|---:|---:|---:|
| CLB LUT | 29,728 | 117,120 | 25.38% |
| LUT as Logic | 24,689 | 117,120 | 21.08% |
| LUT as Memory | 5,039 | 57,600 | 8.75% |
| 其中 LUTRAM / SRL | 2,858 / 2,181 | — | — |
| FF | 41,819 | 234,240 | 17.85% |
| RAMB36 | 24 | 144 | 16.67% |
| RAMB18 | 10 | 288 | 3.47% |
| BRAM tile / 等效 BRAM18 | 29 / 58 | 144 / 288 | 20.14% / 20.14% |
| URAM | 0 | 64 | 0% |
| DSP48E2 | 76 | 1,248 | 6.09% |
| BUFG_PS | 2 | 96 | 2.08% |
| Bonded IOB | 0 | 189 | 0% |

### 直接实例层级归属

| 实例 | LUT | FF | LUTRAM | SRL | RAMB36 | RAMB18 | DSP |
|---|---:|---:|---:|---:|---:|---:|---:|
| CNN `zero_dce_cnn_top_0` | 8,770 | 9,694 | 0 | 921 | 24 | 5 | 19 |
| Bilinear | 4,173 | 4,912 | 0 | 359 | 0 | 3 | 33 |
| Curve | 3,207 | 4,641 | 0 | 753 | 0 | 2 | 24 |
| `axi_control` | 1,042 | 1,096 | 0 | 1 | 0 | 0 | 0 |
| `cnn_data_sc` | 4,159 | 6,970 | 916 | 53 | 0 | 0 | 0 |
| `cnn_model_sc` | 2,514 | 4,231 | 588 | 20 | 0 | 0 | 0 |
| `bilinear_ddr_sc` | 2,439 | 4,588 | 602 | 36 | 0 | 0 | 0 |
| `curve_ddr_sc` | 3,141 | 5,647 | 752 | 37 | 0 | 0 | 0 |
| `rst_ps_100m` | 19 | 40 | 0 | 1 | 0 | 0 | 0 |
| PS wrapper | 264 | 0 | 0 | 0 | 0 | 0 | 0 |
| **全系统** | **29,728** | **41,819** | **2,858** | **2,181** | **24** | **10** | **76** |

五个 SmartConnect 合计 **13,295 LUT、22,532 FF、2,858 LUTRAM、147 SRL**，占本次系统 LUT 约 44.7%、FF 约 53.9%；四个 DDR SmartConnect 合计 12,253 LUT、21,436 FF。互连成本显著，但总资源仍低于器件容量；这不是实测 DDR 吞吐结论。层级数字是综合报告的直接实例归属，PS wrapper 的 264 LUT 不表示 PS 硬核本身消耗这么多 PL LUT。

CNN 自身实际为 24 RAMB36+5 RAMB18 = **53 个等效 BRAM18 / 26.5 BRAM tile**；整个系统 29/144 BRAM tile、无 URAM，故**当前综合网表的 BRAM 容量仍安全**。CNN OOC DCP 利用率与系统层级该实例一致。与此前 HLS 估计 DSP16、LUT约16,247、FF约9,285、BRAM18约56 比较：Vivado 层级实测 DSP19、LUT8,770、FF9,694、等效 BRAM18=53；工具阶段及 LUT/BRAM 计量口径不同，不能相加或视作算法变化。模型/tile 缓存主要映射至块 RAM；本次四组 SmartConnect 的 FIFO/缓冲还使用 2,858 LUTRAM，未额外使用块 RAM。此处仅为综合映射，非物理实现签核。

### 与旧 V1 同阶段比较

旧 V1 post-synthesis 数值来自 `fpga/reports/vivado_fixed16_synthesis_v1.md`，比旧 V1 post-route 更适合本表对照。

| 资源 | 旧 V1 post-synth | 新 V1.1 post-synth | 差值 |
|---|---:|---:|---:|
| LUT | 13,490 | 29,728 | +16,238 |
| LUTRAM | 1,068 | 2,858 | +1,790 |
| SRL | 1,170 | 2,181 | +1,011 |
| FF | 18,681 | 41,819 | +23,138 |
| RAMB36 / RAMB18 | 0 / 5 | 24 / 10 | +24 / +5 |
| 等效 BRAM18 | 5 | 58 | +53 |
| DSP | 57 | 76 | +19 |
| URAM | 0 | 0 | 0 |

新增 CNN 贡献 8,770 LUT、9,694 FF、53 个等效 BRAM18、19 DSP；新增/扩展互连约贡献其余 +7,468 LUT、+13,444 FF、+1,790 LUTRAM。旧 V1 **post-route** 另有 12,021 LUT、17,654 FF、5 RAMB18、57 DSP；其阶段与新 V1.1 本次 post-synth 不同，仅供量级参考，不能作严格 delta。

## 5. 综合后时钟、setup、hold 与关键路径

`report_clocks` 与 `report_timing_summary` 均识别 `clk_pl_0` 周期 **10.000 ns / 100.000 MHz**，来源为 PS8 `PLCLK[0]`。报告还列 PS8 `PLCLK[1]` 的 10 ns `clk_pl_1`，但真正有端点的 Intra Clock Table 与 `report_clock_interaction` 只有 `clk_pl_0→clk_pl_0`；BD 核对的所有当前 HLS/AXI PL 数据时钟同网。`report_clock_interaction` 对该自身时钟对标记 `Clean / Partial False Path`，没有跨时钟数据路径；工具仍打印 `[Timing 38-164]`“multiple clocks”通用警告。`report_exceptions -summary` 实测 **195 条 False Path 约束**、涉及 6 个 setup 和 6 个 hold endpoints；Clock Groups、Multicycle、Max/Min Delay 均为 0。`report_clocks` 的 Generated Clocks 区域为空。本次没有逐条追踪这些 IP/XDC exception 的来源，也没有运行独立 CDC 报告；不能把时钟列表的第二个名字当成新实际数据域。

| 指标 | Post-synthesis 实际值 |
|---|---:|
| Setup WNS / TNS | **+2.613 ns / 0.000 ns** |
| Setup failing / total endpoints | **0 / 147,675** |
| Hold WHS / THS | **−0.093 ns / −1,745.213 ns** |
| Hold failing / total endpoints | **53,770 / 147,675** |
| Pulse width WPWS / TPWS | **+3.500 ns / 0.000 ns** |
| Pulse width failing / total endpoints | **0 / 49,810** |

最差 setup 路径在 **Bilinear 计算核心**，没有进入 CNN 或 SmartConnect：`system_i/bilinear_fixed16_buffered_0/inst/zext_ln52_reg_1261_reg[15]/C` → `.../mul_ln62_reg_1419_reg/DSP_A_B_DATA_INST/A[0]`，group/clock=`clk_pl_0`，slack **+2.613 ns**，Data Path Delay **6.517 ns**（logic **4.606 ns**、估计 route **1.911 ns**），22 logic levels。前十条最差 setup 路径亦在 Bilinear。此时网表尚 `unplaced`，这里的 route 数字是 Vivado 综合后估计，并非物理布线实测。

最差 hold 路径在 **`bilinear_ddr_sc` 的 XPM FIFO 写地址寄存器 → 分布式 RAM 写地址**，group=`clk_pl_0`，slack **−0.093 ns**、Data Path Delay **0.142 ns**。与旧 V1 综合后 WHS−0.093 ns、22,097 failing endpoints、THS−688.756 ns 相比，新 V1.1 的最差 hold slack 相同但违例总数增大；新增互连/CNN 扩大了网表和分析端点。本阶段不把 post-synth hold 当作 post-route 结论，旧 V1 也曾在物理实现后消除 hold 违例；新 V1.1 是否能修复尚未验证。**综合后总 timing 报告为 `Timing constraints are not met`，原因是 hold，而不是 100 MHz setup。**

`check_timing -verbose`：8 个 `no_clock` 引脚全部是 PS8 未用的 EMIO MDC、SDIO、SPI clock 输出；`unconstrained_internal_endpoints=0`、缺失 I/O delay=0、`multiple_clock=0`、`generated_clocks=0`、组合环=0、latch loop=0。当前受分析的三模块 PL 路径没有发现未约束内部端点。最终 post-route timing、时钟/复位物理路径尚未审计。

## 6. AXI / IP / reset warning 与 post-synthesis DRC

| 来源与数量 | 实际观察、影响边界 |
|---|---|
| IP 状态 | 178/178 主/内部实例 `No changes required`；三颗 HLS IP 无 missing/locked。`const_locked` 旧 Constant IP 标为 discontinued，但产物与综合正常。 |
| Output products 初次日志 `[BD 41-2384]` 56 行 | HLS AXI `AWLOCK/ARLOCK` 2 bit 与 SmartConnect 1 bit 连接时只接低位；含 synth/sim 生成中的重复消息。`generate_target`、OOC、顶层综合均未因此失败。未做 RTL AXI 事务或硬件验证，故不能仅凭综合断言所有 sideband 行为。 |
| 之前的 `[BD 41-237]` / `[BD 41-3281]` | 前次 V1.1 Validate 曾记录 HP AWUSER/ARUSER 1 vs 0、自动参数推断提示；本次重新打开与综合日志没有再打印这两个 ID，也未升级为 error。仍需在系统仿真/板级测试检查实际 AXI 行为。 |
| 生成后的内部转换 | 四个 DDR SmartConnect 的 generated BD 均含 `sc_si_converter`，如 `cnn_data_sc` 参数 `RDATA_WIDTH=32`、`MSC000_RDATA_WIDTH=128`、`SEP000_PROTOCOL=AXI4`；明确存在 **32→128 位 AXI4 数据宽度适配**。`axi_control` 内部 `sc_si_converter` 为 `RDATA_WIDTH=128`、三路 `MSC*RDATA_WIDTH=32`、`AXILITE_CONV=1`、`SEP*_PROTOCOL=AXI4LITE`，明确存在 AXI4→AXI4-Lite 控制协议/宽度适配。实际 DDR burst 吞吐未测试。 |
| 顶层 `synth_1/runme.log` | 107 行 WARNING：`Synth 8-7071` 100 行未接 optional/方向不使用的接口脚；`Synth 8-7023` 6 行相应端口数摘要；`IP_Flow 19-4995` 1 行 Windows IP cache 路径偏长。顶层 run **0 ERROR、0 Critical Warning**，生成 DCP；不能只引用 `synth_design` 最后局部摘要的“0 warnings”抹去日志前面的 107 行。 |
| OOC SmartConnect/PS | 各 run 0 ERROR/0 Critical Warning。SmartConnect OOC 有内部 FIFO/RAM 无负载而裁剪、内部 `aresetn_out` 无驱动等 warning；PS OOC 有不使用的 EMIO 端口及连接宽度 warning。BD reset 源头/极性/负载 Validate PASS，顶层正常综合；这些内部警告不是板级复位功能验证。 |
| AXI/结构检查 | 未发现 unsupported part、unsupported burst、WSTRB/SIZE/LEN 协议 error、address decode error、black box、latch、组合环、multiple driver critical warning。上述判断仅基于本次日志/DRC，不等价于 AXI RTL Co-sim、DDR transaction 或正式协议检查。 |

本次 `report_drc`：**0 Error、0 Critical Warning、151 Warning**，全为 DSP pipeline 建议：`DPIP-2` 40、`DPOP-3` 51、`DPOP-4` 60。按所属核心统计 Bilinear 73、Curve 48、CNN 30；前两者合计 121，与旧 V1 的 DSP 建议数量相符。没有因建议而改 HLS pragma、算法或时钟。DRC 尚属 post-synthesis；没有运行 post-place/post-route DRC。

首次 driver 报告阶段 `invalid command name "redirect"` 是**本次 Tcl 报告命令**的真实错误，发生在 `synth_1` 已成功并产生 timing/resource 文件之后；第二次改用 `check_timing -file` 已补齐报告。初次生成时另有 `[Vivado 12-818] No files matched '*system_wrapper.v'`，发生于 wrapper 创建前的存在性探测；随后生成并以 `system_wrapper` 完整综合。`[Vivado 12-7122]` 表示无 incremental 参考 checkpoint，使用正常标准综合。板卡库还有 73 条 `[Board 49-26]`，均为本机其他板型不可用；目标 KV260 board/part 与 PS 产物均正常。

## 7. 当前结论、下一步与 Git

按本阶段分类属于 **A：完整系统 Synthesis PASS、100 MHz post-synth setup PASS、无结构 blocker、资源容量安全**。可以建议 Master 审核后进入 V1.1 Implementation，以确认 53,770 个 hold 违例能否在 place/route 后修复，并复查 AXI USER/LOCK、SmartConnect FIFO/reset、post-route DRC 与最终 timing。**本次没有启动 Implementation。** 综合及 HLS II 不能证明 DDR 带宽、30 FPS 或整帧时延。

本次新增/修改的任务文件仅为 `fpga/scripts/vivado_three_module_v1_1_synth.tcl` 与本报告；Vivado 在独立 V1.1 工程内生成了 output products、wrapper、10 个 OOC run 和顶层 `synth_1`。原有工作区未跟踪文件均保留；旧稳定 V1 的 Git 状态前后为空。建议未来经审核的 commit message：`feat(fpga): add KV260 three-module V1.1 synthesis audit`。**未执行 `git add`、commit 或 push。**

明确未运行/未验证：V1.1 Implementation、post-place/post-route setup/hold/DRC、bitstream、XSA、RTL Co-sim、PS 软件、DDR 实际事务/吞吐、FPS、KV260 板上运行、CNN→Bilinear→Curve 三模块硬件数值链。
