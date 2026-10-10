# KV260 Fixed16 V1：Vivado Implementation 与 post-route 审核

## 1. 目标与基线

基于已通过 Validate Design、output products、HDL wrapper 和 Vivado Synthesis 的 Fixed16 非 CNN V1 系统，沿用当前工程的默认 Implementation strategy，实际执行到 `route_design`，检查 post-place / post-route 时序、布线状态、DRC 和资源。

本次没有改 Bilinear / Curve HLS core、Fixed16 格式、性能 pragma 或 AXI 架构；没有运行 bitstream、Export Hardware/XSA、PS 软件、CNN 集成或 KV260 板上测试。没有进行新的数值 CSim、RTL Co-sim 或 DDR 事务测试。

| 项目 | 实际值 |
| --- | --- |
| Git 分支 / HEAD | `codex/curve-fp32-baseline` / `5b1f54a380e5bd1e2cf0b892c303a94a089a47af` |
| Vivado | 2025.2，SW Build 6299465，IP Build 6300035 |
| Board / part | Kria KV260 Vision AI Starter Kit SOM / `xck26-sfvc784-2LV-c` |
| 工程 | `E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr` |
| Top | `system_wrapper` |
| Strategy / flow | `Vivado Implementation Defaults` / `Vivado Implementation 2025`（未改） |
| 目标时钟 | PS `pl_clk0`，10.000 ns / 100.000 MHz |
| 既有综合基线 | `fpga/reports/vivado_fixed16_synthesis_v1.md`；`synth_1=synth_design Complete!` |
| 本次 run 最终状态 | `impl_1=route_design Complete!`，progress `100%` |

系统仍为 PS HPM0 → `axi_control` → 两个 HLS AXI4-Lite；Bilinear 输入/输出与 Curve 输入/参数/输出共 5 路 m_axi → `axi_ddr` → PS HP0 → DDR。两个 HLS IP repository 仍来自 `E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip` 和 `E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip`，本次没有重新打包。

## 2. 实际执行命令和 Implementation 阶段

实际从 `E:\HLS` 调用 Vivado 2025.2 CLI，并加载 `settings64.bat`。三个命令均采用以下格式，只将 `SCRIPT`、`LOG` 替换为表中值：

```cmd
cmd /c "set PROCESSOR_ARCHITECTURE=AMD64&& call E:\Xilinx\2025.2\data\settings64.bat && call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\SCRIPT -log E:\HLS\vivado_fixed16_implementation_v1\LOG.log -journal E:\HLS\vivado_fixed16_implementation_v1\LOG.jou -notrace"
```

| 执行 | `SCRIPT` | `LOG` | 实际结果 |
| --- | --- | --- | --- |
| Implementation | `vivado_fixed16_implementation_v1.tcl` | `implementation_driver` | `launch_runs impl_1 -to_step route_design -jobs 4`，`wait_on_run`；PASS |
| Routed checkpoint 审核 | `vivado_fixed16_postroute_audit_v1.tcl` | `postroute_audit` | `open_run impl_1`，实际运行 route status、DRC、utilization、timing summary、worst setup/hold path、`check_timing -verbose`；PASS |
| Placed checkpoint 时序补查 | `vivado_fixed16_postplace_audit_v1.tcl` | `postplace_audit` | `open_checkpoint system_wrapper_placed.dcp`，实际运行 timing summary；PASS |

表中实际为三个 batch 命令；`SCRIPT` 路径均在 `E:/github/-/fpga/scripts/`。Implementation 脚本只要求停止在 `route_design`，没有 `write_bitstream` / `launch_runs impl_1 -to_step write_bitstream`。`impl_1` 下存在 `system_wrapper_placed.dcp`、`system_wrapper_physopt.dcp`、`system_wrapper_routed.dcp`，没有 `.bit`。

| 阶段 | 实际结果 | Error / Critical Warning / 重要事项 |
| --- | --- | --- |
| `opt_design` | PASS | run log 阶段摘要：0 error、0 critical warning、0 warning |
| `place_design` | PASS | 同上；生成 `system_wrapper_placed.dcp` |
| `phys_opt_design` | PASS，默认 strategy 实际包含 | 同上；Vivado 因 setup 已满足而跳过进一步 setup 优化，生成 physopt checkpoint |
| `route_design` | PASS | 同上；`Router Completed Successfully`，生成 `system_wrapper_routed.dcp` |

阶段证据在 `E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.runs/impl_1/runme.log`。脚本查询部分 run step `IS_ENABLED` 属性时产生 3 条 `[Common 17-673]`，属于监测属性不适用的提示；实际 log 证实四阶段均被执行，不影响实现，也未改变策略。打开工程时还重复出现与目标 KV260 无关的 `[Board 49-26]` 其他 board-part 库扫描 warning，目标 part 实际成功加载。

## 3. Post-synthesis、post-place、post-route 时序

以下全部是 **同一 10 ns / 100 MHz 约束**。Post-synthesis 为未放置/未布线估计；post-place 从 `system_wrapper_placed.dcp` 实测报告；post-route 从 `system_wrapper_routed.dcp` 实测报告。

| 阶段 | Setup WNS | TNS | Setup failing endpoints | Hold WHS | THS | Hold failing endpoints | WPWS / TPWS | Vivado 判断 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Post-synthesis | +2.613 ns | 0.000 ns | 0 / 64,006 | −0.093 ns | −688.756 ns | 22,097 / 64,006 | +3.500 / 0.000 ns | Timing constraints not met |
| Post-place | +1.168 ns | 0.000 ns | 0 / 61,784 | −0.117 ns | −10.078 ns | 514 / 61,784 | +3.500 / 0.000 ns | Timing constraints not met |
| **Post-route** | **+1.123 ns** | **0.000 ns** | **0 / 61,784** | **+0.010 ns** | **0.000 ns** | **0 / 61,784** | **+3.500 / 0.000 ns** | **All user specified timing constraints are met** |

结论：**100 MHz setup 满足；post-synthesis 的 22,097 个 hold 违例在 placement/routing 后全部消除。** 路由中间阶段一度有 `WHS=-0.032 ns / THS=-0.380 ns`，Vivado 随后的 delay/skew cleanup 将其提升到 `WHS=+0.010 ns / THS=0`。Post-route 已无 failing setup、hold 或 pulse-width endpoints。post-place 的 WHS 数值比 post-synthesis 更负 0.024 ns，但违例数和 THS 显著减小；不能仅凭单个 worst slack 判断整体趋势。各阶段端点总量因物理优化而变化。

Post-route 最差 setup path 位于 Bilinear 的行缓存 BRAM 读端至其 DSP 乘法器输入，slack +1.123 ns。由于 **hold 已无违例**，不再将旧的 `axi_ddr`/XPM FIFO 违例当作当前问题；本次 `postroute_hold_paths.rpt` 仅列满足约束的最小延迟路径。

`check_timing -verbose` 在 routed checkpoint 上报告：`no_clock=0`、`unconstrained_internal_endpoints=0`、缺失 I/O delay=0、`multiple_clock=0`、`generated_clocks=0`、combinational loops=0、latch loops=0。先前 post-synthesis 的 8 个 PS EMIO `no_clock` 提示在 post-route 检查中为 0。时钟 summary 也显示 `clk_pl_1` 定义为 10 ns，但实际 Intra Clock Table 仅有 `clk_pl_0`；本设计被分析的 PL 路径都在 100 MHz 域。本次没有单独运行 `report_cdc`，因而没有宣称完成全面 CDC 分析。

## 4. Route status 与 post-route DRC

`report_route_status`：86,750 条逻辑 net；其中 59,888 条无需路由，26,862 条需要路由且 **26,862 / 26,862 全部完成（100%）**；routing errors=0、unrouted routable nets=0、routing conflicts=0。`route_design` 还明确输出 `Router Completed Successfully`。

Post-route `report_drc` 共 **106 条 Warning、0 Critical Warning、0 Error**：

| Rule | 数量 | 含义与本阶段处理 |
| --- | ---: | --- |
| DPIP-2 | 27 | DSP 输入流水线建议；保留，不修改 HLS 算法或 pragma |
| DPOP-3 | 37 | DSP PREG 输出流水线建议；保留 |
| DPOP-4 | 41 | DSP MREG 乘法流水线建议；保留 |
| RTSTAT-10 | 1 | 提示 `axi_control` 内约 15 条 `mi_handler_m_sc_areset_pipe` 复位相关 net 无可路由负载；不等于有未布线 net。当前 route status 0 error，仍需在后续系统复位验证中关注 |

前次 post-synthesis DRC 的 DSP 建议为 27/45/49，共 121 条；这次为 27/37/41，建议条数下降，未新增 critical DRC。独立 `report_methodology`（Vivado 在 route run 中自动执行）检查数为 0。Post-route utilization 的 Black Boxes 表为空；FF latch=0，时序检查无 combinational loop。实现 run log 中未发现 multiple-driver、CDC、AXI 或 clock error。

此前 BD 的 PS HP0 `AWUSER/ARUSER` width 与 SmartConnect USER width 警告、HLS `AWLOCK/ARLOCK` width 警告，以及 SmartConnect reset 自动关联提示，在本次 implementation `runme.log` 中**未重新出现，也没有升级成 error**；这只说明实现阶段没有再报告它们，不能证明 AXI DDR 事务已验证。HLS IP Pre-Production/packaging 提示亦未在本次实现日志中出现。工具对 `const_locked` utility IP 的迁移建议仍在打开工程时出现。当前仍是未上板、未做 PS 软件及 DDR 读写事务的硬件实现结果。

## 5. Post-implementation 资源及对照

`report_utilization` 于 fully routed checkpoint 上执行。资源是 Vivado 实现值，不应从其变化推断算法变化。

| 资源 | Post-synthesis | Post-route | 变化 | 可用 / post-route 利用率 |
| --- | ---: | ---: | ---: | --- |
| CLB LUT | 13,490 | **12,021** | −1,469 | 117,120 / 10.26% |
| LUT as Logic | 11,252 | 10,232 | −1,020 | 117,120 / 8.74% |
| LUT as Memory | 2,238 | 1,789 | −449 | 57,600 / 3.11% |
| 其中 LUTRAM | 1,068 | 1,052 | −16 | — |
| 其中 SRL | 1,170 | 737 | −433 | — |
| FF | 18,681 | **17,654** | −1,027 | 234,240 / 7.54% |
| RAMB18 | 5 | **5** | 0 | 288 / 1.74% |
| BRAM tile | 2.5 | **2.5** | 0 | 144 / 1.74% |
| URAM | 0 | **0** | 0 | 64 / 0% |
| DSP | 57 | **57** | 0 | 1,248 / 4.57% |

Post-route hierarchy 仅作归属参考：Bilinear 3,942 LUT / 4,912 FF / 3 RAMB18 / 33 DSP；Curve 2,897 LUT / 4,641 FF / 2 RAMB18 / 24 DSP；`axi_control` 873 LUT / 937 FF；`axi_ddr` 4,302 LUT / 7,126 FF；`rst_ps_100m` 17 LUT / 38 FF。Vivado 的总 LUT 受跨层级 LUT 合并影响，**hierarchy 各行不必简单相加**。资源缩减发生于标准实现优化，核心源码与 IP 接口语义未改。

## 6. 文件、原始产物、当前结论

本次新增：

- `fpga/scripts/vivado_fixed16_implementation_v1.tcl`：按现有策略实施到路由，明确不生成 bitstream。
- `fpga/scripts/vivado_fixed16_postroute_audit_v1.tcl`：输出正式的 route、DRC、资源、时序报告。
- `fpga/scripts/vivado_fixed16_postplace_audit_v1.tcl`：从 placed checkpoint 补查中间时序。
- `fpga/reports/vivado_fixed16_implementation_v1.md`：本报告。

工程内新增/更新的实现工件位于 `fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.runs/impl_1/`。便于复核的外部日志与报告位于 `E:/HLS/vivado_fixed16_implementation_v1/`，包括 `implementation_driver.log`、`postroute_audit.log`、`postplace_audit.log`、`postplace_timing_summary.rpt`，以及 `postroute_route_status.rpt`、`postroute_drc.rpt`、`postroute_utilization.rpt`、`postroute_utilization_hierarchical.rpt`、`postroute_timing_summary.rpt`、`postroute_setup_paths.rpt`、`postroute_hold_paths.rpt`、`postroute_check_timing_verbose.rpt`。

当前 Git 分支未改变，新增脚本、报告和 Vivado 工程仍未跟踪；先前集成/综合报告与脚本也仍未跟踪。**未执行 `git add`、commit、push。**

供人工审核后的建议 Commit Message：`Report KV260 Fixed16 V1 routed implementation results`。这仅是建议，本次不提交。

**当前结论**：Fixed16 非 CNN V1 系统的 Vivado Implementation 已完成到全布线，100 MHz setup/hold/pulse-width 均满足；post-synthesis hold 违例由物理实现自动修复。没有 critical DRC 或布线错误。仍有 DSP 优化建议和一项 SmartConnect 复位 net 的 RTSTAT-10 warning。未执行 bitstream、XSA、PS 软件、DDR 事务或板上测试。本次到此停止，等待 Master 审核。
