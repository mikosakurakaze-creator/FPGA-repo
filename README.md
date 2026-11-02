# 复杂环境道路监控视觉增强系统

> 仓库初始占位标识：`oiiaioiiai`

本项目面向夜间、雨天、雾天等复杂环境下的道路监控画面，研究轻量化深度学习视觉增强模型及其在 FPGA 平台上的高效部署。计划通过模型量化、并行计算、流水线设计和片上数据复用，提高嵌入式视觉增强的处理效率。

## 当前阶段

当前处于 **V1 单模型低照度增强软件 Baseline 阶段**。工程脚手架和 Zero-DCE++ 官方源码集成已完成；单图推理、官方 forward 一致性验证和参考数据导出已在本地 CPU 环境实际运行。FPGA 实现尚未开始。

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
skill/          可独立复用的技能包与使用说明
```

## 竞赛目录对照与技能包

竞赛指南 3.3.5.4 的技能包位置采用根目录 [skill/](skill/README.md)，其中提供 [PYNQ Overlay 联调与校验](skill/pynq-overlay-validation/README.md)及[证据驱动 FPGA 排错](skill/evidence-driven-fpga-debug/README.md)。各技能包含独立 README、使用入口、经验来源和实际验证范围，可按其说明单独复制复用。

工程其余部分保留已有组织方式，对照如下；此表说明目录用途，不代表对应流程已全部完成。

| 推荐目录 | 本仓库对应位置 |
| --- | --- |
| `src/` 设计源码 | `model/`、`models/`、`deployment/`、`fpga/hls/`、`weather_restore_lab/` |
| `sim/` 仿真或验证 | `evaluation/`、各模型的验证脚本及报告 |
| `build/` 构建与实现 | `fpga/vivado/`、各工程附带的构建配置与脚本 |
| `board/` 板端程序与说明 | `board/`、各模型的板端交接说明 |
| `data/` 测试数据与参考结果 | `data/`、经审核的参考数据；其余运行输出按 `.gitignore` 留在本地 |
| `skill/` 技能包 | [skill/](skill/README.md) |
| `report/` 设计与协作材料 | `docs/`、`doc/` 及各技能的来源与验证说明 |

本次技能发布不改变上述源码、模型或板端实现。PYNQ 技能中的 Host PASS 不是 PYNQ 真板 PASS，排错案例中的历史状态也不覆盖团队后续版本。

## 参与开发

1. 软件侧统一在长期分支 `feat/software` 开发；FPGA 侧使用团队约定的独立分支。
2. 在已分配分支完成职责明确的任务，避免提交数据集、非白名单权重和工具生成文件。
3. 修改完成后先展示差异并等待人工审核；只有获得当次明确授权后才能提交、推送或创建 Pull Request。
4. 经代码和文档检查后再由团队决定是否合并到 `main`。

详细约定见 [V1 范围](docs/v1_scope.md)、[模块接口](docs/interfaces.md) 和 [团队工作流](docs/team_workflow.md)。

## Zero-DCE++ 软件工具

从项目根目录运行，输入图片由开发者自行提供：

```text
python -m model.zero_dce_pp.inference --input path/to/image.png --device cpu --scale-factor 12
python -m model.zero_dce_pp.validate_consistency --input path/to/image.png --device cpu --scale-factor 12 --atol 1e-6
python -m model.zero_dce_pp.export_reference --input path/to/image.png --device cpu --scale-factor 12
```

默认权重为 `model/zero_dce_pp/weights/Epoch99.pth`，默认生成内容位于已被 Git 忽略的 `outputs/zero_dce_pp/`。详细说明见 [Zero-DCE++ Baseline](model/zero_dce_pp/README.md) 和 [模型规格](docs/zero_dce_pp_model_spec.md)。本地 CPU 验证记录见对应文档；CUDA、其他 PyTorch 版本和 FPGA 结果仍待验证。
