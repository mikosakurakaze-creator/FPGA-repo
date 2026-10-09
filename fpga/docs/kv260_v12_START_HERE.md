# START_HERE：KV260 V1.2 → lzm

2026-10-09。可以开始软件端集成；真实30 FPS与正式Linux执行尚未验收。

| 状态 | 结果 |
| --- | --- |
| BOARD_BRINGUP_BASE | PASS |
| BOARD_MULTI_FRAME | S1_TWO_DIFFERENT_FRAME_PASS |
| BOARD_30FPS | NOT_TESTED |

真实KV260已经完成CNN → Bilinear → Curve单帧完整计算，以及A/B不同输入S1双帧。各模块两次启动，六输出11,028,240个INT16全量零差异，120/120 Guard通过；冷启动最小恢复曾成功复现。当前成功路径依赖JTAG/U-Boot诊断环境，不是可直接运行的Linux生产系统。

## 从这里开始

1. [软件交接与完整ABI](kv260_v12_software_handoff.md)：bit身份、寄存器、shape/bytes、数据流、冷启动及Cache/同步。
2. [便携寄存器映射](kv260_v12_register_map.json)与[真实板测摘要](../reports/kv260_v12_board_validation.md)：机器字段和可追溯证据。
3. [Linux源码与Host测试](../tools/kv260_v12_linux_perf/README.md)：计时/槽接口、native C校验和构建说明。Backend仍未实现；不是完整驱动。
4. [Linux backend审阅](kv260_v12_linux_backend_review.md)与[runtime替代方案](kv260_v12_runtime_alternative_review.md)：启动/DMA材料及下一阶段约束。
5. [独立大文件清单](kv260_v12_large_artifacts.md)与[实体交板清单](kv260_v12_delivery_checklist.md)：Git之外的bit/XSA/A/B/Golden/真实输出及交付渠道。

## 首个软件里程碑

lzm牵头确认完整Linux boot/rootfs、匹配kernel/DT、PL加载及clock/reset策略，随后集成独占DMA/MMIO资源驱动、buffer分配和Cache同步。硬件端提供已验证设计、接口、数据及问题支持。双方共同验收30 FPS，当前不预判瓶颈责任。

本次成功使用的诊断bit SHA256：
`347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86`。
正式Phase6 bit/XSA是另一组文件；目前没有诊断bit配套XSA。不得因为正式XSA可用就把它当诊断image的已验证Linux平台。

## 执行边界

旧go性能方案已停止，不推荐执行。Host mock、候选headers和未实现driver均不是板端验收。Git克隆不含完整大文件数据或Linux启动镜像；本次不开展新板测，任何程序/驱动装载、CPU/Cache/DDR/CSR/PL/启动操作须按新精确范围另行批准。
