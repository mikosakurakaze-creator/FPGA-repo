# Curve 定点化前数据范围分析报告

本报告整理当前软件参考数据的 FP32 实测范围。没有修改 HLS 算法、接口、pragma 或数值类型，也没有实施定点化。以下候选格式仅供后续评估。

## 数据来源与实际运行

分析脚本：`evaluation/curve_range_analysis.py`。数据来自 `outputs/zero_dce_pp/reference/` 下的 `model_input.npy`、`parameters_fullres.npy`、`enhancement_iter_01.npy` 至 `enhancement_iter_08.npy`、`enhanced.npy`，并用 `metadata.json` 核对形状 `[1,3,720,1272]` 和 FP32 类型。

实际使用 Codex 随附的 Python 及 NumPy 2.3.5 运行：

```powershell
& 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' evaluation/curve_range_analysis.py outputs/zero_dce_pp/reference | Set-Content -LiteralPath outputs/zero_dce_pp/curve_range_analysis.json -Encoding utf8
```

完整逐轮统计保存在 Git 忽略的 `outputs/zero_dce_pp/curve_range_analysis.json`。本报告保存时没有重新运行实验。

## 参考数组实测范围

每个文件均有 **2,747,520** 个元素。

| 文件 | min | max | max_abs |
|---|---:|---:|---:|
| `model_input.npy` | 0 | 1 | 1 |
| `parameters_fullres.npy` | −0.350147754 | −0.057052601 | 0.350147754 |
| `enhancement_iter_01.npy` | 0 | 1 | 1 |
| `enhancement_iter_02.npy` | 0 | 1 | 1 |
| `enhancement_iter_03.npy` | 0 | 1 | 1 |
| `enhancement_iter_04.npy` | 0 | 1 | 1 |
| `enhancement_iter_05.npy` | 0 | 1 | 1 |
| `enhancement_iter_06.npy` | 0 | 1 | 1 |
| `enhancement_iter_07.npy` | 0 | 1 | 1 |
| `enhancement_iter_08.npy` | 0 | 1 | 1 |
| `enhanced.npy` | 0 | 1 | 1 |

## 八轮计算中间量

下表汇总全部 **8 × 2,747,520 = 21,980,160** 次逐元素计算；`x` 指每轮更新前的值。乘、减、乘 A、加回 x 均按 float32 执行。逐轮结果与各自 `.npy`、最终结果与 `enhanced.npy` 的最大及平均绝对误差都为 **0**。

| 中间量 | min | max | max_abs |
|---|---:|---:|---:|
| `x` | 0 | 1 | 1 |
| `x*x` | 0 | 1 | 1 |
| `x*x-x` | −0.25 | 0 | 0.25 |
| `A*(x*x-x)` | 0 | 0.083519571 | 0.083519571 |

## 仅供评估的有符号定点候选

对 `ap_fixed<W,I>`，小数位为 `F=W−I`，量化步长为 `2^-F`。以下格式**尚未实施，也未验证量化误差**。

| 候选用途 | 格式 | 整数位理由 | 小数位 | 步长 |
|---|---|---|---:|---:|
| 所有信号共用，初步低位宽 | `ap_fixed<16,2>` | 范围 `[−2, 2−步长]`，包含实测的精确 `1.0` | 14 | 6.103515625×10⁻⁵ |
| 所有信号共用，提高精度 | `ap_fixed<20,2>` | 同样覆盖全部实测范围 | 18 | 3.814697266×10⁻⁶ |
| 所有信号共用，进一步提高精度 | `ap_fixed<24,2>` | 同样覆盖全部实测范围 | 22 | 2.384185791×10⁻⁷ |
| 分信号候选：仅 A、差值、乘积 | `ap_fixed<16,0>` | 范围 `[−0.5, 0.5−步长]`，覆盖这三项实测范围；**不适合**含 `1.0` 的 x | 16 | 1.525878906×10⁻⁵ |

这些整数位只依据**当前这一组参考数据**说明；换图、逐步量化后的误差传播、乘法中间位宽、舍入与溢出策略都还需要单独验证。
