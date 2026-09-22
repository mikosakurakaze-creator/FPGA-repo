# 复杂环境道路监控视觉增强系统

> 仓库初始占位标识：`oiiaioiiai`

本项目面向夜间、雨天、雾天等复杂环境下的道路监控画面，研究轻量化深度学习视觉增强模型及其在 FPGA 平台上的高效部署。计划通过模型量化、并行计算、流水线设计和片上数据复用，提高嵌入式视觉增强的处理效率。

## 当前阶段

当前处于 **V1 单模型低照度增强软件 Baseline 阶段**。工程脚手架和 Zero-DCE++ 官方源码集成已完成，软件推理、一致性验证和参考数据导出工具已编写，但尚未实际运行验证。FPGA 实现尚未开始。

当前仓库已包含 Zero-DCE++ 官方模型、官方预训练权重及本项目适配工具。工具存在不代表其已在本机环境验证可用，也不表示本地已安装完整深度学习或 FPGA 工具链。

暂定硬件平台为 PYNQ-Z2（Zynq-7000 XC7Z020），暂定工具包括 Python、PyTorch、C++、Vitis HLS、Vivado 和 PYNQ。

## 目录结构

```text
model/          纯软件模型复现与参考结果
deployment/     量化、导出及上板前准备
fpga/hls/       HLS 核设计
fpga/vivado/    Vivado 工程与系统集成
board/          PS 端控制与板端运行
evaluation/     功能、性能及 Base 对比
configs/        可版本管理的实验与部署配置
docs/           项目范围、接口、路线图和协作规范
```

## 参与开发

1. 同步稳定的 `main` 分支，并从其创建个人功能分支。
2. 在个人分支完成单一、明确的任务，避免提交数据集、模型权重和工具生成文件。
3. 提交前检查改动及接口文档；完成后推送个人分支并发起 Pull Request。
4. 经代码和文档检查后再合并到 `main`。

详细约定见 [V1 范围](docs/v1_scope.md)、[模块接口](docs/interfaces.md) 和 [团队工作流](docs/team_workflow.md)。

## Zero-DCE++ 软件工具

从项目根目录运行，输入图片由开发者自行提供：

```text
python -m model.zero_dce_pp.inference --input path/to/image.png --device cpu --scale-factor 12
python -m model.zero_dce_pp.validate_consistency --input path/to/image.png --device cpu --scale-factor 12 --atol 1e-6
python -m model.zero_dce_pp.export_reference --input path/to/image.png --device cpu --scale-factor 12
```

默认权重为 `model/zero_dce_pp/weights/Epoch99.pth`，默认生成内容位于已被 Git 忽略的 `outputs/zero_dce_pp/`。详细说明见 [Zero-DCE++ Baseline](model/zero_dce_pp/README.md) 和 [模型规格](docs/zero_dce_pp_model_spec.md)。上述工具尚未实际运行验证。
