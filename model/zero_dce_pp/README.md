# Zero-DCE++ 软件 Baseline

本目录集成 Zero-DCE++ 官方 PyTorch 实现，作为 V1 的第一个低照度增强软件 Baseline。当前工作仅完成源码、权重和可拆分接口的集成；未运行推理、训练、测试或兼容性验证。

## 官方来源

- 官方仓库：<https://github.com/Li-Chongyi/Zero-DCE_extension>
- 上游目录：`Zero-DCE++/`
- 使用的上游提交：`09f202b690f82da939b8e6ec8535960ae97ad8bd`
- 提交日期：2022-06-19
- 论文：Chongyi Li, Chunle Guo, Chen Change Loy, “Learning to Enhance Low-Light Image via Zero-Reference Deep Curve Estimation,” IEEE TPAMI, 2021
- DOI：<https://doi.org/10.1109/TPAMI.2021.3063604>
- 项目页：<https://li-chongyi.github.io/Proj_Zero-DCE++.html>

官方 README 声明代码仅用于学术研究，并采用 Attribution-NonCommercial 4.0 International License。官方仓库没有独立 LICENSE 文件；本项目在 [UPSTREAM_LICENSE.md](UPSTREAM_LICENSE.md) 中保留该许可说明、作者信息和引用。使用代码及预训练权重前应确认用途符合非商业限制。

## 目录与代码边界

```text
zero_dce_pp/
├── upstream/          官方源码原样副本
├── weights/           官方 Epoch99.pth 及来源说明
├── preprocessing.py   本项目输入适配
├── enhancement.py     本项目 forward 拆分接口
├── inference.py       本项目模型加载与单图入口
└── README.md
```

`upstream/` 中的 `model.py`、`lowlight_test.py`、`lowlight_train.py`、`dataloader.py` 和 `Myloss.py` 均从上述提交逐字节复制，未修改。数据集、官方缓存和示例输出未复制。本项目适配代码位于 `upstream/` 外。

## 权重

官方仓库包含 `Zero-DCE++/snapshots_Zero_DCE++/Epoch99.pth`。文件仅 52,395 字节，因此在保留来源和非商业使用提示的前提下纳入本目录：

```text
weights/Epoch99.pth
SHA-256: CA8855B90DF9A80FA4195A831F33D3476B1964F787EB70602797C773067F3B84
```

它是官方训练脚本通过 `torch.save(DCE_net.state_dict(), ...)` 写出的 PyTorch state dictionary，不是 TorchScript 或 ONNX 文件。只应从可信来源加载 pickle-based PyTorch 权重。

## 已拆分的软件接口

- `preprocess_image`：读取图像，显式转为 RGB，除以 255，转换为 float NCHW 张量，并按官方测试脚本将高宽裁到 `scale_factor` 的整数倍。
- `predict_parameters`：按官方 `forward` 的层次和拼接顺序生成低分辨率 3 通道参数图。
- `resize_parameters`：调用官方网络实例中的 `UpsamplingBilinear2d` 恢复参数图尺寸。
- `apply_enhancement`：执行源码中的增强映射，共 8 次，不做输出裁剪。
- `enhance_image`：串联参数预测、参数图放大和逐像素增强。
- `enhance_file`：加载权重和输入图像，返回增强张量与参数图，不隐式保存或裁剪结果。

适配层增加的显式 RGB 转换、输入形状检查和尺寸检查属于边界保护，不改变网络层、通道数、激活函数或增强公式。拆分结果尚未与官方 `forward` 做运行时逐元素对比。

## 官方环境要求

官方 README 给出的环境为：

- Python 3.7
- PyTorch 1.0.0
- torchvision 0.2.1
- CUDA 10.0
- OpenCV

源码还直接导入 NumPy 和 Pillow。官方依赖版本较旧，本项目没有修改团队全局 Python 环境，也没有安装依赖。新版本 PyTorch/Pillow 下可能涉及插值默认行为、`F.tanh` 弃用、`Image.ANTIALIAS` 移除以及 `torch.load` 默认参数变化；兼容性均待验证。

## 预期使用方式

以下是计划中的 API 形态，不代表已经运行验证：

```python
from model.zero_dce_pp.inference import enhance_file

enhanced, parameter_map = enhance_file(
    image_path="path/to/input.png",
    weights_path="model/zero_dce_pp/weights/Epoch99.pth",
    device="cpu",
    scale_factor=12,
)
```

官方测试脚本使用 CUDA，并把输入高宽裁到 12 的整数倍。适配入口默认使用 CPU，调用方可显式选择设备。当前接口返回张量，不决定输出图片编码，以免保存阶段的隐式裁剪混入模型计算结果。

## 后续 FPGA 对接数据

后续验证完成后，需要导出并固定：

- 预处理后的 NCHW 输入张量；
- 每个 depthwise/pointwise 卷积的权重、偏置及输出；
- ReLU 后的 `x1` 至 `x6`；
- 三处通道拼接结果；
- `tanh` 前后参数图；
- 双线性插值后的全分辨率参数图；
- 8 次增强迭代各自的输出；
- 最终增强图，以及软件参考误差容限。

量化位宽、定点格式、张量布局、舍入和饱和规则均为 TBD。
