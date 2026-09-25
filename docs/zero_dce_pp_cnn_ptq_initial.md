# Zero-DCE++ 参数预测 CNN：初步 INT8 量化实验

这是一个可重复运行的单图 PTQ（训练后量化）原型，不是已定版的 FPGA 部署方案。
运行脚本是 `deployment/ptq_cnn_initial.py`。这是早期 CNN-only 对照实验，当前完整整数候选方案见 `zero_dce_pp_integer_quantization_report.md`。

## 做了什么

- 对七个 CNN 模块中的 14 个卷积层做量化：权重逐输出通道对称 INT8，激活逐张量非对称 UINT8，偏置和乘加为 INT32。
- 使用 `data/test/night_01.jpg` 统计各层激活范围，并在同一张图上评估。因此结果仅说明这张图的表现，不能代表泛化效果。
- 下采样、输出 Tanh、参数图插值和八次曲线增强仍使用 FP32，以便单独观察 CNN 量化造成的误差。
- 卷积通过 PyTorch 整数运算模拟，并非 HLS/FPGA 速度测试。权重和偏置分别保存为真实的 INT8/INT32 数组。

## 这次的结果

| 比较 | 平均绝对误差 | 最大绝对误差 |
|---|---:|---:|
| CNN 低分辨率参数图，量化 vs FP32 | 0.00169 | 0.00877 |
| 最终增强图的 FP32 数值，量化 CNN vs 原模型 | 0.00195 | 0.01553 |
| 最终 PNG 的 8-bit 像素级差异 | 0.499 灰度级 | 4 灰度级 |

重新计算的 FP32 参数图和最终增强图与仓库已保存的 FP32 参考数组完全一致（误差 0）。
详细数值、每层误差和实验限制见本地 `outputs/zero_dce_pp/quantization/initial/report.json`。

## 文件

以下文件位于本地 `outputs/zero_dce_pp/quantization/initial/`，被 Git 忽略：

- `comparison.png`：原图、FP32、量化 CNN、放大 8 倍的差异图。
- `enhanced_fp32.png`、`enhanced_int8.png`：可直接查看的效果图。
- `parameters_lowres_fp32.npy`、`parameters_lowres_int8.npy`：CNN 三通道参数图，可做数值比较。
- `enhanced_int8.npy`：未经 PNG 截断的量化 CNN 最终增强结果。
- `cnn_int8_weights.npz`：14 层的 INT8 权重和 INT32 偏置。
- `cnn_quantization.json`：逐层量化刻度、零点、权重尺寸和卷积配置。
- `report.json`：误差、环境、数据来源及局限性。

在本仓库根目录、使用具备依赖的 Python 环境运行：

```powershell
python .\deployment\ptq_cnn_initial.py
```

下一步应补充不同亮度、噪声和正常曝光图片，将校准集与评估集分开，再决定是否采用这套量化规则。FPGA 端还需要冻结数据布局、舍入和重定标实现，并做逐层对照。
