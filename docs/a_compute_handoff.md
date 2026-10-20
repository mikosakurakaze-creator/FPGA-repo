# A 组计算核交接说明

本文保留 A 组原始 C8 交付和 B 侧早期接入阶段的记录。当前流水版与组合系统的后续结果见 [修正报告](stream_revision_20261020.md)，下文历史待办不能作为当前状态清单。

## 交付身份

本文记录本目录整理的 A 组 C8 计算核交付。原交付相对独立工作目录根路径为 `../weather A/weather_A_C8_delivery/`，其中 `DELIVERY_MANIFEST.json` 包含 3,179 份文件，已逐份检查大小和 SHA-256。

本机没有最外层 `weather_A_C8_delivery.zip`。其哈希附文件声明大小为 95,963,841 字节，SHA-256 为 `63cd6c2a00b1ce8b7de6b48d4a439d30b5291b3ff6ac0c1cd2dc4d5509a8ccd3`。附文件与干净重建报告记录的预期归档身份一致，但缺少原 ZIP，无法独立重算该哈希。

已独立核对的软件候选为 `weather_restore_lab/hardware_candidates/c8_hardware_candidates_v1.zip`：

- SHA-256：`9330dbfa20fd4b4e7899d61ecce0d01b7e667c2e66120ce1a74a1e5a3eda0e88`。
- 124 个成员，另含内嵌清单。
- 候选清单状态：`CANDIDATE_NOT_FPGA_VALIDATED`。

该候选包用于追溯软件和模型来源，不能替代最终 A 组 HLS 源码、生成 IP 或系统验证。

## 计算接口合同

`derain_top` 和 `dehaze_top` 是两个参数固定的 TinyRestore C8 核。它们的 ABI 相同，权重与逐节点缩放参数不同，每次接收一个连续 tile：

```c
int derain_top(const int16_t *input, int16_t *output,
               int16_t *scratch, int height, int width);
int dehaze_top(const int16_t *input, int16_t *output,
               int16_t *scratch, int height, int width);
```

tile 采用连续 RGB NCHW、小端有符号 INT16 Q14。输入和输出各含 `3*height*width` 个元素；scratch 为三个八通道工作平面，共 `24*height*width` 个 INT16 元素。高、宽合法范围分别为 1..140。尺寸非法时返回状态 1，不访问指针；有效结果返回 0，输出钳位至 Q14 `[0,16384]`。

推荐整帧调度采用 128x128 有效输出 core、halo 6。720x1272 对应 6x10，即 60 次调用。IP 不支持整帧 stride 或 AXI Stream，因此需收集连续 tile，再裁剪并回写有效 core。

## 已核验的 A 组证据

本地复核报告为 `work/a_delivery_audit_rerun.json`，143/143 项检查通过，已核实：

- 两任务各 30 个图节点在所提供 Golden 用例上误差均为 0 LSB。
- 两任务官方 96x96 Vitis C 仿真通过。
- Vitis Unified 2025.2 综合和 IP 打包完成。
- 8x8 Verilog RTL 联合仿真通过，每个任务均为 491,134 拍。
- 最终 IP ZIP 与解压后的 IP 仓库逐字节一致。

最终 HLS 估算如下：

| 任务 | LUT | FF | BRAM18K | DSP | 估算周期 |
|---|---:|---:|---:|---:|---:|
| 去雨（derain） | 16,570 | 10,680 | 11 | 37 | 7.3 ns |
| 去雾（dehaze） | 17,163 | 10,775 | 11 | 37 | 7.3 ns |

7.3 ns 是针对 10 ns 目标的综合估算，不是布线后时序或真板频率。491,134 拍是单次 8x8 RTL 事务的结果，不能证明连续启动间隔、全分辨率延迟或帧率。

## 集成边界

选定的任务 IP 需通过独立 AXI-Lite 控制地址和三个 DDR master 接入现有系统。精确 CSR 与总线元数据以生成的驱动头文件和 `component.xml` 为准，不能直接套用旧低照度 CNN 的基地址或偏移。交付驱动不包含部署用 Linux DMA 分配、缓存所有权、超时恢复或 Vivado BD。

天气输出是全分辨率增强 RGB Q14，不产生 `A_low`，不能进入低照度 Bilinear/Curve。系统负责人定义自动策略前，手动旁路、低照度、去雨和去雾分别作为独立模式。

## 原交接阶段的后续验收要求

以下工作原由 B 侧承担，必须单独提供证据；当前完成情况见流水版报告：

1. 在获授权的功能工作目录中导入 Vivado，分配地址，连接 AXI 互连、时钟/复位和中断。
2. 实现 tile 数据收集/回写、DMA/缓存所有权、MMIO 顺序、超时与恢复。
3. 系统数值测试覆盖所给 Golden、拼缝/边缘 tile、完整 720x1272，以及连续两个不同输入。
4. 提供低照度与天气组合设计的综合、实现、布线后时序、DDR 带宽和资源报告。
5. 提供计算、传输、端到端延迟、持续吞吐、丢帧、缓存行为、采集/显示及低照度共存的真板证据。

A 组原交付包本身不表示上述系统验收已经完成。

## B 侧早期跟进记录（2026-10-20）

B 侧当时已新增可移植 C11 控制器/tile 适配器和实验整帧核。主机 MMIO/DMA 模拟、两任务各 30 节点 Golden 和整帧数值比较通过。当时这些新增工作没有扩展 A 包本身的硬件验证范围，新核 HLS/RTL、板端 DMA/cache 绑定与系统实现仍待进行。该段为早期状态，详见 [B 侧进展报告](b_progress_report.md)；后续已执行的 HLS、RTL 和布局布线见本文开头的当前报告。
