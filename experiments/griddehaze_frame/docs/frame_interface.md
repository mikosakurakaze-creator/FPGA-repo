# GridDehazeNet 整网候选核接口

日期：2026-10-24。本合同对应 `work/frame_synth01` 的实际 HLS 导出物，以及以当前流水旧核重建的系统 `D:/weather_builds/grid_system02`。第一次 `grid_system01` 误选历史 seed，已停止交付，详见 `system_seed_correction_20261024.md`。这是本轮硬件候选接口；不能套用于旧 weather 核。综合、布线、真板的完成状态分别见实施记录。

## 数据与调度

- 模型固定为 A 的 outdoor INT16 bundle `5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710`。
- batch=1、RGB、NCHW、小端 signed INT16。输入 F14，对应 [-1,1]；输出 F13；中间激活逐节点 F3…14，不能统一解释为 Q14。
- 网络最终 ReLU 输出为 0…32767，F13 的真实值可能大于 1；硬件不套用旧核的 `[0,16384]` 输出钳位。外部显示侧另行将真实值裁剪至 `[0,1]` 并转换 RGB8，显示文件不代替整数 Golden。
- 权重保持 A 的 1,933,120 字节 blob：卷积 OIHW、反卷积 IOHW、INT64 bias、Q14 learned coefficient。逐通道 shift 和图结构固化为只读硬件常量，不附加到原权重 blob。
- MAC 和逐元素中间值使用 48 位有符号数，RHAZ（半值远离零）、饱和和奇数尺寸反卷积目标大小按冻结图执行。参数内容 SHA 仍须由可信调用方核对，硬件不计算 DDR blob 哈希。
- H=4…720、W=4…1280。PL 顺序执行全部 320 节点；CPU 不参与逐层运算。卷积使用最多 8 输出通道、16×16 tile 和片上输入/权重缓存；中间节点写回 DDR，按生存期复用 scratch。

## 已生成的总线与系统连接

| 接口 | 实际导出及新 BD 连接 |
|---|---|
| `s_axi_control` | AXI-Lite 数据 32 位、地址 8 位，经 `axi_control/M04_AXI`；BD 基址 `0xA0040000`，分配 64 KiB |
| `m_axi_feature_mem` | 数据 32 位、地址 64 位，输入/输出/scratch 共用；经 `curve_ddr_sc/S04_AXI` 到 HP3 |
| `m_axi_parameter_mem` | 数据 32 位、地址 64 位，权重和 layout 共用；经 `cnn_data_sc/S04_AXI` 到 HP0 |
| PS HP0/HP3 | 新 BD 均为 128 位，SmartConnect 完成宽度转换；这不证明板上当前 PS 初始化正确 |
| 时钟/复位 | `pl_clk0` 配置 100 MHz，共享 `rst_ps_100m/peripheral_aresetn` |
| 中断 | HLS 有 `interrupt` 输出，目前未接到 PS IRQ；本候选采用轮询 |

新核两个 master 仅映射低 2 GiB DDR。基址为系统 BD 事实；可下载 bit/XSA 是否已生成必须另查实施记录，不能用 preimpl XSA 冒充最终交付。

## 实际 AXI-Lite 寄存器

地址来自生成的 `xgriddehaze_frame_top_hw.h`，不是早期提案的地址。

| 偏移 | 字段 |
|---|---|
| 0x00 | HLS 控制：bit0 START、bit1 DONE（读清）、bit2 IDLE、bit3 READY；禁止 bit7 auto-restart |
| 0x04/0x08/0x0C | HLS GIE/IER/ISR；轮询模式保持关闭 |
| 0x10 | 32 位返回码，0 成功 |
| 0x18/0x1C | input 地址低/高 32 位 |
| 0x24/0x28 | output 地址低/高 32 位 |
| 0x30/0x34 | scratch 地址低/高 32 位 |
| 0x3C/0x40 | parameters 地址低/高 32 位 |
| 0x48/0x4C | layout 地址低/高 32 位 |
| 0x54/0x5C/0x64 | input/output/scratch 字节长度，各 u32 |
| 0x6C/0x74 | parameters/layout 字节长度，各 u32 |
| 0x7C/0x84 | H / W |
| 0x8C/0x94 | 请求 model=`0x47444E31`、ABI=`0x00010000` |
| 0x9C/0xA0 | completed_nodes / valid（valid 读清） |
| 0xAC/0xB0 | hardware_model / valid（valid 读清） |
| 0xBC/0xC0 | hardware_abi / valid（valid 读清） |

HLS 会优化输出引用的中间写入，因此 `completed_nodes` 不能当逐节点实时进度计数器；成功 DONE 后必须为 320。model/ABI 输出由启动时赋值，不保证复位后未启动前即有效。应按同版 XSA/bit 清单选择设备，再提交带身份检查的请求。独立 RTL 测试的逐节点观察来自该版本内部图循环退休状态，不属于公共 ABI。

## layout 元数据

`tools/emit_model.py` 根据冻结图及 H/W 生成 336 个小端 u32，共 1,344 字节：

| word | 内容 |
|---|---|
| 0…7 | magic=`0x314C4447`、版本1、H、W、320、flags0、scratch_bytes、reserved0 |
| 8…15 | 完整 bundle SHA 的原始 32 字节，按小端 u32 装载 |
| 16…335 | 每节点 scratch 字节偏移；input 和最终 output 项必须为0 |

硬件先验证身份、shape、全部节点区间、64 字节相对偏移对齐和生存期重叠，再访问特征或权重。layout 自身必然先被读取；不能宣称所有无效请求均不产生 DMA。

33×47 scratch=794,240 字节；675×1280=442,368,000；720×1280=471,859,200（450 MiB）。720p 输入/输出各 5,529,600，权重 1,933,120，合计 484,851,520 字节，另加 layout 和分配对齐。实际可分配连续总线内存由外部软件侧确认，当前没有板测容量结论。

## 完成、错误和硬件边界

调用方在 IDLE 时配置全部寄存器，只启动一次；运行期间保留五个独占且互不重叠的区域，不能改动参数、layout 或回收输入。每个 DMA slot 至少 64 字节对齐并向上取整，逻辑字节长度仍按真实 payload 填写。所有基址及整个 slot 必须落在 `[0,0x80000000)`，且不得与其他设备的运行内存重叠。

返回码：1=model/ABI/H/W；2=逻辑长度；3=layout 头/身份；4=scratch 对齐或范围；5=仍存活张量重叠；6=bias 超出防护范围；17…19=内部卷积错误；33…34=逐元素错误。任何非零返回均使本次输出无效，不能用上一次结果充当成功。

当前 HLS 顶层检查逻辑长度和相对 scratch，但不验证物理指针合法性或跨区域别名，也不提供 AXI RRESP/BRESP 诊断、超时中止或独立复位排空器。必须由可信硬件调用方验证地址；该限制并不等于 Linux 驱动已实现。各处理路径当前要求互斥运行。

**故障恢复尚未完成**：软件等待超时不代表 DMA 已停止，禁止立即复用缓冲或单独拉低新核复位。共享复位会影响旧核，不能称为独立请求恢复。只有正常 DONE 且返回 0、completed_nodes=320，才可以读取结果；AXI 写响应是否在 DONE 前排空，以实际 RTL 测试结果为证。该候选不应被描述为已经具备完备故障恢复的生产版本。
