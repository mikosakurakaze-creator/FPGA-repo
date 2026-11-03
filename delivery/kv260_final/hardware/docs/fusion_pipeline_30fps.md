# 融合流水线与 30 FPS 验证

日期：2026-11-01。目标帧为 1272×720、RGB/NCHW、INT16 Q14。

## 为什么必须修改

三个输入每帧合计 16,485,120 字节，输出为 5,495,040 字节。30 FPS 要求读 494,553,600 B/s、写 164,851,200 B/s。原 32-bit/100 MHz 读口的理论上限是 400 MB/s；原逐字 I→L→D→计算→写→B 的状态机还有事务往返开销。因此原功能正确的实现不能作为 30 FPS 交付。

## 本次实现

- 128-bit AXI4 INCR，最多 64 拍，按 4 KiB 和帧尾切分；一个读突发与一个写突发可同时在途。
- 三路输入、一路输出各 256×128-bit 分布式 RAM FIFO，缓冲 256 个八标量向量；无需增加 URAM。
- 八个标量通道，每通道三个乘法器；五级乘加、RNE、裁剪流水，无背压时计算 II=1。共享读口平均需三拍数据提供一个三路向量，不能把 II=1 写成整核每拍输出八个像素。
- 整个流水支持背压；输出突发先集齐数据，出错时完成已承诺 AXI 事务再报错。所有权重、cookie、指针、frame_id 及数值规则保持原合同。

## 已执行证据

外部证据根：`D:/weather_builds/fusion_pipeline_20261101`。旧源码保存在 `serial_baseline/` 并附 SHA256。

| 证据 | 状态与范围 |
| --- | --- |
| `rtl03/result.json` | PASS：10 帧/655,360 标量、9 类非法配置、读写错误、错误 RLAST、配置快照、长写背压/FIFO 满、读写重叠 |
| `tail01/result.json` | PASS：65,568 标量，4 KiB 错位基址和不足 64 拍的帧尾；10 帧数值回归 |
| `full01/result.json` | PASS：2,747,520 标量逐元素一致；1,383,169 拍，按 99,999,001 Hz 换算约 13.832 ms；读写同拍出现 251,688 次 |
| `same_image01/result.json` | PASS：来自已锁定 CNN/D 的同一原图三路结果与独立 Golden 逐元素一致 |
| `bandwidth03/result.json` | PASS：2,585,381 拍，约 25.854 ms；读通道最多隔一拍提供一拍数据，另有周期性暂停和事务延迟 |
| `package01/result.json` | PASS：revision 3，128-bit/64 拍 IP 封装完整性通过 |
| `ooc01/`, `verify01/`, `verify02/` | 前两次进程退出异常保留 FAIL；使用现有 desktop 启动 helper 后，verify02 独立重开同一 checkpoint 正常退出，复核 PASS |
| `D:/weather_builds/joint_pipeline01_20261101` | 新六核综合/布局布线通过：WNS +0.078 ns、WHS +0.010 ns；189,323/189,323网络完整布线；fusion→SmartConnect→PS HP3实际全链128位检查通过 |
| `controller_tests02/result.json` | 32项冻结源主机测试通过，包含三槽连续帧入口的物理缓冲查找和批次/间隔计时口径；不代表板端实测 |

仿真内存模型含 AR 后 6–10 拍等待、周期性 R/AW/W 暂停及延迟 B 响应，不含实际 PS 仲裁、DDR 控制器和其他 master 的动态竞争。13.832 ms 只说明该明确内存模型下的融合阶段满足预算，不是上板测得 FPS。

本次routed资源为LUT84,230、FF94,687、BRAM72.5 tiles、URAM58、DSP940。URAM占90.63%，CLB落点14,377/14,640（98.20%），物理布局较紧；0.078 ns的setup余量仅适用于本次精确IP/时钟/集成身份。独立完整覆盖与17项bus-skew检查全部通过，最差slack +3.675 ns；`acceptance.json`已记录通过。新bit/XSA已成功导出；最终ZIP按旁置`_verified.json`及`.zip.sha256`核实，包内有`SHA256SUMS`。

## 联合系统还必须核实什么

现有参考控制器每次 `run()` 处理一帧，帧内 prepare 之后并联 CNN/D，低照度路径仍有 CNN→Bilinear→Curve 的真实生产者依赖，融合等待两路成功。单帧完成时间为

`T_prepare + max(T_CNN + T_bilinear + T_curve, T_D) + T_fusion + T_software`。

因此，融合变快本身不证明整个系统 30 FPS。若单帧总延迟超过 33.333 ms，须使用互不重叠的多帧缓冲和跨帧调度，并以最慢阶段的启动间隔及共享 DDR 负载验收稳态 30 FPS；同一帧的生产者依赖不能省掉。现有 `JointController.run()` 保留为单帧参考；新增 `runtime/pipeline_controller.py` 采用三组帧缓冲，按每核独立 owner 和当前帧依赖调度不同帧，融合输出消费后才允许同一缓冲槽再次 prepare。30 帧/三槽 mock 测试验证全部 180 次核启动、每条帧内依赖、跨帧重叠、缓冲复用时序及失败/超时不交付；它验证的是调度逻辑，不是 FPGA/DDR 性能。新六核布局布线/时序已通过；仍需板端数值与持续多帧实测。


`bandwidth02` 的首轮仿真在输出完整且周期小于预算后，被“必须出现连续两拍计算输入”覆盖断言误判：隔拍 DDR 源本来不能连续供数。该失败保留；`bandwidth03` 将此断言仅用于未限速基线，限速测试仍要求真实读写重叠、逐元素一致及完整帧周期预算。

## 跨帧调度接口

```python
from pipeline_controller import FrameRequest, JointPipelineController
controller = JointPipelineController(real_dma_mmio_backend)
requests = (FrameRequest(frame_id, slots[(frame_id-1) % 3], weights_q15, load_input)
            for frame_id in range(1, 31))
controller.run_pipeline(requests, on_output=consume_output, max_inflight=3)
```

`load_input(request)` 只在相应缓冲槽前一帧已经完成并被消费后调用；`consume_output(frame_id, buffer)` 必须在返回前消费/复制结果，不能继续保存马上要复用的槽位指针。四组模型数组可跨帧只读共享，其余缓冲重叠时推迟入队。所有核仅在空闲时配置，Fusion 保留两路 done 和 completed_frame 校验。`real_dma_mmio_backend` 需完成实际 DMA/cache/MMIO 屏障；本轮不连接真板。

完整板端重放入口为 `runtime/run_pipeline_pynq.py`，具体命令见 `loading_order.md`。它将同一RGB文件重放到三个独立帧槽中，以实际PYNQ/MMIO/cache API调用调度器；统计包含CPU复制、cache、轮询与输出哈希。入口已做主机级缓冲定位测试，尚未在KV260执行。
