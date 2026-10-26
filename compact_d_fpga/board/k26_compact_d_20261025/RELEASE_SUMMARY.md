# D 镜像最终上板包摘要

本目录对应 `k26_compact_d_20261025` 独立 D 镜像。以下文件来自同一份 XSA/导出结果，文件哈希以 `SHA256SUMS` 为准。

## 上板文件

| 文件 | 用途 | SHA-256 |
|---|---|---|
| `compact_d_system.bit` | Vivado/JTAG 位流 | `3e076ffe48e56e641e844a7059192d3c96659e16c7ff5d698f561046fc031f2d` |
| `compact_d_system.bit.bin` | FPGA manager / bootgen 位流 | `0dafda6544215e6f9b8a424aa3f0937cbb32a23eeee0fe2503de088f65b2b74b` |
| `compact_d_system.xsa` | 硬件平台，内含同版 bit 和 `system.hwh` | `20811f06bbf5500c4dbdf4a0bd34b2eb1caa7deeb26c47f26853b036081000f4` |
| `compact_d_system.hwh` | PYNQ/Vitis 硬件描述 | `c2711830c46d1f0c89a989d91de15ed4ae1b1f7fec2f6f6e4503936e4461c95e` |

`bit.bin` 是 `bit` 配置载荷的 bootgen 转换形式；`XSA` 内嵌 bit 与外部 `compact_d_system.bit` 已逐字节核对，`XSA` 内 `system.hwh` 与外部 HWH 也已逐字节核对。

## 接口合同

- 寄存器表和数据布局：[`INTERFACE.md`](INTERFACE.md)。控制基址为 `0xA0050000`，ABI cookie 为 `0x44433031`。
- C 头文件：[`xcompact_d_top_hw.h`](xcompact_d_top_hw.h)。
- 输入主接口 `m_axi_gmem_in` 连接 PS HP0，输出主接口 `m_axi_gmem_out` 连接 PS HP3；PS HP 数据宽度为 128 bit，DDR 地址窗口为低 2 GiB。
- PL 时钟目标为 200 MHz，HWH 实测 `199998001 Hz`；布线后 setup WNS `+0.328 ns`、hold WHS `+0.010 ns`。
- 复位为同步域内低有效 `ap_rst_n`，由 `pl_resetn0 -> proc_sys_reset -> peripheral_aresetn` 提供；PS 中断未连接，调用侧轮询 done/idle。

## 仿真测试台身份

报告 `reports/build.json` 的 `hls_source_sha256.test_compact_d.cpp` 为：

`8450a700ff31385afb6253cdd8511800fc23dd95512993f6ae6d4a62b7f643c9`

与报告匹配的源码副本位于 [`validation/sources/test_compact_d_report_8450a700.cpp`](validation/sources/test_compact_d_report_8450a700.cpp)，其落盘 SHA-256 与报告一致。仓库中的 [`../../hls/test_compact_d.cpp`](../../hls/test_compact_d.cpp) 当前 SHA-256 为：

`ce650312c6473622f2418d5281e32122d54e7d9b505f2668b273661926524303`

两份源码只差一处：仓库版在每个 `D_FRAME_PASS` 行额外打印 `work_cycles` 和 `input_cycles`；计算、输入输出比较、逐节点检查、非法调用检查均相同。因此报告中的 CSim/RTL 结果应引用发布包内的 `test_compact_d_report_8450a700.cpp`，后续若使用仓库版重新跑，应在新报告中记录新的源码 SHA。

## 验证范围

已随包保留 HLS/CSim/RTL、小尺寸及最大宽度输出证据、综合/实现/时序/布线报告和参数清单。完整 720p RTL、真板连续帧和 30 FPS 尚未作为本包已完成结果声明；详见 [`README.md`](README.md) 和 `reports/`。
