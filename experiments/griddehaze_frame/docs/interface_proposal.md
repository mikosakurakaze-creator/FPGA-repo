# GridDehazeNet 接口提案与已导出算子CSR

日期：2026-10-24。本文首先记录方案，再列真实HLS导出值；未把尚未实现的寄存器当成硬件事实。

**后续更新**：本文件保留早期整图提案及内部算子接口作为历史。当前 `griddehaze_frame_top` 已实际导出，整网 CSR 和新 BD 连接以 [frame_interface.md](frame_interface.md) 为准，不能按下方旧提案偏移访问。

集成范围已由用户确定：保留旧weather核与低照度链路，新增独立GridDehazeNet核。下述整图接口属于新增设备，不覆盖旧核寄存器或复用旧task语义，见integration_scope_20261024.md。

## 早期整图请求提案（历史，不是当前 ABI）

建议保留标准控制0x00..0x0C，增加独立只读身份寄存器0x100起。model ID建议 `0x47444E31`（GDN1），ABI `0x00010000`，配合完整bundle SHA绑定。ID/version未匹配时驱动不得写START；旧TinyRestore `task=1` 不存在兼容含义。

候选整图寄存器如下；这些地址没有出现在当前bit/XSA里，不能写旧设备验证。

| 建议偏移 | 字段 |
|---|---|
| 0x00..0x0C | 标准START/DONE/IDLE/interrupt控制；禁用auto-restart |
| 0x10 | 返回错误码，0成功；输出有效性另由DONE/状态保证 |
| 0x20/0x28 | input DMA u64 / 长度u64 |
| 0x30/0x38 | output DMA u64 / 长度u64 |
| 0x40/0x48 | parameter DMA u64 / 长度u64 |
| 0x50/0x58 | scratch DMA u64 / 长度u64 |
| 0x60/0x68 | command DMA u64 / 长度u64 |
| 0x70/0x74 | H / W，4..720和4..1280 |
| 0x78 | request ID，软件和结果关联 |
| 0x100/0x104/0x108 | model ID / ABI版本 / capabilities |
| 0x120..0x13C | 当前固化模型完整bundle SHA-256，寄存器字节序另共同冻结 |
| 0x140.. | 首个失败command、状态、分段cycle计数器等诊断字段 |

ABI的64-bit字段占8字节，且与现有算子CSR完全不同。length的有效payload与DMA分配slot长度分开，不允许把尾部padding当图像像素。DMA物理/总线地址由驱动获得，64字节对齐，区域不重叠。候选先限制所有区间落在低2GiB DDR窗口：`base+length<=0x80000000` 且加法不溢出。这是与现系统映射兼容的提案，最终以新DT/XSA及DMA mask为准。

command由冻结graph、实际H/W和已证明地址计划生成。每项显式给op、逻辑形状、尺度、源/目标区间、权重布局/偏移、bias与逐通道shift、目标deconv尺寸。硬件在访问前核查描述符和边界；仅接受合法op及参数范围。首版按层串行，在结果/读写全部完成后才发布节点完成。PS不将用户提交的任意内存地址直接写入command。

权重blob保持原始格式，requant shift来自graph并放入独立元数据区；不能把它误认为原参数blob的一部分。文件SHA由软件核验，硬件只读bundle常量本身不能证明DDR参数内容哈希正确。每次job的输入identity和固件身份进入运行记录。

错误语义拟分为INVALID_DESCRIPTOR、MODEL_MISMATCH、BOUNDS、AXI_RESPONSE、INTERNAL等。启动前失败无DMA；启动后错误将输出标为无效。TIMEOUT为软件等待超时，不证明硬件停止；ownership保持，专用复位与AXI排空方案尚待平台共同冻结。

## 当前已真实导出的卷积tile接口

来源：`work/hls02/component/hls/impl/ip/drivers/.../xgriddehaze_conv_tile_top_hw.h`，已收集在evidence。该核一次只计算最多8输出通道、16×16输出空间块，支持INT16权重、48-bit MAC、OIHW/IOHW。它不执行320节点的整图计划，也没有model/ABI guard。

| 实际偏移 | 字段/语义 |
|---|---|
| 0x00..0x0C | Vitis HLS标准控制、中断 |
| 0x10 | ap_return，0成功、1尺寸/描述符错误、2缓存不足、3shift范围错误 |
| 0x18/0x1C | feature指针低/高32位 |
| 0x24/0x28 | weights指针低/高32位 |
| 0x30/0x34 | bias指针低/高32位 |
| 0x3C/0x40 | shifts指针低/高32位 |
| 0x48/0x4C | output指针低/高32位 |
| 0x54/0x5C | cin / cout |
| 0x64/0x6C | ih / iw |
| 0x74/0x7C | oh / ow |
| 0x84/0x8C/0x94 | kernel / stride / padding |
| 0x9C | transpose：0普通卷积，1反卷积 |
| 0xA4/0xAC/0xB4 | 输出tile原点y / x / 起始输出通道 |

返回3时已经发生只读装载，不能宣称所有错误都在DMA前发现；尚未写出结果。当前指针没有长度参数，越界保护依赖调用方验证和后续整图控制器，这个算子试验核不能直接面向不受信任用户暴露。

AXI bundle为read_mem/write_mem，当前未建立PS/SmartConnect映射，不能宣称已经接上HP0/HP3。已读取生成RTL：read_mem数据64位、write_mem数据32位，两者地址64位；AXI-Lite数据32位、地址8位。`max_widen_bitwidth=128`是上界请求，并未生成128位master。PS侧宽度及转换由最终BD/XSA核验。整图ABI的0x100以上身份寄存器要求新wrapper扩大控制地址空间，不能直接接到当前8位地址的算子AXI-Lite上。

## 当前已真实导出的逐元素算子接口

`griddehaze_elementwise_top` 是独立新增去雾核内部的另一类算子，与卷积 tile 共用同一数值 bundle。它完成 ReLU、Q14 learned coefficient 乘法、加法、NCHW 通道拼接。通道上限 128，H=1..720、W=1..1280，特征 F=3..14，48 位中间运算；加法在宽整数内对齐两端后相加并最后饱和，系数分支的乘法输出独立舍入/饱和。

以下为实际生成的算子 CSR，不能用来操作旧 weather 核或当作整网 ABI：

| 偏移 | 字段 |
|---|---|
| 0x00..0x10 | HLS 标准控制、中断、返回状态 |
| 0x18/0x1C | 输入 a 地址低/高 32 位 |
| 0x24/0x28 | 输入 b 地址低/高 32 位 |
| 0x30/0x34 | 系数地址低/高 32 位 |
| 0x3C/0x40 | 输出地址低/高 32 位 |
| 0x48/0x50/0x58/0x60 | a/b/系数/输出长度，各 32 位，单位为 INT16 标量 |
| 0x68 | op：1=ReLU、2=mulcoef、3=add、4=cat |
| 0x70/0x78/0x80 | a/b/输出通道数 |
| 0x88/0x90 | H / W |
| 0x98/0xA0/0xA8 | a/b/输出的小数位数 F |

返回值 0 成功、1 形状/尺度/op 不合法、2 逻辑长度不足。描述符与长度检查发生在数据读取前；未使用的 b/系数不被读取。输入、输出不得重叠，指针必须来自合法 DMA 分配；物理地址窗口、别名和 ownership 还需整图 wrapper/驱动保证。长度检查不能单独证明传入地址有效。

按每通道 256 标量块装载、计算、写回，系数先缓存在片上。真实导出 read_mem/write_mem 数据均为 32 位、地址均为 64 位；AXI-Lite 数据 32 位、地址 8 位。当前未连接 PS，也未做 RTL 协同仿真或 AXI 写排空验证；C 仿真只证明数值与逻辑长度检查。

## 需要取得证据再确定的值

HLS导出的算子寄存器已有实物生成文件；整图CSR、最终基址、PS端数据宽度、DT节点、IRQ、实际PL时钟、coherent DMA地址和可分配容量、SMMU状态以及复位排空能力均还没有本版平台证据。不能用旧HWH或本提案填成“已验证”。

责任划分：B实现整图CSR、互连与复位/完成语义，通过新BD/XSA提供基址、窗口、总线宽度、IRQ/时钟等硬件资源定义及bit/XSA；软件侧据此适配Linux驱动、合入设备树并实测DMA/CMA。尚未拿到当前驱动不阻止B继续硬件开发，板端联调结果另行记录，见responsibility_boundary_20261024.md。
