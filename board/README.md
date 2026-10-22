# 板端文件

当前可供下游上板的 KV260/K26 硬件发布目录：

[releases/k26_weather_v2_20261022](releases/k26_weather_v2_20261022/README.md)

目录内的 `weather_system.bit` 用于 Vivado Hardware Manager/JTAG，
`weather_system.bit.bin` 用于支持 FPGA Manager 的 Linux 加载流程，
`weather_system.xsa` 用于按同一硬件平台创建 Vitis/PS 软件，
`weather_system.hwh` 用于需要 HWH 元数据的 overlay 工具。

该版本目标器件为 `xck26-sfvc784-2LV-c`，Vivado/Bootgen 版本为 2025.2，PL 名义时钟为 100 MHz。发布目录中的 `manifest.json`、`SHA256SUMS` 和 `tools/board_artifacts.py verify` 用于确认所有文件仍属于同一份已布线设计。

当前包没有 ILA，因此没有 LTX；没有在本机生成 A53 ELF、BOOT.BIN，也没有完成真板、摄像头、显示或持续视频测试。下游需要用 XSA 创建匹配的 PS 应用和板卡启动流程。
