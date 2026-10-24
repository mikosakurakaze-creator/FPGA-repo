# K26 GridDehazeNet Reduced Hardware Release

这是给下游上板同学使用的五核 K26 硬件候选：保留原有 CNN、Bilinear、Curve、Weather 和新增 GridDehazeNet。`griddehaze_system.bit` 与 `griddehaze_system.xsa` 来自同一次 Vivado 2025.2 implementation/export。

## 已完成

- 实际综合与布局布线通过；100 MHz routed timing：WNS `+0.729 ns`、WHS `+0.010 ns`、WPWS `+3.500 ns`。
- 191,089/191,089 routable nets 完成；write-bitstream 前 DRC 为 0 Errors。
- 实际生成 Verilog/ROM 源码审计通过，五个核均在同一系统中。
- XSA 内嵌 bit 与目录中的 bit 逐字节一致；文件哈希见 `SHA256SUMS`。

## 使用边界

本包按用户要求采用 reduced gate，以尽快交付可加载的平台文件。33x47 冷/暖双帧跨 tile RTL 回归、布线后新核数值回归、旧核连续帧回归和真板验收本轮未完成，不能把本包称为完整数值 release。下游上板后仍需验证 DDR、DMA、缓存一致性、输入输出 ABI 和实际画面。

Linux 驱动、设备树、上传流程和 HDMI 不在本包范围。新核控制基址为 `0xA0040000`，完整接口合同位于 `experiments/griddehaze_frame/docs/frame_interface.md`。

## 文件

- `griddehaze_system.bit`：五核系统 bitstream。
- `griddehaze_system.xsa`：包含 bit 的硬件平台。
- `griddehaze_system.hwh`：从同一 XSA 提取的硬件描述。
- `xgriddehaze_frame_top_hw.h`：同版控制寄存器头文件，供下游软件适配参考。
- `frame_interface.md`：新核 AXI 控制和 DDR 地址合同。
- `routed_timing.rpt`、`routed_utilization_summary.rpt`、`routed_drc.rpt`、`route_status.rpt`：实现阶段证据。
- `compiled_sources_audit.json`：五核实际生成源码/ROM 审计。
- `release_manifest.json`、`SHA256SUMS`：构建来源和文件哈希。
