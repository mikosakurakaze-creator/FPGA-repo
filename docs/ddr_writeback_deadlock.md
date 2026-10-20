# Weather 输出写回卡死：定位与修正

## 失败证据

`work/frame03` 的两任务 8×8 HLS RTL co-sim 确实通过，但它不足以证明变尺寸和跨 tile 可用。随后 `sequence02/03/04` 均未通过；不能把其中 C 测试台打印的 PASS 当作 RTL PASS。

为区分 vendor UVM/VIP 异常与硬件问题，新增独立 SystemVerilog 测试台，直接连接未修改的 IP Verilog，以 AXI-Lite 配置参数，以有停顿的 AXI DDR 模型响应读写。测试台不用 vendor UVM/VIP。

`work/rtl_memory03/simulation.log` 记录：同一核不复位，task 0→1→0 的 8×8 三次调用逐位通过，随后 131×1 调用在 200,000 cycles 门限内未结束。此时已读 **393 个 32-bit 总线 beat**，输出 **0 beat**，顶层 FSM=`0x10`、tile FSM=`0x2000`、store FSM=`0x4`。窄行输入需要不同的半字地址，读 beat 数不是输入字节数除以 4。

这在独立内存模型中复现了相同卡点，说明不能仅归因于 vendor 仿真器异常或内存耗尽。另有 Vivado 综合的内存分配失败，是构建资源问题，需单独处理。

## 机制与修正

旧 `store_core` 的通道、行、像素循环被 HLS 自动合并。实际流水中，行写请求约在 iteration 3 发出，数值计算后的写数据约在 iteration 16 发出，写响应检查约在 iteration 21。行很短时，先行请求/响应与有限 AXI adapter 队列相互阻塞，整条计算流水一起停住，后方数据也无法继续到达写口。

新结构为：

1. 在片上完成一行尾层卷积、缩放、残差相加和输出截断。
2. 将该行保存到小型片上 row buffer。
3. 调用独立的 `write_row`，仅做连续 DDR 写回。
4. 完成后再处理下一行；禁止合并外层行/通道循环。

这使深算术流水与 AXI 写请求/响应脱钩。没有修改生成后的 RTL，没有增加 DDR scratch，也没有改变模型参数、舍入顺序、Q14、RGB/NCHW 或外部寄存器合同。host-only 的 `tile_local()` 还检查完整 140 像素宽 A tile，因此行缓存按 140 元素分配；正式整帧 core 的有效写宽最大为 128。

## 验证与交付门限

修正后的 host 全量结果见 `work/onchip_host_20261020_06/verification.json`：包括两个任务逐层 Golden、边界与负对照，以及 720×1272、720×1280 整帧比较。此结果不能代替 RTL。

修正后的 HLS 构建为 `work/frame04`。独立 RTL 回归须在同一实例上完成 7 次调用：三个 8×8、131×1、1×133，以及两任务各一个 131×133；检查有效输出、尾部 guard、AXI 地址、burst 边界、WSTRB、WLAST、背压时 VALID/payload 稳定性，以及 done 前写响应排空。故意改变 Golden 的 1 LSB 必须被拒绝。

后续实际结果和最终 bit/XSA 身份以 `system_integration_20261020.md` 与最终构建清单为准。失败候选 `frame03/system01` 不进入最终可上板候选包。
