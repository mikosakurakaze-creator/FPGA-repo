# 联合镜像加载和调用顺序

交付边界为硬件包。包内结果若标记 `HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED`，表示联合布局布线和报告门禁通过；不表示已经上板或达到某一帧率。新同图验证包括冻结 HLS C 模型的全帧逐元素比较，以及真实融合 AXI RTL 的全帧比较；不冒充完整六核系统 RTL 仿真。

## 1. 加载前

1. 在 KV260 的 Linux/aarch64 环境准备匹配的 PYNQ 与 Vivado 2025.2 导出物支持。必须独占整片 PL，并具备安全重新配置/复位的权限。
   DMA allocator 必须能从 DDR LOW 提供全部缓冲：本入口净 payload 合计 38,257,019 字节，另需对齐和 CMA 余量。高于 `0x7FF00000` 或未对齐的分配会被入口拒绝；目标 Linux/CMA 配置须在上板时确认。
2. 使用 `sha256sum -c SHA256SUMS` 验证交付文件。核对 `manifest.json` 的状态、器件、时钟、资源/时序报告和 Golden 范围。
3. `joint_system.bit` 与 `joint_system.hwh` 必须同名配对，不能混用历史低照度、单 D 或其他联合镜像。XSA 内嵌 bit 与外部 bit 已逐字节核对。
4. 在目标板编译内存屏障库：`cd runtime && cc -O2 -shared -fPIC mmio_fence.c -o libjoint_fence.so`。这是目标机运行依赖；本机没有执行板端编译/加载。
5. 原图必须是精确 1272×720 的 decoded RGB8 HWC，长度 2,747,520 字节。不要将 JPEG 文件直接传给 IP。Golden 中的 `rgb.u8` 来自 night_01 的明确输入裁剪 `[4,0,1276,720]`；D 网络已经按 1272 宽重新运行，没有裁剪 1280 宽模型输出。

## 2. 实际控制地址

最终地址以包内从 XSA/HWH 核验生成的 `address_map.json` 为准：

| Core | Base | Range | Nominal clock |
| --- | --- | --- | --- |
| Bilinear | `0xA0000000` | 64 KiB | 100 MHz |
| Curve | `0xA0010000` | 64 KiB | 100 MHz |
| CNN | `0xA0020000` | 64 KiB | 100 MHz |
| RGB8 prepare | `0xA0030000` | 64 KiB | 100 MHz |
| Three-way fusion | `0xA0040000` | 64 KiB | 100 MHz |
| Compact D | `0xA0050000` | 64 KiB | 200 MHz |

PS 分频器实际元数据为 99,999,001 / 199,998,001 Hz；融合 IP 的时钟元数据跟随连接传播。两个时钟域分别使用同步复位；D 的控制和 DDR 通过双时钟 SmartConnect 连接。不要运行时单独改变 PL 时钟或复位某一核后继续复用旧缓冲。

综合阶段的原始 `check_timing` 报告出现 PS8 的 8 个未用 EMIO 时钟输出。最终 routed/export 的原始计数按各自报告保留；若仍出现这 8 项，必须由同一 checkpoint 的 `*_unused_ps_clocks.txt` 证明精确这组引脚零 PL 输入负载、零顶层端口，且没有其他无钟项。有效 PL 无钟引脚和未约束内部端点必须为 0。跨时钟总线的全部 bus-skew 约束也须通过。详见 `clock_coverage.md`；不改写报告计数。

本轮 routed 实测 WNS +0.032ns、WHS +0.010ns、WPWS +1.700ns；原始 no_clock 和未约束内部端点均为 0。183,014/183,014 routable nets 完整布线；17 项 bus-skew 全部通过，最差 slack +3.898ns。URAM 58/64（90.63%）为主要容量瓶颈，setup 余量只有 0.032ns；修改 IP、器件、时钟或集成后必须重新实现验收。包中同时保留原始 CDC/DRC Warning，未将完整系统 RTL 或板端运行计入已验证范围。

## 3. 单帧顺序

1. 加载整个联合 bit/HWH。通过真实 DMA allocator 为 `address_map.json` 中的全部缓冲分配独立物理内存，64-byte 对齐。完整区间必须在 DDR LOW 内；排除 PS 保留的最后 1 MiB，因此软件 allocator 上界为 `0x7FF00000`，且不得触碰 OS/其他进程的内存。
2. 写入 RGB8 和四个冻结低照度模型数组。D 参数已固化在 IP 内。所有输出及 workspace 也先交还设备所有权，避免 CPU 脏缓存覆盖 FPGA 写入。
3. 确认六核 idle，读取一次状态清除残留 done；写完整的 64-bit 物理指针 low/high word。禁止使用 CPU 虚拟地址，禁止 auto_restart。
4. 启动 prepare；等待本次 done、idle 和 `ap_return=0`。prepare 同时产生原图 I、D 归一化输入、CNN 低分辨率输入。
5. 并联启动 CNN 与 D。CNN 完成后依次启动 Bilinear、Curve。D 配置 `H=720,W=1272,cookie=0x44433031`；Curve count 为 2,747,520。
6. 仅当本次 Curve 与 D 均成功完成后启动融合。权重是三个 UINT32/Q15，分别位于 `[0,32768]`，和必须为 32768；例如 `[10923,10923,10922]`。写入 frame_id 和 `0x4A463031` cookie。运行中权重更新只作用于下一帧。
7. 等待融合 done、idle、`ap_return=0`，核对 `completed_frame==frame_id`；再 invalidation/sync_from_device，把融合输出交给 CPU。输出为 little-endian RGB NCHW INT16 Q14，5,495,040 字节。
8. 任何错误/超时都禁止启动后续融合、读出无效结果或复用相关缓冲。需要对整个 PL 复位/重新配置并确认 outstanding AXI 已静止后恢复。仅新建 Python controller 对象不构成硬件恢复。

## 4. 可运行的板端入口

在目标机编译 fence 库并确认独占 PL 后：

```sh
python3 runtime/run_pynq.py --package "$PWD" --rgb golden/rgb.u8 \
  --weights 10923 10923 10922 --timeout 120 --output result.i16
cmp result.i16 golden/fused.i16
```

入口检查包哈希和 HWH 地址，使用 PYNQ MMIO/allocate、cache ownership 与 ARM `dsb sy`，调用经过 host 测试的单帧调度器。120 秒仅为调用超时设置，不是测量耗时。发生 PL 错误后该进程保留 DMA 分配并等待人工恢复，不能在未复位/静止前强行退出或释放内存。本轮未连接目标板，以上命令尚未上板执行。
