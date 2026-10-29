# PS8 未使用输出与有效 PL 时序覆盖

日期：2026-10-29。此项记录真实引脚范围，不创建虚构时钟、不新增 false-path 或 waiver，也不改写原始报告。

## 综合 DCP 的实际诊断

`check_timing -verbose` 将原先 8 个 no_clock 精确定位为同一 PS8 硬核的输出：

- `system_i/zynq_ultra_ps_e_0/inst/PS8_i/EMIOENET{0,1,2,3}MDIOMDC`
- `system_i/zynq_ultra_ps_e_0/inst/PS8_i/EMIOSDIO{0,1}CLKOUT`
- `system_i/zynq_ultra_ps_e_0/inst/PS8_i/EMIOSPI{0,1}SCLKO`

独立 Vivado 正常退出，重开 SHA256=`f595e389cfbd940e8fc438102f82a9bcc575caf75973deb6b6faf105019e1e6d` 的真实综合 checkpoint。逐项确认 `REF_NAME=PS8`、`DIRECTION=OUT`，遍历跨层次全部 net segments 后，leaf 输入负载、顶层端口、关联时钟数均为 0。因此这些输出没有驱动本联合设计中的 PL 寄存器或外部引脚，不能把它们误称为模型核缺少工作时钟。六核真实 HWH 的 100/200 MHz 分域与低有效同步复位另已核对。

原始证据在 `D:/weather_builds/joint_clock_audit01_20261029/` 和 `joint_clock_audit02_20261029/`。综合诊断不替代 routed 验收。

## 最终门禁

1. `build_system.py --stage coverage` 必须在实现阶段真正通过之后，独立重开精确的 `joint_routed.dcp`，记录 checkpoint SHA 和实际命令/退出码。
2. 保留完整 `routed_clock_check.rpt`；`routed_unused_ps_clocks.txt` 必须逐项证明精确上述 8 个输出的身份和零负载，任何少项、未知项、PL 负载或顶层端口立即失败。
3. `accept_system.py` 将完整 no_clock 名单与该证明严格匹配。默认仍拒绝非零 no_clock；只有完整身份/扇出证据一致才分类为未使用 PS 输出。原始 `coverage.no_clock` 按该次报告保留为 0 或 8，同时 `active_unclocked_pins=0`。无论计数如何，8 个 PS 输出均另做零负载证明。
4. constant_clock、multiple_clock、unconstrained_internal_endpoints 必须为 0；setup/hold/pulse-width、完整 route、全部 bus-skew 约束和严重 CDC/DRC 门槛均不放宽。`routed_bus_skew.rpt` 与独立导出的 `export_bus_skew.rpt` 必须覆盖完整约束集合、全部 slack 非负。
5. 导出阶段再次独立重开已验收 DCP，重做同样的证明；打包器读取该次实际报告。不能使用综合证明替代 routed 或 export 的证明。

本轮增加测试覆盖：缺少证明仍拒绝 8 项、证明缺项拒绝、未知无钟引脚拒绝、任何 PL 负载/顶层端口/关联时钟变化拒绝。完整六核系统 RTL 与板端验证的范围仍按加载说明明确区分。
