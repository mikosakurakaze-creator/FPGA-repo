# Bilinear 坐标映射软件 oracle 报告

## 1. 目标与范围

接续 `fpga/reports/bilinear_software_spec.md`，用 reference 对应版本的实际 PyTorch 实现确认 `torch.nn.UpsamplingBilinear2d(scale_factor=12)` 的 `align_corners`、输出尺寸和像素坐标规则；用完整的小张量结果验证手写双线性公式，再用现有 `parameters_lowres.npy` 与 `parameters_fullres.npy` 进行抽样和整图核对。本次只建立软件数值 oracle；没有编写 Bilinear HLS、定点化、C Simulation、C Synthesis、RTL Co-simulation、Vivado Implementation、板上测试、commit 或 push。

## 2. 环境、代码位置与数据

- Git 分支：`codex/curve-fp32-baseline`；任务开始时 HEAD：`6bdceba`。
- reference 的 `outputs/zero_dce_pp/reference/metadata.json` 记录 CPU、`torch.float32`、PyTorch `2.14.0+cpu`、`scale_factor=12`。原始解释器当前未找到；系统默认 Python 与 Codex 随附 Python 均无 `torch`。为重现同版本行为，在仓库外 `E:\HLS\bilinear_oracle_venv` 建立隔离 Python 环境，安装 PyTorch `2.14.0` wheel；实际运行 `torch.__version__` 为 **`2.14.0+cpu`**。本次环境的 NumPy 为 `2.5.3`，未声称它与原始导出环境其他包完全相同。
- 项目调用：`model/zero_dce_pp/upstream/model.py:39-40` 构造 `nn.UpsamplingBilinear2d(scale_factor=self.scale_factor)`；`model/zero_dce_pp/enhancement.py:69-79` 通过 `network.upsample(parameters)` 执行并检查输出 H/W。
- 所安装 PyTorch 源码：`E:\HLS\bilinear_oracle_venv\Lib\site-packages\torch\nn\modules\upsampling.py:293` 的 `UpsamplingBilinear2d.__init__` 实际调用 `super().__init__(size, scale_factor, mode="bilinear", align_corners=True)`；`Upsample.forward` 从约 `:170` 开始，实际把 `self.size`、`self.scale_factor`、`self.mode`、`self.align_corners`、`self.recompute_scale_factor` 传给 `torch.nn.functional.interpolate`。
- 所安装 PyTorch C++ 头文件 `E:\HLS\bilinear_oracle_venv\Lib\site-packages\torch\include\ATen\native\UpSample.h:273-315` 给出 align-corners scale 与源索引；`:453-478` 给出邻居索引和插值权重。以下公式同时经过实测小张量输出检验。
- 参考数组：`parameters_lowres.npy` 为 NCHW FP32 `[1,3,60,106]`，`parameters_fullres.npy` 为 NCHW FP32 `[1,3,720,1272]`。本次直接读取已有 `.npy`，未重新运行网络模型。

## 3. 实际模块属性与调用语义

在 PyTorch `2.14.0+cpu` 中实际构造 `torch.nn.UpsamplingBilinear2d(scale_factor=12)` 并读取属性，得到：

| 项目 | 实测值 |
|---|---|
| `size` | `None` |
| `scale_factor` | `12.0` |
| `mode` | `'bilinear'` |
| `align_corners` | **`True`** |
| `recompute_scale_factor` | `None` |
| `antialias` | 模块未传入；实际 `F.interpolate` 签名默认 `False` |

本例输出尺寸为 `H_out = floor(H_in × scale_factor)`、`W_out = floor(W_in × scale_factor)`：小张量 `2×3` 经倍率 2 得 `4×6`；reference `60×106` 经倍率 12 得 `720×1272`。`scale_factor` 先确定输出尺寸；在 **`align_corners=True`** 路径，插值坐标比例不是简单的 `1/scale_factor`，而是输入和输出**端点**之间的比例。

## 4. 坐标、邻居、权重与边界公式

对某个输出位置 `(oy, ox)`，令输入高宽 `(Hi, Wi)`、输出高宽 `(Ho, Wo)`，零起始索引。已安装 PyTorch 的 align-corners 路径以及手写 oracle 使用：

```text
sy = 0                         若 Ho == 1；否则 oy × (Hi − 1) / (Ho − 1)
sx = 0                         若 Wo == 1；否则 ox × (Wi − 1) / (Wo − 1)
y0 = floor(sy)                 x0 = floor(sx)
y1 = min(y0 + 1, Hi − 1)       x1 = min(x0 + 1, Wi − 1)
wy = sy − y0                   wx = sx − x0
v = (1−wy)[(1−wx)I[y0,x0] + wx I[y0,x1]]
    + wy [(1−wx)I[y1,x0] + wx I[y1,x1]]
```

实现对索引和权重作边界保护；在本次正常上采样的 align-corners 路径，源坐标本身位于 `[0,Hi−1]×[0,Wi−1]`。右/下末端令 `x1=x0` 或 `y1=y0`，故没有越界读取，也没有外部零填充。四个输出角坐标分别对应四个输入角坐标，因此角点应精确保留。`Hi=1` 或 `Wi=1` 时对应方向比例为 0。

例如小张量 `2×3` 放大到 `4×6` 时，`sy = oy/3`、`sx = 2ox/5`。输出 `ox=2` 映射 `sx=0.8`，**不是** `2/2=1`。reference 的 `60×106 → 720×1272` 则为 `sy=oy×59/719`、`sx=ox×105/1271`；倍率 12 决定 720 与 1272，再由端点比值决定实际源坐标。

## 5. 完整小张量 oracle

构造 NCHW FP32 `1×1×2×3`，输入每点有不同值，用同类 PyTorch 模块 `nn.UpsamplingBilinear2d(scale_factor=2)` 得到 `1×1×4×6`：

**完整输入**：

```text
[[  0.0,  10.0,  40.0],
 [100.0, 130.0, 200.0]]
```

**完整 PyTorch FP32 输出**（保留 Python float 转换后的实际值）：

```text
[[  0.0,                 4.0,                 8.0,                16.000001907348633,  28.0,               40.0],
 [ 33.333335876464844, 40.0,                46.66666793823242,   58.666664123535156,  76.0,               93.33333587646484],
 [ 66.66667175292969,  76.0,                85.33333587646484,  101.33333587646484,  124.0,              146.6666717529297],
 [100.0,                112.0,               124.0,               144.0,               172.0,              200.0]]
```

| 输出 `(oy,ox)` | 源坐标 `(sy,sx)` | 邻居 `(y0,x0)..(y1,x1)` | 权重 `(wy,wx)` | 手算 double | PyTorch FP32 |
|---|---|---|---|---:|---:|
| `(0,0)` | `(0,0)` | `(0,0)..(1,1)` | `(0,0)` | 0 | 0 |
| `(0,1)` | `(0,0.4)` | `(0,0)..(1,1)` | `(0,0.4)` | 4 | 4 |
| `(1,2)` | `(1/3,0.8)` | `(0,0)..(1,1)` | `(1/3,0.8)` | 46.666666666666664 | 46.66666793823242 |
| `(2,3)` | `(2/3,1.2)` | `(0,1)..(1,2)` | `(2/3,0.2)` | 101.33333333333333 | 101.33333587646484 |
| `(3,5)` | `(1,2)` | `(1,2)..(1,2)` | `(0,0)` | 200 | 200 |

对全部 24 个小张量输出，手写 double 公式与 PyTorch FP32 的 **max absolute error = `5.0862630303072365e-06`**；差异反映运算精度与舍入，并未要求 bitwise equality。为了区分另一种坐标规则，同一输入用 `F.interpolate(..., align_corners=False)` 计算时，相对该模块的 max absolute difference 为 **21.0**。

四个角点实测为 `(0,0)=0.0`、`(0,5)=40.0`、`(3,0)=100.0`、`(3,5)=200.0`，均与对应输入角点**精确相等**。

## 6. 真实参数图核对

使用相同版本的 `nn.UpsamplingBilinear2d(scale_factor=12)` 对整个 `parameters_lowres.npy` 重新放大，再与已有 `parameters_fullres.npy` 比较；并用手写 double 公式复算 **72 个**输出坐标（8 个边角样本 + 固定随机种子 `20260924` 的 64 个位置）：

| 核对 | 数量 | max absolute error | mean absolute error |
|---|---:|---:|---:|
| 本次 PyTorch 整图 vs 已保存 reference | 2,747,520 | `8.940696716308594e-08` | `8.240851623325284e-09` |
| 手写 double 抽样 vs 已保存 reference | 72 | `8.380113400430211e-08` | `1.2711042842126577e-08` |

本次 PyTorch 输出与 reference 有 **1,613,492 / 2,747,520** 个元素 bitwise 相等，其余点存在上表量级的微小差异；没有把它写成完全相等，也没有在未查明具体运算路径差异前归因。抽样的四角值与各通道低分辨率对应角点相等。完整 72 个坐标、源坐标、四邻居、权重、手算值和 reference 值保存在 `outputs/zero_dce_pp/bilinear_coordinate_oracle.json`（Git 忽略的运行产物）。

## 7. 实际命令、验证范围与结论

实际在仓库根目录执行的关键命令：

```powershell
python -m venv E:\HLS\bilinear_oracle_venv
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' -m pip install torch==2.14.0 numpy
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' -c "import torch,inspect; m=torch.nn.UpsamplingBilinear2d(scale_factor=12); print(torch.__version__,m.__dict__); print(inspect.getsource(torch.nn.UpsamplingBilinear2d))"
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' evaluation\bilinear_coordinate_oracle.py outputs\zero_dce_pp\reference --output outputs\zero_dce_pp\bilinear_coordinate_oracle.json
```

另外直接查看了上述已安装 PyTorch 的 `Upsample.forward`、`F.interpolate` 函数签名及 `UpSample.h` 对应行。Python oracle 退出码 0，版本核对、shape/dtype 核对均通过，未见运行异常或 NaN/Inf 报告；数值差异如上。未设 FPGA/HLS 数值验收阈值；本次无 DSP/LUT/FF/BRAM/URAM、时钟或 II 结果。

**结论：** 对当前 PyTorch `2.14.0+cpu`，项目使用的 `UpsamplingBilinear2d(scale_factor=12)` 实际是 `mode='bilinear'`、`align_corners=True`、`size=None`，输出先按倍率确定尺寸，再按首末像素端点映射源坐标；邻居和权重遵循上式，边界使用最后有效输入点，四角精确保留。小张量完整输出与真实参数图均支持此公式。该结论是软件 oracle，可供后续设计审核；本次没有确定 HLS 实现或最终硬件数据格式。

本次只新增 `evaluation/bilinear_coordinate_oracle.py` 和本报告；原有软件、HLS 源码及接口均未修改。此前工作区中尚有 Fixed14/Fixed12 sweep 的未跟踪文件，本次保留原状。建议供未来审核的 Commit Message：`test(fpga): document bilinear coordinate oracle`，仅为建议，本次未执行 `git add`、commit 或 push。
