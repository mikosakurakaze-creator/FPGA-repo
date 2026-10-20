# Weather 整帧原型接口合同（实验 ABI v2）

更新：2026-10-21；当前实现为 `experiments/stream_frame`。主机数值验证、两任务 Vitis CSim/综合/8×8 RTL/IP 导出、五次 vendor RTL、九次独立 AXI RTL（含双任务完整 720p）与新组合系统布局布线均已通过。最终 bit/XSA 与交付状态见 [流水版修正记录](stream_revision_20261020.md)。现有 `derain_top` / `dehaze_top` 包继续使用 [ABI v1 合同](weather_ddr_contract_draft.md)。

## 函数与数据

```c
int weather_frame_top(const int16_t *input, int16_t *output,
                      int height, int width, int task);
```

`task=0` 去雨，`task=1` 去雾；两套固定参数均编译进源码，整次调用只选一种。不接受运行时权重。`height=1..720`，`width=1..1280`。

输入、输出均为 `[1,3,H,W]`，连续 RGB NCHW，小端有符号 INT16，实数值为 `raw/16384`。先完整 R 平面，再 G、B；元素字节地址为 `base + 2*((c*H+y)*W+x)`。不支持 row stride、平面 padding 或输入输出重叠。原型只要求标量至少 2 字节对齐，实际 DMA 分配需满足平台的 cache-line 和物理连续性要求。独立回归覆盖了窄行、奇数长度的半字访问及输出 WSTRB；实际 32-bit 总线读可能覆盖包含最后一个标量的对齐字，平台分配须保留该字和隔离缓存线。standalone 后端要求两个独立 64-byte 对齐/隔离的分配。

每个 buffer 至少 `6*H*W` 字节。720×1272 为 5,495,040 字节；720×1280 为 5,529,600 字节。输入输出是两个独立有效范围；没有外部 scratch。正常图像输入为 `[0,16384]`，主机测试也覆盖有符号 INT16 极值。输出钳位 `[0,16384]`。

uint8 RGB 转换：`RNE(pixel*16384/255)`；预览转换：`clip(RNE(raw*255/16384),0,255)`。RNE 表示最近值、正好一半取偶数。PNG 仅供查看，核查以原始 Q14 字节为准。

权重 INT8、偏置和累加 INT32，中间激活 INT16 且使用节点自己的小数位；不能把全部中间激活按 Q14 解读。量化、残差及饱和规则保持 A 的原实现。

返回值：0 成功；1 尺寸非法；2 任务非法。若尺寸与任务同时非法，先返回 1。非法参数在访存前返回。合法尺寸下，调用方负责有效地址、容量和所有权，硬件无法验证主机指针是否为空或是否重叠。

## AXI 与控制寄存器

源码请求 `m_axi_gmem_in` 读整帧 DDR、`m_axi_gmem_out` 写整帧 DDR，AXI-Lite `CTRL` 控制。没有 AXI Stream；不输出 `A_low`，输出直接是增强后的全分辨率 RGB，不接 Bilinear/Curve。

| 偏移 | 字段 | 状态 |
|---:|---|---|
| `0x00` | 标准 `ap_ctrl_hs`：start bit0、done bit1、idle bit2、ready bit3、auto-restart bit7 | 实际 RTL/头文件已核对 |
| `0x10` | return | 实际 RTL/头文件已核对 |
| `0x18/0x1C` | input 64 位字节地址，低/高 32 位 | 源码显式指定 |
| `0x24/0x28` | output 64 位字节地址，低/高 32 位 | 源码显式指定 |
| `0x30` | height | 源码显式指定 |
| `0x38` | width | 源码显式指定 |
| `0x40` | task | 源码显式指定 |

所有偏移已与 `work/stream02/derain/component/hls/impl/ip` 的实际驱动头文件核对。新合并系统 base 为 `0xA0030000`，数据总线 32-bit、地址 64-bit；两路 master 仅接低 DDR 2 GiB 窗口。现有 v1 的 `0x30` 是 scratch 指针，不能混用。`D:/weather_builds/stream_system01/interface_audit.json` 保存实际生成 BD/RTL 的核验。

源码请求最大读/写 burst 64、每方向 outstanding 4、最大深度 2,764,800 个 INT16。请求不保证 HLS 达成；也不能由 16 位标量类型推断总线只有 16 位。

## 时序与所有权

采用串行的一次一帧调用。上次完成前不能改 input、output 地址、shape、task，也不能读取或复用设备持有的 buffer。内部为各层同时工作的 DATAFLOW 行流水；行缓存跨调用复用，每层首行 padding 覆写旧状态。主机和 RTL 已验证交替任务/尺寸；并发调用及 auto-restart 未支持。

PS 验证参数和空闲状态 → 将输入/输出所有权交给设备 → 写地址和尺寸/任务 → barrier → start → 有界轮询 done → 检查 return → 同步输出并交回 CPU。使用 [portable PS 控制说明](../deployment/README.md) 中的隔离和恢复流程处理超时。

时钟为名义 100 MHz，HLS `clock=10 ns`；新组合系统 post-route setup WNS +1.018 ns、hold +0.010 ns，零时序失败。六个空间阶段的 HLS 实际 II=1，但外部吞吐受行读写、FIFO 和 DDR 响应影响。`work/stream_rtl01` 中两任务完整 720×1280 各为 3,009,677 拍，即 30.09677 ms，低于 3,333,333 拍预算。该数字来自独立 DDR 模型（完整帧不主动注入停顿，每两拍最多返回一个 32-bit 读 beat、每方向一个在途 burst），不是固定延迟或真板 FPS 合同。

独立有停顿 AXI 回归已检查 `ap_done` 出现时本帧输出写响应已排空。完整 PS/DDR 系统的真板验证仍需执行。超时不能视作停止 DMA；必须停止 master 并排空在途事务后才能复用内存。

## 接入前门槛

1. 已通过两任务官方 Golden、完整帧主机比较和 HLS 综合。
2. 已通过两任务 vendor RTL、任务/尺寸切换、反压、guard、负对照和双任务完整 720p RTL；8×8 只是最小用例。
3. 已核对导出 IP 的 CSR、总线元数据及系统输入 254 份 RTL/ROM 身份。
4. 已连接 DDR、时钟/复位并通过新组合系统 implementation；bit/XSA 身份以当前报告为准。真板 Golden、实际 DDR 仲裁和持续视频仍待验收。

当前实际结果与原始报告路径见 [流水版修正记录](stream_revision_20261020.md)；[原系统集成记录](system_integration_20261020.md) 和 [B 侧报告](b_progress_report.md) 保留此前阶段的历史。
