# Zero-DCE++ V1 软件模型规格

本文档基于 Zero-DCE++ 官方仓库提交 `09f202b690f82da939b8e6ec8535960ae97ad8bd` 中的实际源码整理。当前未执行推理或数值对比；凡涉及运行时版本行为或硬件取舍的内容均明确标记为待验证或 TBD。

## 1. 输入与输出

官方测试脚本的输入处理流程如下：

1. 使用 Pillow 打开图像；
2. 转为 NumPy 数组并除以 `255.0`；
3. 转为 PyTorch float tensor；
4. 高、宽分别向下裁剪为 12 的整数倍；
5. 从 HWC 转为 CHW，并增加 batch 维；
6. 移至 CUDA。

官方脚本没有显式调用 RGB 转换，但网络第一层固定接收 3 通道。本项目适配层显式执行 RGB 转换以落实该约束。

默认测试路径中的张量约定：

| 项目 | 规格 |
| --- | --- |
| 输入布局 | NCHW |
| 输入通道顺序 | RGB |
| 输入数据类型 | PyTorch float（通常为 float32） |
| 输入数值范围 | 由 8-bit 图像除以 255 得到，预期为 [0, 1] |
| batch | 官方单图测试为 1，网络本身保留 N 维 |
| 网络输出 | `(enhanced_image, x_r)` |
| 输出布局 | 两者均为 NCHW |
| 输出通道 | 两者均为 3 |
| 显式输出裁剪 | 无 |

`torchvision.utils.save_image` 属于序列化阶段；可能发生的保存裁剪不属于网络 `forward`。

## 2. 模型总体流程

```text
RGB input x
  ├─ if scale_factor != 1:
  │    bilinear downsample by 1 / scale_factor
  │
  └─ 7 × depthwise-separable convolution blocks
       ├─ ReLU after blocks 1..6
       ├─ skip concatenations before blocks 5, 6, 7
       └─ tanh after block 7 → low-resolution x_r
                                │
                                └─ UpsamplingBilinear2d(scale_factor)
                                     → full-resolution x_r
                                          │
                                          └─ repeat 8 times:
                                               x ← x + x_r × (x² − x)
```

官方测试脚本实例化 `enhance_net_nopool(scale_factor=12)`；官方训练脚本默认参数是 `scale_factor=1`。两者不同，后续建立参考数据时必须记录所用值。

## 3. 网络层定义

每个 `CSDN_Tem(in_ch, out_ch)` 依次包含：

1. 3×3 depthwise Conv2d：stride 1，padding 1，groups = `in_ch`，默认带 bias；
2. 1×1 pointwise Conv2d：stride 1，padding 0，groups 1，默认带 bias。

主网络设置 `number_f = 32`：

| 层 | 输入 | depthwise 权重形状 | pointwise 权重形状 | 输出通道 | 后处理 |
| --- | --- | --- | --- | --- | --- |
| e_conv1 | RGB 输入 | [3,1,3,3] | [32,3,1,1] | 32 | ReLU |
| e_conv2 | x1 | [32,1,3,3] | [32,32,1,1] | 32 | ReLU |
| e_conv3 | x2 | [32,1,3,3] | [32,32,1,1] | 32 | ReLU |
| e_conv4 | x3 | [32,1,3,3] | [32,32,1,1] | 32 | ReLU |
| e_conv5 | concat(x3,x4) | [64,1,3,3] | [32,64,1,1] | 32 | ReLU |
| e_conv6 | concat(x2,x5) | [64,1,3,3] | [32,64,1,1] | 32 | ReLU |
| e_conv7 | concat(x1,x6) | [64,1,3,3] | [3,64,1,1] | 3 | tanh |

所有拼接均沿通道维 `dim=1`。按源码中默认 bias 计算，网络共 10,561 个可训练标量参数。该计数来自层定义，尚未通过运行时工具复核。

## 4. 参数图生成与插值

若 `scale_factor == 1`，参数预测直接使用输入分辨率。否则官方源码调用：

```python
F.interpolate(x, scale_factor=1 / scale_factor, mode="bilinear")
```

随后 7 个卷积块生成 3 通道参数图，并通过 `tanh`。放大阶段使用模型构造时创建的：

```python
nn.UpsamplingBilinear2d(scale_factor=scale_factor)
```

官方代码没有显式给下采样指定 `align_corners`；上采样则依赖 `UpsamplingBilinear2d` 在所用 PyTorch 版本中的语义。由于官方环境为 PyTorch 1.0.0，而现代 PyTorch 的默认行为和弃用提示可能不同，插值逐点一致性必须在指定版本组合下验证。适配层调用官方网络自身的 upsample 模块，不另行猜测该参数。

当测试使用 `scale_factor=12` 时，官方脚本先裁剪输入尺寸为 12 的整数倍，从而使放大后的参数图与输入对齐。

## 5. 增强映射

源码中的单次更新为：

```text
x_next = x + x_r × (x² − x)
```

同一个全分辨率 3 通道参数图 `x_r` 连续使用 8 次。运算为逐元素运算，正负号是加号加上 `x_r × (x² − x)`。第 4 次结果在源码中另命名为 `enhance_image_1`，但没有改变计算公式。第 8 次结果作为最终增强图返回。

网络内部没有 `clamp`、饱和或量化操作。FPGA 版本的溢出、舍入和饱和策略均为 TBD，必须以浮点参考误差分析为依据。

## 6. 权重格式

官方权重路径：

```text
Zero-DCE++/snapshots_Zero_DCE++/Epoch99.pth
```

- 大小：52,395 字节
- SHA-256：`CA8855B90DF9A80FA4195A831F33D3476B1964F787EB70602797C773067F3B84`
- 保存方式：训练脚本对 `DCE_net.state_dict()` 调用 `torch.save`
- 本项目路径：`model/zero_dce_pp/weights/Epoch99.pth`

它不是包含完整模型定义的部署格式。后续导出前应验证所有键名、形状、dtype、bias 和加载结果，并记录 PyTorch 版本。

## 7. FPGA 对接参考数据

后续软件验证阶段至少应导出：

1. 裁剪及归一化后的输入；
2. 下采样结果；
3. 每个 depthwise 卷积输出；
4. 每个 pointwise 卷积输出；
5. 每个 ReLU 输出 `x1..x6`；
6. `concat(x3,x4)`、`concat(x2,x5)`、`concat(x1,x6)`；
7. e_conv7 输出和 tanh 后的低分辨率参数图；
8. 放大后的参数图；
9. 8 次曲线更新的中间结果；
10. 最终增强输出；
11. 权重和 bias 的确定性导出文件及校验值。

以下硬件项目尚未确定：

- 权重、激活、累加器位宽：TBD
- 定点小数位和量化尺度：TBD
- 舍入与饱和规则：TBD
- 张量存储布局和通道打包：TBD
- 插值硬件实现及边界规则：TBD
- 片上缓存、并行度和流水线结构：TBD
- 软件/硬件允许误差：TBD

## 8. 待验证事项

- 拆分接口与官方 `forward` 的逐元素一致性；
- 官方 `Epoch99.pth` 在选定现代 PyTorch 版本下的加载兼容性；
- PyTorch 1.0.0 与目标版本的双线性插值数值差异；
- 显式 RGB 转换对非 RGB 输入的预期行为；
- 官方裁剪策略是否适合作为最终产品接口，或是否需要另行定义 padding；
- 输出理论范围和保存图像时的裁剪策略；
- 固定参考图片、逐层 golden tensors 与误差容限；
- CPU/GPU 可重复性和推理性能。

在完成上述验证前，不应将本适配层描述为已验证等价或可部署。
