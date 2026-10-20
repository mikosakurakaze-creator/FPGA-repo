# K26 联调入口

## 本轮交付的范围

最终候选目录中的 `weather_system.bit` 与 `weather_system.xsa` 必须来自同一份构建；`manifest.json` 给出文件大小和 SHA-256。XSA 内嵌的 bit 还会与外部 bit 逐字节核对。当前流水版的最终状态、时序数值与文件位置见 [修正记录](stream_revision_20261020.md)；`system_integration_20261020.md` 为旧串行版历史。

此系统沿用原低照度 PS 配置，增加 Weather Frame 控制口 `0xA0030000`。Weather 输入读 HP0、输出写 HP3，图像为 RGB NCHW signed16 Q14。初次联调串行运行一个模式；低照度参数图路径与天气 RGB 路径各自独立。

## 1. 准备 PS 软件

本机缺少 Vitis Embedded 的 A53 standalone 工具链，目前没有构建成功的 ELF。需要匹配 2025.2 的 Embedded/AArch64 组件，包含 `aarch64-none-elf-gcc`、standalone BSP 和 Vitis Embedded 平台构建功能。只有 HLS/Vivado 组件不能完成该步。

在完整工具环境中，用当前 XSA 和新的空输出路径运行：

```powershell
& 'D:/Dev/Miniconda3/python.exe' tools/run_windows_desktop.py -- `
  'D:/Dev/Miniconda3/python.exe' tools/run_standalone.py `
  --xsa 'D:/weather_builds/stream_system01/weather_system.xsa' `
  --workspace 'D:/weather_builds/stream_ps_workspace01' `
  --output 'D:/weather_builds/stream_ps_build01' `
  --vitis 'D:/vivado/2025.2/Vitis'
```

命令以工作目录根目录为例；候选包中的对应工作目录是 `recipe/`，XSA 改为候选包内的实际绝对路径。此构建入口不会连接、复位或编程板卡。

## 2. 启动条件

使用 KV260/K26 当前支持的固件与启动流程，完成 PS、DDR、PL 时钟/复位初始化，再加载本次 bit，并通过匹配 XSA 的 Vitis 平台显式启动 ELF。裸机 app 不执行 PS 初始化、PMU 管理或 bitstream 配置。不要将此裸机 app 当成 Linux 用户态程序，也不要在 Linux 正在使用这些 DDR/寄存器时直接启动它。

初次只跑内存 Golden 测试。两个最大帧缓冲区是链接器分配、独立 64-byte 对齐、identity-mapped 的低 DDR；软件会执行实际缓存同步与设备 MMIO。`[0,2 GiB)` 是硬件可达窗口，不是可任意覆盖的空闲区。

当前 smoke 只调 Weather。保留的低照度链仍需要原有软件正确加载输入/模型 DDR、分配中间缓冲区并依次调度 CNN/Bilinear/Curve；本轮没有将该旧链的 PS 运行或三模块端到端板测写成已验证。

## 3. 判定结果

保留串口原始输出、bit/XSA/ELF 哈希、板卡型号、启动方式和实际时钟。app 按 task 0→1→0 连续调用，不在调用之间 reset，检查官方 8×8 Golden、输入不变性和输出缓冲区尾部 guard。成功终点为：

```text
WEATHER_SMOKE_PASS frames=3 tasks=0,1,0
```

任何失败或超时都会停止应用；超时缓冲区被隔离，不自动 reset 或复用。IP reset 本身不能证明之前的 DDR 事务已排空。

## 4. 接下来的验收

单次 smoke 通过后，再扩展真板上的尺寸切换、跨 128 边界、720p、连续帧和实际画质/测时。分别记录 CPU 准备/缓存操作、PL 启动到完成、结果取回和端到端时间。

当前尚无真板、连续视频、720p 持续 FPS、Linux DMA 驱动、摄像头采集或显示链路的通过证据。100 MHz 时序通过也不表示达到目标帧率。
