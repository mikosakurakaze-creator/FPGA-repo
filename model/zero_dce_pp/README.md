# Zero-DCE++ 软件 Baseline

本目录集成 Zero-DCE++ 官方 PyTorch 实现，作为 V1 的第一个低照度增强软件 Baseline。官方源码、权重和可拆分接口已集成；单图推理、官方 forward 一致性验证及参考数据导出已经在本地 CPU 环境实际运行。

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

适配层增加的显式 RGB 转换、输入形状检查和尺寸检查属于边界保护，不改变网络层、通道数、激活函数或增强公式。已在记录的本地 CPU 环境中与官方 `forward` 直接比较 FP32 Tensor，增强结果和全分辨率参数图均得到零误差；其他环境仍需重复验证。

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

## 推理、验证与参考导出命令

以下命令均从项目根目录执行。将 `path/to/image.png` 替换为本地测试图片；本项目不提供或下载数据集。

单张图片推理：

```text
python -m model.zero_dce_pp.inference --input path/to/image.png --weights model/zero_dce_pp/weights/Epoch99.pth --output-dir outputs/zero_dce_pp/inference --device cpu --scale-factor 12
```

官方 forward 与拆分接口的 FP32 一致性验证：

```text
python -m model.zero_dce_pp.validate_consistency --input path/to/image.png --weights model/zero_dce_pp/weights/Epoch99.pth --report outputs/zero_dce_pp/consistency_report.json --device cpu --scale-factor 12 --atol 1e-6
```

FPGA 参考数据导出：

```text
python -m model.zero_dce_pp.export_reference --input path/to/image.png --weights model/zero_dce_pp/weights/Epoch99.pth --output-dir outputs/zero_dce_pp/reference --device cpu --scale-factor 12
```

CUDA 可用且环境正确时，可把 `--device cpu` 改为 `--device cuda` 或 `cuda:0`。上述三个命令已经在本地 CPU 环境运行；CUDA 路径尚未验证。

### 推理输出

`inference.py` 将生成：

- `original_input.png`：Pillow 解码并转为 RGB 的原始尺寸图像；
- `model_input.npy`：实际送入网络的 FP32 NCHW 张量；
- `model_input.png`：模型输入预览；
- `enhanced.npy`：未裁剪的 FP32 增强结果；
- `enhanced.png`：将增强结果裁到 [0,1] 后量化为 uint8 的预览；
- `parameter_map.npy`：未修改的 FP32 全分辨率参数图；
- `parameter_map.png`：把 [-1,1] 映射到 [0,1] 后生成的参数图预览；
- `metadata.json`：尺寸、设备、PyTorch 版本、权重校验值和 PNG 转换策略。

数值比较和 FPGA golden data 必须使用 `.npy`，不得使用 PNG。

### 一致性报告

`validate_consistency.py` 直接比较两条路径的 FP32 tensor，分别报告增强图和全分辨率参数图的最大绝对误差、平均绝对误差及是否满足 `--atol`。报告同时记录 PyTorch 版本、设备、输入尺寸和 `scale_factor`。

### 参考数据输出

`export_reference.py` 输出预处理输入、下采样输入、低/全分辨率参数图、八次增强迭代结果、最终增强图和 `metadata.json`。本阶段不导出各卷积层中间值。

## 已记录的软件验证

本地验证输入为 `night_01.jpg`，原始尺寸 941×1672，按官方规则实际送入模型的 NCHW 尺寸为 `[1, 3, 936, 1668]`。验证环境和结果：

- PyTorch：`2.14.0+cpu`
- 设备：CPU
- dtype：`torch.float32`
- `scale_factor`：12
- 绝对容差：`1e-6`
- 增强结果最大/平均绝对误差：`0.0 / 0.0`
- 全分辨率参数图最大/平均绝对误差：`0.0 / 0.0`
- `consistency_passed`：`True`
- 权重 SHA-256：`CA8855B90DF9A80FA4195A831F33D3476B1964F787EB70602797C773067F3B84`

推理结果、验证报告和参考数组位于被 Git 忽略的本地 `outputs/zero_dce_pp/`，不纳入版本控制。该记录不覆盖 CUDA、其他 PyTorch 版本或其他输入。
