# 软件模型

本目录用于 V1 单模型低照度增强的软件实现、推理验证和可复现参考数据定义。

当前 Baseline 为 [Zero-DCE++](zero_dce_pp/README.md)，已经包含：

- 官方 PyTorch 源码的原样副本；
- 官方预训练权重 `Epoch99.pth`；
- RGB/NCHW 预处理；
- 参数预测、参数图插值和八次增强计算拆分；
- 单张图片推理入口；
- 官方 `forward` FP32 一致性验证工具；
- FPGA 参考数据导出工具。

已在一组本地 CPU 环境和固定输入上完成推理、一致性验证与参考数据导出，拆分实现和官方 `forward` 的增强结果及参数图误差为 0.0。该结果不代表 CUDA、其他 PyTorch 版本或 FPGA 实现已经验证。

数据集、虚拟环境、缓存和运行输出由 `.gitignore` 排除。模型输入、计算流程和待定硬件接口见 [Zero-DCE++ 模型规格](../docs/zero_dce_pp_model_spec.md)。
