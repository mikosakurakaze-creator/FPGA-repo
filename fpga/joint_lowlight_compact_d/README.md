# KV260 低照度、Compact D 与三路融合

当前版本为 2026-11-02 接受的六核联合实现：Prepare 和 Fusion 均采用流水与 AXI burst，最终 setup WNS **0.391 ns**、hold WHS **0.100 ns**。100/200 MHz、模型、数值规则和寄存器地址保持原合同。

一帧由 Prepare 生成原图 Q14、CNN 小图和 D 输入；随后 CNN → Bilinear → Curve 与 Compact D 并行运行；两路成功后，Fusion 按软件权重融合原图、低照度结果和 D 结果。模块间通过 DDR 缓冲交接，D 层间使用片上 FIFO。连续帧入口可让不同核处理不同帧，不能跳过同一帧的完成依赖。

- [当前发布身份、资源与验证范围](docs/release_20261102.md)
- [Prepare 流水、burst 与其余核检查](docs/prepare_pipeline.md)
- [Fusion 结构、仿真吞吐与跨帧调度](docs/fusion_pipeline_30fps.md)
- [融合寄存器与数值合同](docs/fusion_contract.md)
- [地址、加载及调用顺序](docs/loading_order.md)
- [当前时钟与复位](docs/clock_reset_20261102.md)
- [当前发布的小型证据](evidence/release_20261102/)

本分支保存实现源码、测试、构建与验证脚本，以及小型报告。大型硬件包保留本地：

`D:/competing/outputs/kv260_joint_fifo_hold_release_20261102_final.zip`

ZIP SHA256：`a7cccfafeb963c990fc3aab90c4451df750776abc3763fbb00438d4ded51625e`。

包内有 bit、bit.bin、XSA、HWH、6 核 91 项寄存器表、时钟/复位和调用说明、实际实现输入、Golden、报告及 SHA256SUMS。Git 中未重复上传这些大型产物。

硬件包已独立校验，尚未完成完整六核 RTL 或真板数值与持续 FPS 验证。30 FPS 是待板端验收的目标，单核仿真耗时和时序通过不代表整机帧率。

## 本机复核

从仓库根目录运行主机回归（输出目录必须尚不存在）：

```sh
python fpga/joint_lowlight_compact_d/scripts/run_host_tests.py --out /path/to/new_host_checks
python -m unittest discover -s fpga/joint_lowlight_compact_d/scripts -p 'test_*constraint*.py' -v
python fpga/joint_lowlight_compact_d/scripts/verify_delivery.py --zip /path/to/kv260_joint_fifo_hold_release_20261102_final.zip --out /path/to/new_zip_check.json
```

依赖项目脚本的约束回归可在 `scripts/` 目录执行。重新构建需要 Vivado/Vitis 2025.2、锁定模型/IP 和相应父版输入；当前发布的完整输入及生成 wrapper 在本地 ZIP 中。最终六节点方案使用 `targeted_fifo_policy.tcl`、`targeted_fifo_mapping.py` 及原约束独立审核；不上传已放弃的逐寄存器移位实验。

`evidence/release_20261102/` 对应本版；其余旧 evidence、CHANGE_REVIEW 和 REMOTE_AUDIT 保留历史身份，不能代替当前发布证据。原始失败日志与完整绑定链保留在本地包和构建目录。
