# 整帧流水计算核

此实现使用整帧 DATAFLOW 流水线替换按 tile、按层串行执行的方案。它是独立候选，已完成布线的 `frame04/system02` 功能基线仍保留；旧基线的验证结果不能代替此源码的验证。

外部继续采用同一 ABI：RGB NCHW、有符号 INT16 Q14 输入输出、两个 DDR master、H=1..720、W=1..1280、task 0 去雨/task 1 去雾，以及原 CSR 映射。权重、算术、逐节点舍入、饱和和网络拓扑保持原规则。每个空间阶段使用两行缓存和一个 3x3 寄存器窗口；原 RGB 随中心特征一起传递，最终残差相加无需整帧大小的旁路 FIFO。每层独立加入零 padding，在产生有效输出前覆盖旧行状态。

每个方向的三个 2048 样本 FIFO 负责平面 DDR 行 burst 与 RGB 像素之间的重排。其深度能容纳 1280 像素行，避免颜色 FIFO 过小引起循环等待。层间 FIFO 在 RTL 中容量有限；可移植主机执行使用顺序、无界 FIFO，不能证明 RTL 无死锁，因此必须验证连续调用 RTL。

先运行 `scripts/verify_host.py --cxx ... --delivery ... --output NEW --full-frame`，再通过 `../../tools/run_windows_desktop.py` 启动 `scripts/run_hls.py --host-report NEW/verification.json ...`。当前源码和脚本的哈希必须与主机报告匹配。可移植测试宏只提供主机 FIFO/数据包类型；实际综合使用 `hls::stream` 和打包的 `ap_uint<176>`。

验收要求两模型 Golden 节点/完整帧、厂商 CSim/RTL、带 AXI 停顿的任务/尺寸/越界保护回归，以及 100 MHz 下低于 3,333,333 拍的完整帧周期证据和新的组合系统实现。仅有请求 II=1 的 pragma 不能证明 720p30 或真板通过。

当前证据（2026-10-21）：`work/stream_host02`、`stream02`、`stream_sequence01`、`stream_rtl01` 和 `stream_driver01` 均通过。两任务完整 720p RTL 在独立 DDR 模型下各为 3,009,677 拍；新组合系统 `D:/weather_builds/stream_system01` 在名义 100 MHz 下完成布线，WNS +1.018 ns、WHS +0.010 ns。最终 bit/XSA 状态和未执行的 PS/真板验收见 `../../docs/stream_revision_20261020.md`。尚无真板帧率结果。
