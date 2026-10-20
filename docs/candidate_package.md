# C8 天气恢复候选与计算 IP

本文记录原始软件候选和 A 组 ABI v1 tile IP。当前组合整帧 v2 的构建、布线后时序和 bit/XSA 身份见 [流水版报告](stream_revision_20261020.md)，历史串行版见 [系统集成记录](system_integration_20261020.md)。组合系统实例化一个包含两任务的整帧核，没有同时实例化两个原 v1 tile IP。

## 软件候选身份

- 源基线：远端 `feat/software`，提交 `b4aa1834fd74b483761a5ccdb1224b65c497366f`。
- 内层软件归档：`hardware_candidates/c8_hardware_candidates_v1.zip`。
- 归档 SHA-256：`9330dbfa20fd4b4e7899d61ecce0d01b7e667c2e66120ce1a74a1e5a3eda0e88`。
- 内层清单状态：`CANDIDATE_NOT_FPGA_VALIDATED`，指 A 组开发计算核之前的软件候选状态。

## 网络与整数算术

TinyRestore C8 包含 3x3 RGB stem、五个深度可分离残差块和 1x1 RGB 残差 tail，共 1,011 个标量参数：920 个权重、91 个偏置。去雨和去雾图结构相同，权重和缩放参数不同。

- 图像 tile：连续 RGB NCHW、小端有符号 INT16 Q14。
- 权重：有符号 INT8 OIHW，每个输出通道独立指定小数位，编译进对应固定任务 IP。
- 偏置与 MAC 累加器：有符号 INT32。
- 激活：有符号 INT16，按节点使用各自的小数位。
- 重缩放：最近值舍入，恰好一半取偶数，随后在整数图规定阶段执行有符号 INT16 饱和。
- 残差两条分支先分别重缩放再相加，ReLU 在指定求和之后执行。
- 输出：RGB Q14，钳位到 `[0,16384]`。

A 组 top 接收 1x1 至 140x140 连续 tile；推荐整帧调度为 128x128 输出 core、halo 6。官方打包 Golden 为 96x96，A 组另验证过主机 tile 路径和拼缝/边缘。A 组 8x8 RTL 用例不等于全分辨率 RTL 帧。

## A 组计算核交付

最终 HLS 包解压在 `../ip_repo/`，原 ZIP 位于 `../ip_archives/`。`derain_top` 和 `dehaze_top` 各自包含固定任务参数，对外提供三个 DDR master、AXI-Lite 控制、时钟/复位和中断，无运行时权重口或 AXI Stream。

软件候选估计：未分块的 720x1272 C8 图像约 0.843 GMAC，含 tile 重叠约 0.990 GMAC；30 FPS 对应约 29.7 GMAC/s。这是模型工作量，不是 HLS 周期或真板 FPS。

## 验证证据范围

A 交付审查记录两任务各 30 个图节点误差 0 LSB，官方输出 C 仿真、综合、IP 打包，以及每任务一次 491,134 拍的 8x8 Verilog RTL 联合仿真。去雨 HLS 估算为 16,570 LUT / 10,680 FF / 11 BRAM18K / 37 DSP；去雾为 17,163 LUT / 10,775 FF / 11 BRAM18K / 37 DSP。7.3 ns 是针对 10 ns 请求的 HLS 估算。

若同时实例化原两个固定 IP，其 HLS 资源算术和为 33,733 LUT、21,455 FF、22 BRAM18K、74 DSP，尚未包含旧低照度设计、互连、时钟/复位或顶层逻辑。该算术和不代表当前组合系统。A 组 ABI v1 原交付没有整机布局布线证据；当前整帧 v2 的结果见系统报告。真板运行、持续吞吐和整帧真板画质仍待验证。
