# KV260 三模块 V1.2 当前进度

更新：2026-10-03。供 Master、LZM、WZH、老登和其他队友快速了解当前交付状态。

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

**BOARD_30FPS = NOT_TESTED**：还没有在真实 KV260 上测试。
RTL 仿真、时序收敛和 bitstream 生成均不等于真板 30FPS 验收。

板到后、Master 另行安排的下一阶段需要：

1. 完成 PS 软件与真实 DDR buffer 分配。
2. 处理 cache flush / invalidate 并下载 bitstream。
3. 验证 CNN → Bilinear → Curve 单帧数值。
4. 测量 100+ 帧的真实稳态 FPS，并检查最终夜景图像输出。

## 当前一句话结论

目前 V1.2 已完成三模块 RTL 级 30FPS 验证、正式 CNN IP 固化、100 MHz
布局布线及时序收敛，并已生成 bitstream / XSA。PC 侧 FPGA 硬件开发基本完成，
下一阶段是 KV260 真板 bring-up 和真实 30FPS 验收；最终产品尚未完成。

| 当前状态 | 结果 |
| --- | --- |
| CNN_RTL_30FPS | PASS |
| SHORT_MULTI_FRAME_30FPS | PASS |
| IMPLEMENTABLE_CNN_IP | PASS |
| POST_ROUTE_100MHZ | PASS |
| BITSTREAM_XSA | PASS |
| BOARD_30FPS | NOT_TESTED |

正式证据入口：[当前 checkpoint](../reports/v1_2_phase4_checkpoint.md)、
[8 帧 RTL 报告](../reports/v1_2_phase4f_short_multiframe.md)、
[正式 CNN IP](../reports/v1_2_phase4g_implementable_cnn_ip.md)、
[布局布线报告](../reports/vivado_three_module_v1_2_implementation.md)、
[bitstream / XSA 报告](../reports/vivado_three_module_v1_2_bitstream_xsa.md)。
