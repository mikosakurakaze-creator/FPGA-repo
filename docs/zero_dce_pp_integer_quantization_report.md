# Zero-DCE++ 端到端整数化实验报告

日期：2026-09-23  
状态：**软件整数仿真已跑通；不是 FPGA 部署验收或最终画质定版。**

## 1. 目标与结论

本实验把本仓库 Zero-DCE++ 的**完整单图前向链路**改成可复现的整数运算原型：RGB 预处理/缩小、14 层卷积、ReLU/拼接、Tanh、参数图双线性插值、八次曲线增强，以及输出 `uint8`。没有改动官方源码或权重。

选择 **INT8 权重 + INT16 激活 + INT32 偏置/卷积累加**。CNN 中有深度卷积、三处拼接和多层误差传播；INT16 激活给中间特征更多精度。CNN 输出的低分辨率参数图 `A_low` 和插值后参数图使用 Q14；曲线图像计算使用 Q15。CPU 原型在计算卷积时用 INT64 容器防止仿真过程溢出，但按 INT32 范围约束和检查累加结果；这不等于已综合出 INT32 硬件。

对当前唯一真实测试图 `night_01.jpg`，整数版相对 FP32：低分辨率参数图平均绝对误差 **0.001720**，最终增强数值平均绝对误差 **0.002180**，最终 PNG 平均差 **0.556 个 8-bit 灰度级**、最大差 **3 级**。肉眼对照见 `night_01_comparison.png`。结果表明**这套规则在当前输入上可用作继续开发的候选**，不能据此证明其他场景的画质或板端性能。

## 2. 输入、校准与参考

- 模型：官方 Zero-DCE++ `Epoch99.pth`，SHA-256 `CA8855B90DF9A80FA4195A831F33D3476B1964F787EB70602797C773067F3B84`；`scale_factor=12`。
- 原图 `720×1280`；按官方测试规则裁成 `720×1272`；CNN 输入为 `60×106`；参数图为 `3×60×106`。
- FP32 参考由仓库软件链路重新计算；参数图和最终图与仓库已有 `.npy` 参考的最大误差均为 **0**。
- 校准数据：从同一张 `night_01.jpg` 确定性生成的暗图、极暗加噪、增亮、低对比度，加全黑/全白边界输入。没有用原图本身统计动态范围；但这些素材仍与评估原图**同源**，不是真正独立的校准/测试集。
- 逐层记录 FP32 激活绝对值最大值，据此选每层 INT16 小数位；对每个输出通道的权重分别选 INT8 小数位。配置在 `configs/zero_dce_pp_integer_rules.json`。

## 3. 冻结的候选整数规则

| 环节 | 规则 |
|---|---|
| 输入 | RGB `uint8`，高宽向下裁到 12 的倍数；`round_even(pixel×2^14/255)` 得 Q14 正数。 |
| CNN 缩小 | `scale_factor=12`、双线性 `align_corners=False`；对整 12 倍输入，每个小图点取原图坐标 `(12i+5.5,12j+5.5)` 的四邻域均值，整数除法舍入到偶数。 |
| CNN 激活 | 有符号 INT16，逐层二进制小数位 `F`；实值约为 `q/2^F`。各层 `F` 见 JSON。每次卷积输出重定标并饱和到 `[-32768,32767]`。 |
| CNN 权重 | 有符号 INT8、每输出通道一个小数位 `F_w`，量化范围 `[-127,127]`，`round_even(w×2^F_w)`。权重按 PyTorch OIHW 形状保存；深度卷积组数见配置。 |
| 偏置/乘加 | 偏置 `round_even(b×2^(F_in+F_w))` 存 INT32；整数乘加按 INT32 数值范围检查。输出重定标至 `F_out`，负值也采用最近、正中取偶舍入。 |
| ReLU、拼接 | ReLU 将负值清零。拼接前把两路特征重定标到下一个卷积的输入小数位，再按通道拼接。 |
| Tanh 与 CNN 输出 | 把末层结果重定标到 Q8 索引，查 `[-8,8]` 上 4097 项的 Tanh Q15 表，索引越界钳到端点。查表内容离线由浮点生成；查表后 `A_low=clip_int16(round_even(Q15_raw/2))`，得到有符号 Q14。 |
| 参数插值 | 低分辨率参数为有符号 Q14；按官方 `UpsamplingBilinear2d` 的 `align_corners=True` 坐标，分别在水平、竖直方向做整数有理权重插值，每一步最近、正中取偶舍入，输出 Q14。 |
| 八轮增强 | 原图 Q14 转 Q15；插值后的参数 Q14 转 Q15，同一参数图每轮复用。每轮 `square=round_even(I²/2^15)`，`delta=round_even(A×(square-I)/2^15)`，`I=clip(I+delta,0,2^15)`，重复八次。公式的符号严格对齐官方 `I+A(I²-I)`。 |
| 输出 | `round_even(I×255/2^15)`，钳到 `[0,255]` 后保存 RGB PNG。 |

以上规则使用**对称二进制定点**，所以没有仿射量化的 `zero_point`。`round_even` 是“四舍六入、五看偶数”；正负数处理对称。配置 JSON 中每个卷积都有 `input_frac`、`output_frac`、各输出通道 `weight_frac`、权重尺寸、padding、组数和 INT32 累加上界。`outputs/zero_dce_pp/quantization/integer/integer_weights.npz` 含实际 INT8 权重与 INT32 偏置。`A_low` 的 DDR 测试数据字节序与平面排列见下一节；CNN HLS top 的 m_axi 指针合同见 `docs/zero_dce_pp_hls_cnn_contract.md`。物理地址与 Vivado 地址映射仍由集成侧确定。

### 3.1 CNN→Bilinear 的 Q14 接口

V1 固定输入图经裁剪后为 `[1,3,720,1272]`，CNN 输出 `A_low` 为 `[1,3,60,106]`。三个通道依次对应原图 R、G、B，NCHW 平面连续排列，先放完 R 的 `60×106` 个标量，再放 G、B。每个标量为二进制补码有符号 INT16 Q14，实值 `raw/16384`；这与 `ap_fixed<16,2>` 的小数位数一致。每通道 12,720 字节，整帧 38,160 字节，字节偏移为 `2×((c×60+y)×106+x)`。

软件导出的 `night_01_a_low_q14_nchw_le.bin` 是无行填充的小端字节流；`night_01_a_low_q14_manifest.json` 包含尺寸、通道、长度和 SHA-256。二者在 `outputs/zero_dce_pp/quantization/integer/`，受 Git 忽略。固定接口定义在 `configs/zero_dce_pp_a_low_interface.json`。V1 传输次序约定为 CNN 生成完整同帧 `A_low` 到 DDR，再由 Bilinear 读取；HLS top 已声明输出 m_axi 端口及 ap_ctrl_hs 完成信号。缓冲区物理基地址、Vivado AXI 路由和板端缓存同步仍需集成。

旧版实验曾生成 `night_01_parameters_integer_q15.npy`；该文件若仍留在本地输出目录，属于过期数据。以 `night_01_parameters_integer_q14.npy` 和本节的 Q14 二进制文件为准。

软件 Q15→Q14 的中点采用最近偶数舍入。队友的 `AP_RND` 是否在所有正负半刻度情况下逐位相同，仍需用该二进制参考和 HLS 仿真核对；不能仅凭类型名认定一致。

### 3.2 CNN 量化参数的确切含义

本方案不是常见的“全层统一一个十进制 scale”的 INT8 仿射量化。对卷积层 `L`，逐层输入/输出均为有符号 INT16、`zero_point=0`：

```text
x_real ≈ x_int16 × input_scale       input_scale  = 2^(-input_frac)
y_real ≈ y_int16 × output_scale      output_scale = 2^(-output_frac)
w_real[c] ≈ w_int8[c] × weight_scale[c]
weight_scale[c] = 2^(-weight_frac_per_output_channel[c])
b_real[c] ≈ b_int32[c] × bias_scale[c]
bias_scale[c] = input_scale × weight_scale[c]
```

权重、偏置都按**输出通道**分别定 scale，但零点统一为 0。`configs/zero_dce_pp_integer_rules.json` 保存全部小数位，`outputs/zero_dce_pp/quantization/integer/night_01_layer_io_manifest.json` 同时写出相应的数值 scale 和 zero point。输入先从上个节点的小数位转换到本层 `input_frac`，再进入乘加。不能把上层输出的 INT16 原码直接送入下一层，除非二者 `frac` 相同。

卷积的整数定义是：零填充，`acc[c]=bias_int32[c]+Σ(input_int16×weight_int8[c])`；深度卷积 `groups=C_in`，逐点卷积 `groups=1`。计算 `F_acc[c]=input_frac+weight_frac[c]`，然后 `output=clip_int16(round_even(acc×2^(output_frac-F_acc[c])))`。若指数为负，就对 `2^(F_acc-output_frac)` 做带符号的最近偶数除法。**导出的正确输出是这个重定标/饱和后的卷积输出，尚未经过后接的 ReLU**。FPGA 核对单层时无需依赖训练代码。

### 3.3 14 层格式表

下表所有形状均为 `NCHW` 且 `N=1`，只列 `C×H×W`。输入和输出都是有符号 INT16，scale 分别为 `2^-F入`、`2^-F出`，零点都为 0。权重是 INT8 OIHW；表中 `F权` 是输出通道小数位的**最小到最大范围**，不是所有通道共用同一个数。逐通道完整列表在 manifest/JSON 中。偏置均为 INT32，其 scale 为对应输入 scale 乘该通道权重 scale。

| 卷积层 | 输入 C×H×W | 输出 C×H×W | F入 | F出 | F权范围 | 权重 O×I×KH×KW | groups |
|---|---:|---:|---:|---:|---:|---:|---:|
| `e_conv1.depth_conv` | 3×60×106 | 3×60×106 | 14 | 14 | 8 | 3×1×3×3 | 3 |
| `e_conv1.point_conv` | 3×60×106 | 32×60×106 | 14 | 14 | 7–16 | 32×3×1×1 | 1 |
| `e_conv2.depth_conv` | 32×60×106 | 32×60×106 | 14 | 13 | 8–16 | 32×1×3×3 | 32 |
| `e_conv2.point_conv` | 32×60×106 | 32×60×106 | 13 | 14 | 8–16 | 32×32×1×1 | 1 |
| `e_conv3.depth_conv` | 32×60×106 | 32×60×106 | 14 | 14 | 7–16 | 32×1×3×3 | 32 |
| `e_conv3.point_conv` | 32×60×106 | 32×60×106 | 14 | 14 | 7–16 | 32×32×1×1 | 1 |
| `e_conv4.depth_conv` | 32×60×106 | 32×60×106 | 14 | 12 | 7–16 | 32×1×3×3 | 32 |
| `e_conv4.point_conv` | 32×60×106 | 32×60×106 | 12 | 12 | 7–16 | 32×32×1×1 | 1 |
| `e_conv5.depth_conv` | 64×60×106 | 64×60×106 | 12 | 13 | 7–16 | 64×1×3×3 | 64 |
| `e_conv5.point_conv` | 64×60×106 | 32×60×106 | 13 | 13 | 7–16 | 32×64×1×1 | 1 |
| `e_conv6.depth_conv` | 64×60×106 | 64×60×106 | 13 | 13 | 7–16 | 64×1×3×3 | 64 |
| `e_conv6.point_conv` | 64×60×106 | 32×60×106 | 13 | 14 | 8–16 | 32×64×1×1 | 1 |
| `e_conv7.depth_conv` | 64×60×106 | 64×60×106 | 14 | 14 | 8–16 | 64×1×3×3 | 64 |
| `e_conv7.point_conv` | 64×60×106 | 3×60×106 | 14 | 16 | 9 | 3×64×1×1 | 1 |

`e_conv5` 的 64 通道来自 `x3|x4`，`e_conv6` 来自 `x2|x5`，`e_conv7` 来自 `x1|x6`；竖线表示沿通道拼接。每组 `point_conv` 后接 ReLU（第 7 组除外），且需按**下一层输入 scale**再次重定标。`e_conv7.point_conv` 后走 Tanh Q15 查表，并在 CNN 输出边界转换成 Q14。

### 3.4 逐层测试输入与正确输出

`night_01_layer_io.npz` 保存上述 **14 层每一层的完整整数输入和完整正确输出，共 28 个数组**；不是仅给一个最终增强图。数组键名固定为 `<层名>.input` 和 `<层名>.output`，例如：

```python
import numpy as np

with np.load("night_01_layer_io.npz", allow_pickle=False) as vectors, \
     np.load("integer_weights.npz", allow_pickle=False) as weights:
    x = vectors["e_conv3.point_conv.input"]   # int16, [1,32,60,106]
    y = vectors["e_conv3.point_conv.output"]  # int16, [1,32,60,106]
    w = weights["e_conv3.point_conv.weight_int8"]  # int8, OIHW
    b = weights["e_conv3.point_conv.bias_int32"]   # int32, O
```

对每层，用 manifest 中的 `input_key`、`output_key`、`weight_key`、`bias_key` 找到数据；`input_frac`、`output_frac`、逐通道 `weight_frac` 与 `groups/padding/stride` 确定计算。正确输出是**逐整数精确匹配**的 golden output，不是“接近 FP32 即可”。manifest 还记录输入/输出形状、数据类型和按 C 连续内存顺序的 SHA-256，方便检查转换为 HLS Testbench 数据时有无乱序。`.npz/.npy` 是 Python 交换容器，不要求硬件解析；若转成 `.bin`，必须另行冻结字节序、内存排列和对齐，本次未冒充已规定。

除单层向量外，`night_01_integer_test_vectors.npz` 包含缩小图、各层输出、Q14 低分辨率参数图及插值/八轮增强的左上角 `16×16` 片段；`night_01_parameters_integer_q14.npy` 是完整 Q14 参数图，`night_01_enhanced_integer_q15.npy` 是最终整数增强图。单层 Testbench 应先核对 `layer_io`，再串整网和增强部分。

## 4. 结果与误差定位

| 输入 | 参数图 MAE | 最终 FP32 值域 MAE | PNG 平均差/灰度级 | PNG 最大差/灰度级 | INT16 裁剪次数 |
|---|---:|---:|---:|---:|---:|
| 原图 | 0.001720 | 0.002180 | 0.556 | 3 | 0 |
| 暗化 0.35 倍 | 0.001769 | 0.002139 | 0.544 | 3 | 0 |
| 极暗加噪 | 0.001877 | 0.001900 | 0.477 | 3 | 0 |
| 增亮 1.5 倍 | 0.001732 | 0.002034 | 0.517 | 3 | 0 |
| 低对比度 | 0.001649 | 0.002687 | 0.682 | 3 | 0 |
| 全黑 | 0.001530 | 0 | 0 | 0 | 0 |
| 全白 | 0.001627 | 0 | 0 | 0 | 0 |

原图的预处理/缩小误差 MAE 为 `0.0000164`；14 个卷积输出的逐层 MAE 已保存在 `results.json`。原图上最大的一层平均误差是 `e_conv4.point_conv` 的 `0.00411`。Q14 低分辨率参数图最大绝对误差 `0.00587`，最终增强图最大绝对误差 `0.00982`。八轮结果的 MAE 从第 1 轮 `0.00021` 增至第 8 轮 `0.00218`，说明误差在曲线重复迭代中累积，但这次未出现明显失控。

导出的权重原始数据为 **10,075 字节 INT8**，偏置 **1,944 字节 INT32**；Tanh 表为 4097 个 INT16 项（约 8 KiB）。这**不是总硬件存储预算**，还没有计入大图、特征图、拼接缓存、插值缓存和接口缓冲。按 INT16 全范围（绝对值最大 32768）保守计算的最大单通道 INT32 累加上界为 **383,670,400**，低于 `2,147,483,647`；原图实测最大绝对累加值为 **367,480,032**。

## 5. 交付文件与复现

- `deployment/zero_dce_integer_ptq.py`：完整整数前向、校准、权重导出及数值比较脚本。
- `evaluation/test_zero_dce_integer_ptq.py`：舍入、缩小、插值、Tanh、曲线不动点及导出向量复算测试。
- `configs/zero_dce_pp_integer_rules.json`：当前候选整数规则，可版本管理。
- `configs/zero_dce_pp_a_low_interface.json`：V1 CNN→Bilinear Q14 形状、通道和 DDR 测试数据格式。
- `outputs/zero_dce_pp/quantization/integer/`：本地生成结果，受 `.gitignore` 保护，不作为提交内容。其中 `integer_weights.npz` 和 `tanh_q15_lut.npy` 是计算数据；`night_01_layer_io.npz`、`night_01_layer_io_manifest.json` 是 14 层的完整整数输入/输出及格式清单；`night_01_integer_test_vectors.npz` 是其他关键节点向量；`night_01_parameters_integer_q14.npy`、`night_01_a_low_q14_nchw_le.bin` 和对应 manifest 是 Bilinear 输入参考；`night_01_enhanced_integer_q15.npy` 是最终整数增强图；PNG 是视觉对比；`results.json` 是详细误差记录。

从本仓库根目录、使用具备依赖的 Python 环境执行：

```powershell
python .\deployment\zero_dce_integer_ptq.py
python -m pytest -q .\evaluation\test_zero_dce_integer_ptq.py
```

改为 Q14 接口后实际运行了完整脚本及 7 个测试（含 Q15→Q14 正负中点、DDR 二进制重载、14 层逐层输入对正确输出复算），**7/7 通过**。其后新增的 CNN HLS 源码经本机 g++ 数值检查：19,080 个 Q14 输出标量与同图软件 golden 逐个一致，最大原码误差 0。该检查使用本机 `ap_int` 类型替身。2026-09-25 又使用 Vitis 2025.2 完成 C 仿真，同样 19,080 项零误差；HLS 综合完成，但 40.443 ns 估计时钟未达到 10 ns 目标。Vivado 时序、RTL 协同仿真与上板测量尚未完成，也没有得到速度、功耗或 FPGA 资源收益的板端结论。

## 6. 下一步验收门槛

1. 收集真实且独立的夜景、局部强光、噪声、正常曝光等图片；分开校准集和测试集。当前合成变体只能做算术压力检查，不能支撑画质结论。
2. 设定允许的参数图/最终图误差和主观画质标准，复测色偏、噪声放大及亮部损伤；根据新数据调整各层小数位或混合精度。
3. 与 FPGA 队友确认已写入 `configs/zero_dce_pp_hls_interface.json` 的张量布局、权重字节序、定点舍入、帧缓存和接口；C 仿真已逐项核对 `A_low` golden，下一步需优化综合时钟与 II，再做 RTL 协同仿真、Vivado 和板端验证。

因此，本次“完全量化”指**全计算链已有明确且实际运行的整数软件规则**；项目书要求的多场景量化验收和 FPGA 闭环仍未完成。
