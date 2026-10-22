# K26 天气恢复硬件发布包

## 可直接使用的文件

| 文件 | 用途 |
|---|---|
| `weather_system.bit` | Vivado Hardware Manager/JTAG 下载的原始 bitstream |
| `weather_system.bit.bin` | Bootgen 由本次 bitstream 转换的 FPGA Manager 二进制文件 |
| `weather_system.xsa` | 与 bitstream 匹配的 Vivado Hardware Platform，含 `system.hwh`、PS 初始化和生成驱动 |
| `weather_system.hwh` | 从同一 XSA 原样提取的系统元数据 |
| `ps_init/` | XSA 内嵌的 `psu_init.*`，供 PS 初始化流程参考 |
| `drivers/` | XSA 内嵌的四个 IP 驱动源和硬件头文件 |
| `reports/` | 本次导出产生的时序、布线、DRC、接口审计和构建身份报告 |
| `manifest.json` | 工具、器件、来源提交、文件哈希和验证范围 |
| `SHA256SUMS` | 发布目录文件的 SHA-256 清单 |

## 硬件身份

- 器件：`xck26-sfvc784-2LV-c`，板卡：KV260/K26。
- 工具：Vivado/Bootgen 2025.2。
- 时钟：100 MHz；post-route setup WNS `+1.018 ns`，hold WHS `+0.010 ns`，pulse-width WPWS `+3.500 ns`。
- 路由：`169,908` 条需布线网络全部完成，路由错误为 0。
- DRC：832 条非阻断 Warning；Error 和 Critical Warning 为 0。
- 导出核验：XSA CRC、XSA 内嵌 bit、独立 HWH、驱动文件和 BIN 转换均已逐字节检查。

## 当前系统接口

天气整帧核基址为 `0xA0030000`，使用两路 DDR master：输入经 HP0 读取，输出经 HP3 写回；没有 AXI Stream 和外部 scratch。输入输出均为连续 RGB NCHW、有符号 INT16 Q14，尺寸范围 `H=1..720`、`W=1..1280`；`task=0` 去雨，`task=1` 去雾。寄存器和缓存所有权合同见 [接口合同](../../../docs/weather_frame_v2_contract.md) 与 [上板联调说明](../../../docs/board_bringup.md)。

低照度 CNN/Bilinear/Curve 仍在同一组合设计中，控制基址依次为 `0xA0020000`、`0xA0000000`、`0xA0010000`。天气核输出是增强后的全分辨率 RGB，不是 `A_low` 参数图。

## 使用边界

本次复用已完成的综合、布局布线和 bitstream；重新用 Vivado 打开布线后实现，执行时序/路由/DRC 检查并导出 XSA，再用 Bootgen 转换 BIN。没有重新执行综合和布局布线。

当前没有在真实 KV260 上下载、启动或测量帧率，也没有生成 A53 standalone ELF、Linux 设备树或 BOOT.BIN。本机缺少 A53 Embedded 编译器；[PS 控制器及最小测试源](../../../deployment/README.md) 与 [构建入口](../../../tools/run_standalone.py) 已在仓库中。下游需用本目录 XSA 创建匹配 PS 平台并编译测试应用。该 BIN 仅是 PL 配置数据，不能当作 SD 启动用 BOOT.BIN。

Linux 加载还需板卡镜像支持的固件、设备树和时钟/复位配置；HWH 本身不能代替这些配置。JTAG 下载 bit 也不能代替 PS/DDR 初始化。首次联调按上板说明串行运行一个模式，先执行 Golden 测试，再接入连续视频、摄像头和显示链路。当前没有 ILA，因此不提供 LTX。

在使用前运行：

```powershell
python tools/board_artifacts.py verify --release board/releases/k26_weather_v2_20261022
```

上述命令在仓库根目录执行，只使用 Python 标准库，不连接板卡。成功终点为 `WEATHER_BOARD_RELEASE_PASS`。Git 配置已固定本目录文件字节，避免换行转换改变 SHA-256。

## 重新导出

在保留完整工程的构建机上，以仓库根目录为工作目录，使用新的空输出路径：

```powershell
vivado -mode batch -source system/export_board.tcl -tclargs D:/weather_builds/stream_system01 D:/weather_builds/board_export_new
```

进入新输出目录，复制本目录的 `fpga.bif`，执行：

```powershell
bootgen -arch zynqmp -image fpga.bif -process_bitstream bin -w on
```

此步骤依赖完整的已实现 Vivado 工程；本目录用于下载和 PS 平台构建，不包含大型 DCP/缓存。`reports/build.json` 保留原始工程输入的哈希和执行记录，`reports/vivado_export_console.txt` 与 `reports/bootgen_console.txt` 保留本次导出日志。
