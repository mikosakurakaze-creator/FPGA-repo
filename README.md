# 复杂环境道路监控视觉增强系统

> 仓库初始占位标识：`oiiaioiiai`

本项目面向夜间、雨天、雾天等复杂环境下的道路监控画面，研究轻量化深度学习视觉增强模型及其在 FPGA 平台上的高效部署。计划通过模型量化、并行计算、流水线设计和片上数据复用，提高嵌入式视觉增强的处理效率。

## 当前阶段

当前处于 **V1 单模型低照度增强软件 Baseline、候选量化与 CNN HLS top 阶段**。工程脚手架和 Zero-DCE++ 官方源码集成已完成；单图推理、官方 forward 一致性验证、参考数据导出及端到端整数软件原型已在本地 CPU 环境实际运行。CNN HLS top 和 Q14 DDR 输出合同已经写入 `fpga/hls/` 与 `configs/`。Vitis 2025.2 C 仿真及 HLS 综合已运行；综合估计时钟为 40.443 ns，未达到 10 ns 目标。RTL 协同仿真、Vivado 集成和板端验收尚未执行。

当前仓库已包含 Zero-DCE++ 官方模型、官方预训练权重及本项目适配工具。本地一次验证使用 PyTorch 2.14.0+cpu、CPU、`scale_factor=12`，拆分实现与官方 forward 的增强结果和参数图最大/平均绝对误差均为 0.0；该结果只代表记录的环境和输入，不代表其他平台已验证，也不表示本地已安装完整 FPGA 工具链。

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

1. 软件侧统一在长期分支 `feat/software` 开发；FPGA 侧使用团队约定的独立分支。
2. 在已分配分支完成职责明确的任务，避免提交数据集、非白名单权重和工具生成文件。
3. 修改完成后先展示差异并等待人工审核；只有获得当次明确授权后才能提交、推送或创建 Pull Request。
4. 经代码和文档检查后再由团队决定是否合并到 `main`。

协作约定见 [AGENTS.md](AGENTS.md)；量化实验的当前范围与限制见 [量化实验报告](docs/zero_dce_pp_integer_quantization_report.md)。

## Zero-DCE++ 软件工具

从项目根目录运行，输入图片由开发者自行提供：

```text
python -m model.zero_dce_pp.inference --input path/to/image.png --device cpu --scale-factor 12
python -m model.zero_dce_pp.validate_consistency --input path/to/image.png --device cpu --scale-factor 12 --atol 1e-6
python -m model.zero_dce_pp.export_reference --input path/to/image.png --device cpu --scale-factor 12
```

默认权重为 `model/zero_dce_pp/weights/Epoch99.pth`，量化运行结果位于被 Git 忽略的 `outputs/zero_dce_pp/quantization/`。模型细节及本地 CPU 验证记录见 [Zero-DCE++ Baseline](model/zero_dce_pp/README.md)；CUDA、其他 PyTorch 版本和 FPGA 结果仍待验证。

## 候选整数化实验

当前候选规则为 CNN INT8 权重、INT16 激活、INT32 偏置/累加；CNN 输出的 `A_low` 和参数插值使用 Q14，曲线图像计算使用 Q15。实现位于 [deployment/zero_dce_integer_ptq.py](deployment/zero_dce_integer_ptq.py)，逐层参数位于 [configs/zero_dce_pp_integer_rules.json](configs/zero_dce_pp_integer_rules.json)，CNN→Bilinear 接口见 [configs/zero_dce_pp_a_low_interface.json](configs/zero_dce_pp_a_low_interface.json)，过程、误差及复现方法见 [量化实验报告](docs/zero_dce_pp_integer_quantization_report.md)。早期 CNN-only 试验见 [初步 PTQ 记录](docs/zero_dce_pp_cnn_ptq_initial.md)。生成的权重、逐层测试向量、效果图和 HLS 打包数组保存在受 Git 忽略的 `outputs/zero_dce_pp/quantization/`；软件端需运行脚本生成这些文件。该方案尚缺独立真实图片评估和硬件验证。

CNN HLS top、m_axi DDR `A_low` 输出、工作区和 `ap_done` 时序合同见 [HLS CNN contract](docs/zero_dce_pp_hls_cnn_contract.md)。Vitis 2025.2 C 仿真与 HLS 综合结果见 [HLS 运行说明](fpga/hls/README.md)；Vivado 集成和板端验收尚未执行。
