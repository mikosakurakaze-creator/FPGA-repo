# KV260 三模块 V1.2 当前进度

更新：2026-10-09。软件开发先读 [最新交接](kv260_v12_software_handoff.md)。

当前软件交接从 [START HERE](kv260_v12_START_HERE.md) 开始；[权威板测摘要](../reports/kv260_v12_board_validation.md) 列出最新 S1 和 `p7cold_resume_1009_02` 冷恢复证据；下文保留正式 release 与历史单帧结果。

真实 KV260 已完成最小冷启动控制恢复，以及诊断 bit 的 CNN→Bilinear→Curve 单帧：三个完整输出 bit-exact、每个 IP 一次 START、60 次 guard 检查通过。随后 A→B 不同输入 S1 双帧 PASS：每个 IP 两次 START、六份输出共 11,028,240 个 INT16 标量零差异、120/120 guard。`BOARD_CONTROL_ACCESS=PASS`、`BOARD_BRINGUP_BASE=PASS`、`BOARD_MULTI_FRAME=S1_TWO_DIFFERENT_FRAME_PASS`；超过两帧的持续运行与 `BOARD_30FPS=NOT_TESTED`。正式 release bit 未独立重演本次链路，保持其原始身份。

上次 D-cache 最后确认 OFF、MMU 未独立评估，连接已关闭；不把历史板态当作当前证明。下文保留正式 RTL/implementation 结果。

## 现在做到了什么

完整链路 **CNN → DDR → Bilinear → DDR → Curve** 已经在 RTL system TB 中跑通。
8 帧流水测试的稳态最差输出间隔为 **3,307,317 cycles**；按 **100 MHz** 计算，
约 **30.236 FPS**，因此三模块 **RTL 级 30FPS PASS**。

## 数值是否正确

8 帧的 CNN A_low、Bilinear A_full、Curve enhanced 都做了逐元素检查，
共比较 **44,112,960** 项：**raw mismatch = 0、guard = 0、hazard = 0**。
Phase4F 验证的是 write-credit RTL overlay；Phase4G 随后将相同的三个 writer
固化为正式 CNN IP，并完成同源单帧验证。

## FPGA 硬件是否塞得下

正式 CNN IP 已固化；Vivado **Synthesis、Implementation、Route 均 PASS**。
100 MHz 布局布线后：Setup WNS **+0.636 ns**、Hold WHS **+0.010 ns**、
Pulse WPWS **+3.500 ns**；**78,288 / 78,288** 个需布线网络全部完成。
DRC 为 **0 Error、0 Critical Warning**，另有 198 条普通 Warning，详见正式报告。

## Bitstream 有没有

已经生成并校验 **system_wrapper.bit** 和 **kv260_three_module_v1_2_writecredit.xsa**；
XSA 内含的 bitstream 与外部 bitstream 大小和 SHA-256 一致。
硬件交付资料已就绪，文件路径、大小、SHA-256、寄存器和 DDR 布局见
[硬件交付说明](v1_2_hardware_handoff.md) 与 [寄存器及 DDR 配置](v1_2_hw_register_map.json)。
构建产物保留在外部交付目录，不随源码提交到 Git。

## 现在还缺什么

**BOARD_30FPS = NOT_TESTED**：尚未进行真实连续性能测量；真板单帧及不同输入 S1 双帧已通过。
RTL 仿真、时序收敛和 bitstream 生成均不等于真板 30FPS 验收。

Master 另行批准的下一阶段需要：

1. 完成 PS 软件与真实 DDR buffer 分配。
2. 实现生产 cache clean/invalidate 或正确非缓存映射，不能沿用诊断 dcache off 当生产方案。
3. S1不同输入双帧已通过；后续双方共同确认生产调用与长期连续运行，不再安排独立S2预实验。
4. 使用板端可靠计时测量真实稳态 FPS，并检查输出数值；见 [验收计划](kv260_v12_acceptance_plan.md)。

## 当前一句话结论

目前 V1.2 已完成三模块 RTL 级 30FPS 验证、正式 CNN IP 固化、100 MHz
布局布线及时序收敛，并已生成 bitstream / XSA。PC 侧 FPGA 硬件开发基本完成，
诊断bit真板单帧与S1不同输入双帧已完成，现在开始向lzm交接；生产软件、长期运行及真实30 FPS由双方后续集成验收，最终产品尚未完成。

| 当前状态 | 结果 |
| --- | --- |
| CNN_RTL_30FPS | PASS |
| SHORT_MULTI_FRAME_30FPS | PASS |
| IMPLEMENTABLE_CNN_IP | PASS |
| POST_ROUTE_100MHZ | PASS |
| BITSTREAM_XSA | PASS |
| BOARD_CONTROL_ACCESS | PASS |
| BOARD_BRINGUP_BASE | PASS（诊断 bit 单帧） |
| BOARD_MULTI_FRAME | S1_TWO_DIFFERENT_FRAME_PASS |
| BOARD_30FPS | NOT_TESTED |

正式证据入口：[当前 checkpoint](../reports/v1_2_phase4_checkpoint.md)、
[8 帧 RTL 报告](../reports/v1_2_phase4f_short_multiframe.md)、
[正式 CNN IP](../reports/v1_2_phase4g_implementable_cnn_ip.md)、
[布局布线报告](../reports/vivado_three_module_v1_2_implementation.md)、
[bitstream / XSA 报告](../reports/vivado_three_module_v1_2_bitstream_xsa.md)。
