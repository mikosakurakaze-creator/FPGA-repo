# KV260 V1.2 验收状态与后续分工

2026-10-09。当前阶段为向lzm交接现有可用FPGA成果；不继续开发FPS实验框架，不进行新板端操作。性能未验收不阻止软件接口交接。

| 验收层 | 当前结果 |
| --- | --- |
| 正式RTL/实现/bit-XSA | 已有权威报告；保留release身份 |
| 真板单帧完整三模块 | PASS |
| 真板S1 A/B双帧 | S1_TWO_DIFFERENT_FRAME_PASS |
| BOARD_BRINGUP_BASE | PASS |
| BOARD_30FPS | NOT_TESTED |
| 长时间连续运行/Linux驱动/相机显示 | NOT_TESTED / NOT_IMPLEMENTED |

[真实板测摘要](../reports/kv260_v12_board_validation.md)绑定原始证据与输出身份。RTL仿真FPS、Host mock、Windows/JTAG数据搬运/轮询和调试会话总时长不能更新BOARD_30FPS。

## 后续真实性能验收

由双方共同完成：lzm牵头完整Linux启动、驱动、DMA buffer/Cache和调用链，硬件端提供设计与接口并支持硬件问题。先确认实际11路AXI master跨4HP的地址域/所有权，构建并冻结真实backend，再申请完整精确执行范围；旧go批准不沿用。

现有候选接口保留两段各6预热+120有效帧，可由双方按实际产品路径审核后确定。需真实更新输入、三模块实际计算、验证全部输出和Guard，记录硬件时钟源/频率依据、有效/预热帧数、计时边界、总时长/FPS、mean/max/p95/p99、各模块启动/完成/错误、输入变化及终态。

区分IP软件观察窗口、串行service、DDR/PS/cache/control/交换与验证额外开销、真实连续吞吐。不得相加/减去分段耗时拼出持续FPS；无内部PL计数器时，软件窗口不能拆为纯算术和DDR stall。当前边界为预量化Q14内存输入→enhanced DDR输出，不覆盖相机到显示。

低于30 FPS时先判断PL、PS控制、DDR/Cache或测试校验竞争，提出最小修复；不立即重建工程，不预先归责任一方。异常立即停止新增start，不自动retry/reset/reprogram。

当前共享材料：[START_HERE](kv260_v12_START_HERE.md)、[交接说明](kv260_v12_software_handoff.md)、[后端审阅](kv260_v12_linux_backend_review.md)、[交板清单](kv260_v12_delivery_checklist.md)。
