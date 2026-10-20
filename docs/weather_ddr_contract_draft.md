# 天气恢复 DDR 与 AXI-Lite 接口合同

本合同依据 A 组最终 `INTERFACE.md`、HLS `component.xml` 和生成驱动头文件整理。Vivado 地址分配及板端 DMA 分配器由 B 侧系统集成决定。

本文是已打包 A 组 IP 的 **ABI v1**。新整帧核使用独立的 [ABI v2 合同](weather_frame_v2_contract.md)。`deployment/weather_control.c` 支持两种约定；v2 已完成生成接口与最终系统离线核验，结果见当前报告。禁止将 v2 标量寄存器套入 v1 scratch 指针映射。

## 顶层函数与任务身份

```c
int derain_top(const int16_t *input, int16_t *output,
               int16_t *scratch, int height, int width);
int dehaze_top(const int16_t *input, int16_t *output,
               int16_t *scratch, int height, int width);
```

这是两个独立的固定参数核。不能传外部权重指针、混用任务权重/缩放，或假定单个 v1 IP 能运行时切换任务。尺寸非法时返回 1，不访问指针；合法 tile 返回 0。

## 每个 tile 的内存合同

| 缓冲区 | 布局 | 元素数 | 140x140 时的字节数 | 访问方向 |
|---|---|---:|---:|---|
| `input` | 连续 RGB NCHW、小端有符号 INT16 Q14 | `3*H*W` | 117,600 | IP 读 |
| `output` | 同输入布局，Q14 钳位 `[0,16384]` | `3*H*W` | 117,600 | IP 读写 |
| `scratch` | 三个工作平面 `[3,8,H,W]`，有符号 INT16 | `24*H*W` | 940,800 | IP 读写 |

三段字节范围均须有效且互不重叠。元素至少 2 字节对齐；确认实际驱动约束后，应使用符合平台 DMA/缓存行对齐要求的分配。最大尺寸下，input/output/scratch 合计至少 1,176,000 字节。每次 `done` 且输出复制完成后，可串行复用相同分配。

元素 `(c,y,x)` 的字节偏移为 `2*((c*H+y)*W+x)`，不允许行或通道 padding。完整 720x1272 每个帧缓冲区为 5,495,040 字节，但矩形 tile 在整帧中跨行，非连续紧凑布局。IP 没有 row stride，必须先收集连续输入 tile，再将裁剪后的输出 core 回写整帧。

RGB uint8 转 Q14：`round_to_nearest_even(pixel * 16384 / 255)`。数值核查以原始 Q14 张量为准；预览转换为 `round_to_nearest_even(raw * 255 / 16384)`，再钳位 `[0,255]`。

## tile 几何规则

- core：128x128；halo：6；紧凑 IP 输入最大 140x140。
- 720x1272 帧需要 6 行 x 10 列，即 60 次调用。
- core `[y:y1,x:x1]` 对应打包输入范围 `[max(0,y-6):min(H,y1+6), max(0,x-6):min(W,x1+6)]`。
- IP 在实际 tile 边界执行自己的零 padding；丢弃 halo 输出，只复制有效 core。
- 真正图像边缘将 halo 裁剪到图像范围，不额外制造有效输入像素。

## AXI 接口

每个 IP 提供：

- `s_axi_CTRL`：AXI4-Lite，32 位数据、7 位地址。
- `m_axi_gmem_in`、`m_axi_gmem_out`、`m_axi_gmem_work`：三个 AXI4 master，64 位地址、32 位数据。打包元数据列出 `MAX_BURST_LENGTH=256`，同时列出 `HAS_BURST=0`、`SUPPORTS_NARROW_BURST=0`；各 bundle 的最大读长度为 64，最大写长度在 `gmem_in` 为 16，在 `gmem_out`/`gmem_work` 为 64。HLS 综合报告显示标量 16 位张量访问，数据加宽/stride 推断失败，因此 SmartConnect/数据宽度行为和真实 DDR 事务必须在系统仿真中确认，不能仅凭元数据认定 burst 高效。
- `ap_clk`、低有效 `ap_rst_n`、`interrupt`。

没有 AXI Stream。三个内存 master 需经适合的互连接到所选 DDR 路径。地址宽度和 32 位总线宽度描述 master 接口，张量值仍为 16 位，软件不能将元素重打包成 32 位。原 HLS 功能基线通过 `gmem_work` 读写中间特征，存在带宽/时序风险；声称满足 100 MHz 或视频吞吐前需实际测量。

## AXI-Lite 寄存器

指针均为 64 位字节地址。通过生成驱动或等价有序 MMIO 先写低字、再写高字。

| 偏移 | 字段 | 含义 |
|---:|---|---|
| `0x00` | `AP_CTRL` | `ap_start` bit 0、`ap_done` bit 1（读后清零/COR）、`ap_idle` bit 2、`ap_ready` bit 3（读后清零/COR）、auto-restart bit 7 |
| `0x04` | `GIE` | 全局中断使能 |
| `0x08` | `IER` | 中断使能 |
| `0x0C` | `ISR` | 中断状态，写入后翻转相应状态位 |
| `0x10` | `AP_RETURN` | 核返回状态：0 成功，1 尺寸非法 |
| `0x18/0x1C` | `input_r` 低/高字 | 输入字节地址 |
| `0x24/0x28` | `output_r` 低/高字 | 输出字节地址 |
| `0x30/0x34` | `scratch` 低/高字 | 工作区字节地址 |
| `0x3C` | `height` | tile 高，1..140 |
| `0x44` | `width` | tile 宽，1..140 |

最终 BD 中，每个 IP 应分配独立控制基址。不能默认沿用 V1.2 低照度 CNN 的基址或偏移。

## 所有权交接顺序

1. 检查尺寸、容量、对齐和范围无重叠，确认 IP 空闲。
2. 打包当前输入 tile，同步/清理供设备访问；按目标 DMA/cache API 将 output 和 scratch 交给设备。
3. 写全部指针高低字及尺寸，执行所需内存屏障，再启动 IP。
4. 以有界超时等待 `ap_done` 或中断，检查 `AP_RETURN == 0`。
5. 同步/失效输出缓存并交给 CPU，裁剪回写输出 core，再释放或复用三个缓冲区。

交付驱动定义寄存器访问，不实现部署用 Linux DMA 分配、缓存所有权、系统互连或恢复。同一 IP 调用不可重入，并行 IP 事务不得共用同一 scratch 分配。

B 侧可移植控制层已实现有界轮询、所有权回调、完成状态不确定时的隔离，以及停止/排空后的恢复，见 [PS 控制说明](../deployment/README.md)。主机模拟测试通过；真实平台 DMA/cache 和复位/排空仍需板端后端与硬件证据。
