# 时钟与复位说明

来自本包实际 HWH、地址审计和同次新实现；不得和旧镜像混用。

| 核 | 基址 | 频率/Hz | 时钟 | 低有效复位 |
| --- | --- | --- | --- | --- |
| bilinear | 0xA0000000 | 99999001 | zynq_ultra_ps_e_0_pl_clk0 | rst_ps_100m_peripheral_aresetn |
| curve | 0xA0010000 | 99999001 | zynq_ultra_ps_e_0_pl_clk0 | rst_ps_100m_peripheral_aresetn |
| cnn | 0xA0020000 | 99999001 | zynq_ultra_ps_e_0_pl_clk0 | rst_ps_100m_peripheral_aresetn |
| prepare | 0xA0030000 | 99999001 | zynq_ultra_ps_e_0_pl_clk0 | rst_ps_100m_peripheral_aresetn |
| fusion | 0xA0040000 | 99999001 | zynq_ultra_ps_e_0_pl_clk0 | rst_ps_100m_peripheral_aresetn |
| d | 0xA0050000 | 199998001 | zynq_ultra_ps_e_0_pl_clk1 | rst_ps_d_peripheral_aresetn |

PS HPM 控制侧及 HP0–HP3 数据侧工作于约 100 MHz。D 的约 200 MHz 域经双时钟 SmartConnect 连接控制/读/写通路。各核之间通过同一片 DDR 的不同缓冲区交接；D 内部层间使用片上 FIFO。

PS/pl_resetn0 低有效复位送入两组 proc_sys_reset，各自在所属时钟域同步释放。超时或 AXI 失败后作废输出，停止新启动，待所有 outstanding 静止或完成全 PL 恢复后才复用缓冲。

本次 routed WNS=0.391 ns，WHS=0.1 ns；完整覆盖、CDC、DRC、bus-skew 及 route 见 reports/。这是新流水融合的联合实现结果。
