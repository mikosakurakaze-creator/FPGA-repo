# D 核硬件接口

本合同对应独立 D 镜像，控制基址 `0xA0050000`，目标时钟 200 MHz。以实际交付的 XSA、HWH、`xcompact_d_top_hw.h` 和镜像 SHA 为最终绑定。旧 Weather/Grid/低照度镜像保留在各自工程；此 D 镜像只包含 PS、D 和必要互连。

## 数值与存储

- A bundle：`2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`。
- 参数 SHA256：`b30ccd73ad10a685db4c591d3c4a31286178bc80be8e65ff3801364458706e57`。参数固定在 bit 内，不从 DDR 动态装载。
- 输入/输出均为 `[1,3,H,W]`、RGB、连续 NCHW、小端 signed INT16；字节偏移 `2*((c*H+y)*W+x)`，无行 padding/stride。
- `1<=H<=720`、`1<=W<=1280`；极小和奇数尺寸有效。
- 输入 F14、合法整数范围 `[-16384,16384]`；隐藏 F13；输出 F14，整数范围 `[0,32767]`。输出在显示转换前可以大于 16384。
- 保留 A 的 RHAZ、卷积后饱和、残差饱和、最终 ReLU 次序；37 位累加由 A 的溢出界证明支持。
- 中间特征、残差及 RGB 旁路在片上行缓存/FIFO 中流动，无 DDR 中间 scratch。

## DDR 与控制

`m_axi_gmem_in` 经 SmartConnect 连接 PS HP0；`m_axi_gmem_out` 经独立 SmartConnect 连接 HP3。HLS master 为 32-bit 数据、64-bit 地址；PS HP 为 128-bit，SmartConnect 转换数据宽度。已配置的访问窗口为 `[0,0x80000000)`；完整缓冲范围必须落在窗口内。

调用侧提供两个互不重叠的物理连续 DMA 缓冲区，推荐基址按 64 bytes 对齐；每个缓冲区至少 `6*H*W` bytes。不能原位覆盖输入。720p 每个缓冲区 5,529,600 bytes，两份共 11,059,200 bytes，约 10.55 MiB。这里是核所需容量，不代表板端实际已成功分配。

核自行发 AXI 读写，无外置 AXI DMA IP。调用侧负责地址映射、DMA/cache 一致性及缓冲区生命周期；本目录不提供 Linux 驱动、上传或 HDMI 功能。PS/DDR 配置继承本机既有 K26 工程，HP0/HP3 保持 128-bit 配置；PS PL0 改为 200 MHz。

| 相对偏移 | 含义 |
|---|---|
| `0x00` | HLS 控制：bit0 start；bit1 done（读清）；bit2 idle；bit3 ready |
| `0x04/0x08/0x0C` | HLS 标准中断寄存器；当前系统中断未接至 PS，使用轮询 |
| `0x10` | signed 32-bit 返回码 |
| `0x18/0x1C` | 输入 DMA 地址低/高 32-bit |
| `0x24/0x28` | 输出 DMA 地址低/高 32-bit |
| `0x30` | H |
| `0x38` | W |
| `0x40` | ABI cookie：必须写 `0x44433031` |
| `0x48/0x4C` | work_cycles，低/高 32-bit |
| `0x50` | work_cycles 有效位（读清） |
| `0x58/0x5C` | input_cycles，低/高 32-bit |
| `0x60` | input_cycles 有效位（读清） |

启动前确认 idle，写好全部参数后置 start；使用单次调用，关闭 auto_restart。完成后同时确认 done/idle、return=0，再同步并读取输出。返回 `-1` 表示 cookie 错误，`-2` 表示尺寸错误，这两种情况不会启动图像 DDR 访问。核不校验地址是否已映射、容量、输入整数范围或缓冲区重叠，调用侧须满足合同。

`work_cycles` 测量 DATAFLOW 工作区间，`input_cycles` 表示该区间内输入搬运完成点；它们不含全部启动和 AXI 写响应排空开销。端到端核心延迟以 start 到 ap_done 的测时为准。Host/CSim 的计数器不表示硬件周期，RTL/板端读数才有此含义。

复位为同步域内的低有效 `ap_rst_n`，与互连共用复位。正常完成前不要改寄存器、复用或释放缓冲区。若超时，输出无效；本版没有独立 AXI abort/drain 状态机，调用侧应保留在途缓冲并完成系统复位及事务静止确认后再复用，不能仅清 start 后重试。

## 帧率证据

200 MHz、隐藏卷积 II=1、6 phase/像素属于当前 HLS 结果及设计结构。正式帧率记录还要结合 720p RTL 的 start-to-done 周期、布线后时序及板端 DDR/连续帧测时。旧系统的 34 FPS、Host 用时和仅按 MAC 数计算的值均不作为 D 板端 FPS。
