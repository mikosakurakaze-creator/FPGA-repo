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

## 驱动

目录 `driver/compact_d_top_v1_0/` 是和此版 IP 同时生成、并由 `reports/build.json` 的 IP 文件哈希记录的 HLS 驱动。裸机接口在 `src/xcompact_d_top.c`、`src/xcompact_d_top.h`；Linux UIO 控制接口在 `src/xcompact_d_top_linux.c`；寄存器偏移在 `src/xcompact_d_top_hw.h`。其余构建/驱动元数据也一并保留。各文件 SHA-256 均列于 `SHA256SUMS`。

这是 AXI-Lite 寄存器控制驱动，不是完整 Linux 视频/DMA 驱动；它不处理物理连续缓冲区分配、cache flush/invalidate、设备树或图像采集显示。`xcompact_d_top_linux.c` 依赖系统已提供匹配的 UIO 设备节点。此驱动源码已与硬件 IP 构建记录核对，但未在目标板上编译或运行。

随包驱动文件的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `driver/compact_d_top_v1_0/src/xcompact_d_top.c` | `ae27c016cd9c7a2569987689a8fc6c8c9e747669d73ef6da021a2f7e5fd2aa87` |
| `driver/compact_d_top_v1_0/src/xcompact_d_top.h` | `b2e6ab31c1029a71aa4bc1f9ff473a162aeed6eb2383a65f79e1fb441c55761c` |
| `driver/compact_d_top_v1_0/src/xcompact_d_top_hw.h` | `1afc234f8a64dc915bff56ae391043d68b5a30c023cb7f9205d8484f15450046` |
| `driver/compact_d_top_v1_0/src/xcompact_d_top_linux.c` | `4ae64431128ed9a8bf63fc8c982620f270de9128a0c7d1cdf1a8ac9e46b59650` |
| `driver/compact_d_top_v1_0/src/xcompact_d_top_sinit.c` | `5f14cb493d6ebe53928b0fab2b00d37c66b42aa0908c312348f643c3c220f787` |
| `driver/compact_d_top_v1_0/src/CMakeLists.txt` | `770b6afec9d94bcfb03baf2ac6fbb4c55bbb431bfe9dd5adf187dba1f48697a4` |
| `driver/compact_d_top_v1_0/src/Makefile` | `5ff43b46772574a73f42eca5c2757d49918a4c8c5d4b4bb2d5933a2a3119967a` |
| `driver/compact_d_top_v1_0/data/compact_d_top.mdd` | `eaf72bfb3048fef160534fce950fd46615f0e49e4ef31c6b1a45a538e3f3b63d` |
| `driver/compact_d_top_v1_0/data/compact_d_top.tcl` | `0e5a97f37ff265f82a564358a55a327d0f0e670681190e2512eed3599235107e` |
| `driver/compact_d_top_v1_0/data/compact_d_top.yaml` | `cbb33d0903d97f542df215b7b0d64337fef9fe594604ad5435ef5a911f92f834` |

## 仿真测试台身份

报告 `reports/build.json` 的 `hls_source_sha256.test_compact_d.cpp` 为：

`8450a700ff31385afb6253cdd8511800fc23dd95512993f6ae6d4a62b7f643c9`

与报告匹配的源码副本位于 [`validation/sources/test_compact_d.cpp`](validation/sources/test_compact_d.cpp)，其落盘 SHA-256 与报告一致。仓库中的 [`../../hls/test_compact_d.cpp`](../../hls/test_compact_d.cpp) 当前 SHA-256 为：

`ce650312c6473622f2418d5281e32122d54e7d9b505f2668b273661926524303`

两份源码只差一处：仓库版在每个 `D_FRAME_PASS` 行额外打印 `work_cycles` 和 `input_cycles`；计算、输入输出比较、逐节点检查、非法调用检查均相同。因此报告中的 CSim/RTL 结果对应发布包内的 `validation/sources/test_compact_d.cpp`，后续若使用仓库版重新跑，应在新报告中记录新的源码 SHA。

## 验证范围

已随包保留 HLS/CSim/RTL、小尺寸及最大宽度输出证据、综合/实现/时序/布线报告和参数清单。完整 720p RTL、真板连续帧和 30 FPS 尚未作为本包已完成结果声明；详见 [`README.md`](README.md) 和 `reports/`。
