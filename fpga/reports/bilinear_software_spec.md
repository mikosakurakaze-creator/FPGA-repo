# Bilinear 软件真值规范（源码提取）

## 1. 任务目标与范围

本报告只从当前仓库的软件实现提取 `parameters_lowres` 到 `parameters_fullres` 的真实调用链、张量约定和尺寸处理规则，为后续 Bilinear HLS 设计提供可审核的软件依据。未修改软件或 HLS 算法，未编写 Bilinear HLS，未运行新的数值实验、HLS C Simulation、C Synthesis、RTL Co-simulation、Vivado Implementation 或板上测试。

## 2. 基线与数据来源

- 当前 Git 分支：`codex/curve-fp32-baseline`；检查时 HEAD：`6bdceba`。
- 软件实现：`model/zero_dce_pp/enhancement.py`、`model/zero_dce_pp/upstream/model.py`、`model/zero_dce_pp/preprocessing.py`、`model/zero_dce_pp/export_reference.py`。
- 已有参考元数据：`outputs/zero_dce_pp/reference/metadata.json`。其中记录参考导出环境 PyTorch `2.14.0+cpu`、CPU、`torch.float32`、`scale_factor=12`。这些是已有元数据记录，本次没有重新运行导出。
- 目标器件及 HLS 版本：本次仅阅读软件源码，不涉及器件和 HLS 工具。

## 3. 参数图放大的精确调用链

1. `enhancement.py:35-60` 的 `predict_parameters()` 先生成低分辨率、三通道参数图；末尾 `F.tanh(...)` 发生在放大**之前**（`:58-60`）。
2. `enhancement.py:63-79` 的 `resize_parameters()`：`scale_factor == 1` 时直接返回原参数张量；否则在 `:72` 调用 **`network.upsample(parameters)`**。随后仅核对输出 H/W 是否与调用者传入的 `output_size` 相等；不相等时抛出 `ValueError`。`output_size` 不是插值 API 的 `size` 参数。
3. `upstream/model.py:35-40` 创建网络时定义 **`nn.UpsamplingBilinear2d(scale_factor=self.scale_factor)`**。因此放大由该 PyTorch 模块执行，插值模式由 `UpsamplingBilinear2d` 指定为 bilinear；`scale_factor` 来自网络构造参数。仓库没有为这个上采样调用传入 `size`。
4. `export_reference.py:67-81` 在导出参考时依次调用 `predict_parameters()`、`resize_parameters(network, parameters_lowres, tuple(model_input.shape[-2:]))`，并保存两级参数图。`upstream/model.py:78-83` 官方 `forward()` 也使用同一个 `self.upsample(x_r)` 模块。

关键源码片段与位置：

```python
# model/zero_dce_pp/upstream/model.py:39-40
self.scale_factor = scale_factor
self.upsample = nn.UpsamplingBilinear2d(scale_factor=self.scale_factor)

# model/zero_dce_pp/enhancement.py:69-79
if network.scale_factor == 1:
    resized = parameters
else:
    resized = network.upsample(parameters)
if tuple(resized.shape[-2:]) != tuple(output_size):
    raise ValueError(
        "official scale-factor upsampling did not reproduce the input "
        "size; preprocess with dimensions divisible by scale_factor"
    )
return resized

# model/zero_dce_pp/export_reference.py:69-74
parameters_lowres = predict_parameters(network, model_input)
parameters_fullres = resize_parameters(
    network,
    parameters_lowres,
    tuple(model_input.shape[-2:]),
)
```

### PyTorch 调用参数

| 项目 | 本仓库实际设置 / 可确认行为 |
| --- | --- |
| 实际 API | `torch.nn.UpsamplingBilinear2d` 实例的 `forward`，通过 `network.upsample(parameters)` 调用 |
| `mode` | 由 `UpsamplingBilinear2d` 模块类型固定为 bilinear；放大调用没有单独传 `mode` 关键字 |
| `scale_factor` | `network.scale_factor`；当前参考元数据为 `12` |
| `size` | 未设置；使用 PyTorch 默认值 |
| `align_corners` | 仓库未显式设置；使用 PyTorch `UpsamplingBilinear2d` 默认值。本次只核对仓库源码，未另行核查对应 PyTorch 安装包内部实现，故不把默认值的具体数值写成仓库显式约定 |
| `recompute_scale_factor` | 未设置；使用 PyTorch 默认值 |
| `antialias` | 未设置；使用 PyTorch 默认值 |

注意 `enhancement.py:28-32` / `upstream/model.py:65-69` 的 **下采样输入图像** 使用另一处 `torch.nn.functional.interpolate(image, scale_factor=1/network.scale_factor, mode="bilinear")`；它不是低分辨率参数图放大所用的 API。该下采样调用的 `align_corners`、`recompute_scale_factor`、`antialias` 也未在仓库显式设置，使用 PyTorch 默认值。

## 4. Shape、layout 与不可整除尺寸

- `enhancement.py:15-17` 要求输入图像是 4 维 NCHW 且通道数为 3；`predict_parameters()` 的最终卷积输出 3 通道（`upstream/model.py:50`）。`export_reference.py:32-37` 将张量 layout 记录为 NCHW。
- 已有 `metadata.json` 中，`parameters_lowres.npy` 为 `torch.float32`、NCHW `[1,3,60,106]`，`parameters_fullres.npy` 为 `torch.float32`、NCHW `[1,3,720,1272]`；每个参数图分别有 19,080 和 2,747,520 个元素。`model_input.npy` 为 `[1,3,720,1272]`。
- `preprocessing.py:41-49` **先裁剪**输入 H/W：`H_crop = (H // scale_factor) * scale_factor`，`W_crop = (W // scale_factor) * scale_factor`，然后转成 NCHW。因此不可整除的原图会丢弃底部/右侧余数像素，不把上采样目标改成原图尺寸。尺寸小于 `scale_factor` 时抛出 `ValueError`。
- 本次已有参考元数据给出的例子：原图 H/W `720 × 1280`，`scale_factor=12`，预处理后为 `720 × 1272`；低分辨率参数图为 `60 × 106`，上采样结果为 `720 × 1272`。
- 若绕开预处理，`resize_parameters()` 仍只按模块的 `scale_factor` 放大，再与传入 `output_size` 做**严格相等检查**（`enhancement.py:74-78`）；不匹配即报错，没有回退到 `size=output_size` 的插值。仓库未给出任意不可整除原始尺寸在 PyTorch 插值内部的独立尺寸计算代码，因此本报告不假定这种绕开预处理的调用能产生指定原图尺寸。
- `scale_factor == 1` 时 `resize_parameters()` 不调用上采样模块；参数图直接作为结果，但仍执行输出 H/W 检查。

## 5. 其他操作与边界

- 参数预测末尾的 `F.tanh` 在上采样**之前**（`enhancement.py:58-60`）；上采样函数内部没有额外 `clamp`、`reshape`、`permute`、`cast`、量化或显式通道重排，只有条件分支、模块调用、尺寸核对与返回（`:63-79`）。
- 输入图像在更早的 `preprocessing.py:38-49` 做 `uint8 / 255.0`、`.float()`、裁剪、HWC→CHW `permute`、添加 batch 维和 `.contiguous()`；这些不是参数图上采样后的操作。
- `export_reference.py:89-91` 用 `save_tensor()` 保存已有真值；已有元数据注明原始张量没有 clipping 或 quantization（`export_reference.py:119-123`）。本次没有重新检查数组数值，也未验证任何 FPGA 输出误差。

## 6. 实际执行、结论与下一步

实际只运行了源码文本查阅、已有 `metadata.json` 查阅、`git branch --show-current`、`git rev-parse --short HEAD` 和 `git status --short`；没有运行 PyTorch 前向、数值比较或硬件工具。报告以源码中明确设置的参数和已有参考元数据为事实；PyTorch 调用中未显式给出的参数均标为“使用 PyTorch 默认值”，未自行补写坐标公式或默认数值。软件真值调用链已定位，报告可保留作为后续设计输入。后续若需要逐像素复现插值坐标，应先依据参考环境 PyTorch `2.14.0+cpu` 的实际库实现或独立真值测试确认其默认参数和边界规则；本任务未开始这一步。

本次仅新增本报告；没有修改软件源码、接口、HLS pragma 或位宽。无新的数值误差、资源、时钟、II 或 warning 数据可报告。未 commit，未 push。
