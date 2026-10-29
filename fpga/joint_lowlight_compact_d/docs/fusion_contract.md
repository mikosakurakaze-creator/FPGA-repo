# 新增融合核合同

生产默认：`SCALAR_COUNT=2747520`，即 `[1,3,720,1272]` RGB/NCHW/little-endian signed INT16 Q14；每个输入/输出均为 5,495,040 字节。包装后的系统必须显式锁定这一参数。仿真中的 65,536 标量配置只用于加速多用例回归；另有完整 2,747,520 标量 RTL 测试。

## 数值与访存

三个 AXI-Lite 权重字段均接收完整 UINT32。每个值必须 <=32768，34 位加法检查总和恰好 32768。在启动被接受的同一时钟沿，锁存所有指针、三个合法权重和 frame_id；运行中写配置只影响下次启动，busy 期间 start 不排队或重启。

每个标量计算 signed64 `I*wI + L*wL + D*wD`，只做一次除以 32768 的最近偶数舍入，最后裁剪 `[0,16384]`。不提前裁剪输入。两个连续 INT16 标量打包成一个 32-bit AXI 数据字，顺序与 NCHW 线性地址相同。

单个 `m_axi_gmem`，64-bit 地址、32-bit 数据、INCR 单 beat、最多一个未完成读或写。每次输出字依次读 I/L/D，再写输出；AW 与 W 独立握手，等待 B 响应后才推进。这个实现优先保证合同与资源边界，**不提供 30 FPS 或 DDR 吞吐承诺**。不能把仿真时钟数当作真板耗时。

所有基址须 64-byte 对齐，完整缓冲必须在 LOW DDR `[0,0x80000000)`。输出不得与任何输入重叠。硬件拒绝非法权重、cookie 或地址后不会发起任何图像 DDR 事务。三输入之间仅为只读，可别名，但当前调度器按不同分配检查，避免模型生产者冲突。

## AXI-Lite ABI

保留基址 `0xA0040000/64K`。这只是最终 BD 应分配的地址；当前独立 IP 导出不代表联合 BD 已实现该映射。

| 偏移 | 内容 |
| --- | --- |
| 0x00 | bit0 start；bit1 done（读清）；bit2 idle；bit3 ready（idle 电平）；bit7 不实现 auto_restart |
| 0x04 / 0x08 / 0x0C | GIE / IER(done,ready) / ISR(toggle-on-write)；最终系统使用轮询 |
| 0x10 | signed INT32 return |
| 0x18 / 0x1C | I pointer low/high |
| 0x24 / 0x28 | L pointer low/high |
| 0x30 / 0x34 | D pointer low/high |
| 0x3C / 0x40 | output pointer low/high |
| 0x48 / 0x50 / 0x58 | 完整 UINT32 wI / wL / wD |
| 0x60 | cookie=`0x4A463031` |
| 0x68 | 下次 frame_id |
| 0x70 | 最近一次成功完成的 frame_id；启动时清零 |
| 0x74 | 启动时锁存的 active_frame_id |

本核是手写 RTL，不冒用 HLS driver；ready 的电平语义已明确，不依赖其读清。AP_CTRL 读一次即保存 done；不得再次读取期待仍为 1。partial WSTRB 按字节更新配置。保留/未映射偏移写入返回 SLVERR；busy 时 start 被忽略。

return：0 成功，-1 cookie，-2 权重，-3 AXI 读/写响应或 RLAST 异常，-4 对齐/窗口/输出重叠。-1/-2/-4 在 DDR 事务前返回；-3 可能已有部分输出，输出必须作废。

`ap_clk` 目标 100MHz，`ap_rst_n` 低有效同步复位；须由该域 reset synchronizer 释放。单核 OOC 结果不能作为系统布局布线时序签核。发生 timeout、AXI/协议故障时，软件不得继续复用缓冲，需执行完整 PL 恢复并证明 outstanding 事务静止。

## 调度边界

`runtime/controller.py` 提供单 owner、单帧参考调度：prepare 完成并成功后并联启动 CNN 和 D；逐级确认 CNN→Bilinear→Curve；同一调用的 Curve_done 与 D_done 均成立后才启动融合。融合 return=0 且 completed_frame 与当前 frame_id 相同才将输出所有权交 CPU。

真实后端必须提供独占硬件 lease、物理 DMA 地址、MMIO barrier 和正确的 DMA/cache 所有权转换；本次没有实现或调用板端后端。host mock 的单元测试不等于 AXI 联合 RTL 仿真，也不等于板测。L/D 按任务 1 合同采用只读别名，省去两个 raw-copy 实例及多余 DDR 流量。
