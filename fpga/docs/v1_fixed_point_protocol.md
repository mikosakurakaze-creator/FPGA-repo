# V1 三模块源码级定点数值协议

**冻结对象**：WZH `zero_dce_cnn_top` → DDR `A_low` → `bilinear_fixed16_buffered` → DDR `A_full` → `curve_image_fixed16` → DDR `enhanced`。本文冻结的是**当前源码规定的数值和缓冲合同**，供刘子铭实现软件 Fixed-point Golden；不宣称 CNN 已进入现有 KV260 Block Design，也不冻结尚未实现的 PS 地址和最终画质门限。逐层完整 486 个 weight fractional-bit 值及可解析字段见同目录 [`v1_fixed_point_protocol.json`](v1_fixed_point_protocol.json)。

## 1. 基线、证据与软件 FP32 口径

- Master 分支 `codex/curve-fp32-baseline`，核对时 HEAD `7b86ca168352c8f2d1bf605184f720c3e2c32527`。后级原始源码：`fpga/hls/bilinear_fixed16_buffered/{bilinear_fixed16_buffered.hpp,bilinear_fixed16_buffered.cpp}`、`fpga/hls/curve_image_fixed16/{curve_image_fixed16.hpp,curve_image_fixed16.cpp}`；未修改。
- WZH 的 `origin/feat/zero-dce-quantization` 使用已审计 commit `01580f026a9d14145cad91e8957143c120928a0d`，直接核对 `fpga/hls/zero_dce_cnn_top.{h,cpp}`、`configs/zero_dce_pp_integer_rules.json`、`deployment/zero_dce_integer_ptq.py`、`configs/zero_dce_pp_hls_interface.json`。该提交不在 Master 当前分支；本次通过隔离 worktree `E:/HLS/wzh_cnn_latest_01580f0` 读取，没有 merge。
- HLS `ap_fixed` 行为由本机 AMD Vitis 2025.2 `include/etc/ap_fixed_base.h` 的 `RType`、division 和 `quantization_adjust` 核对，并用该版本 **实际 C Simulation** 测了中点、运算结果类型及两个现有模块的小向量。固定格式和源码所含 pragma 都是当前实现事实；未做新的综合、RTL Co-sim、Vivado 或板端实验。

软件 FP32 reference 的真实代码顺序：`model/zero_dce_pp/preprocessing.py:33-49` 显式转 RGB，`np.asarray(...)/255.0` 后转 `torch.float32`，从原测试图 720×1280 按 12 的倍数裁到 720×1272，HWC→NCHW `[1,3,720,1272]`。`model/zero_dce_pp/enhancement.py:28-32` 用 `torch.nn.functional.interpolate(..., scale_factor=1/12, mode="bilinear")` 下采样 CNN 输入；**`align_corners` 未显式传参，当前 PyTorch 有效行为为 `False`**。网络预测 `A_low` 后，`upstream/model.py:40` 声明的 `nn.UpsamplingBilinear2d(scale_factor=12)` 在当前 PyTorch 环境的有效行为是 **`align_corners=True`**；`enhancement.py:63-80` 直接调用该模块放大至 `[1,3,720,1272]`。FP32 Curve 在 `enhancement.py:82-100` 每个通道/元素独立执行 `x←x+A(x²−x)` 八轮，A 不更新，计算中**无 clamp**。仅 PNG 预览在 `model/zero_dce_pp/io_utils.py:59-63` 将结果归一到显示区间、`np.clip(...,0,1)`、`np.rint(*255)`、转 `uint8`；`.npy` 数值 reference 不经此显示量化。`outputs/zero_dce_pp/reference/metadata.json` 记录 FP32/NCHW 的各 reference shape。上述口径与任务提出的总体口径一致；注意 downsample 的 `align_corners=False` 是**省略参数后的实际行为**，源码没有写 `align_corners=False`。

## 2. 数字格式、layout 与边界

HLS 后级共同外部格式 `ap_fixed<16,2,AP_RND,AP_SAT>`：signed 二补码，W=16、I=2 **含符号位**、F=14、zero point=0、真实值 `signed_raw/16384`、LSB `2^-14 = 0.00006103515625`、可表示 `[-2, 1.99993896484375]`。WZH 的 `ap_int<16>` Q14 `A_low` **有相同的 16-bit 原始位解释**；`ap_int` 本身没有 AP_RND 属性，Q14 数值由 WZH 的整数算法产生。所有 V1 DDR 图像缓冲按 RGB 三个平面依序、NCHW/C 连续、无行填充；元素线性下标 `((c*H+y)*W+x)`、字节偏移 `2*((c*H+y)*W+x)`，每元素 2 B、小端 signed raw。三通道不 interleave。

| DDR buffer | `[N,C,H,W]` | scalar / bytes | writer → reader | 有效期/解释 |
|---|---|---:|---|---|
| `A_low` | `[1,3,60,106]` | 19,080 / 38,160 | CNN `a_low_q14` m_axi → Bilinear `parameters_lowres` m_axi | CNN `ap_done` 后有效，Bilinear 完成前不复用；raw Q14 **按位直读，不再 requantize**。当前 Master BD 尚无 CNN IP。 |
| `A_full` | `[1,3,720,1272]` | 2,747,520 / 5,495,040 | Bilinear `parameters_fullres` m_axi → Curve `parameter` m_axi | Bilinear 完成后、Curve 完成前保持；同一 Fixed16 raw 位，无 float 往返。 |
| `model_input` | `[1,3,720,1272]` | 2,747,520 / 5,495,040 | 目前 TB 从 FP32 `model_input.f32` 用 `curve_fixed16_t(float)` 显式量化；后续 PS/前级负责同规则写 DDR → Curve `input` | Curve 开始前可读，完成前保持。**FP32 字节不能直接作 Fixed16 读**。PS 生产/缓存管理尚未实现。 |
| `enhanced` | `[1,3,720,1272]` | 2,747,520 / 5,495,040 | Curve `output` m_axi → PS/host | Curve `ap_done` 后有效，下一帧覆盖前保持；Fixed16 raw，不是 PNG uint8。 |

当前后级 HLS 顶层接口为 Bilinear 两路独立 `gmem_input/gmem_output` m_axi + H/W/基址/控制 AXI-Lite（宽度约束 `1≤Wi≤128`）；Curve 三路独立 `gmem_input/gmem_parameter/gmem_output` m_axi + `count`/基址/控制 AXI-Lite，V1 `count=2,747,520`。CNN 七个数组指针共享一个物理 `m_axi_gmem`，各基址通过 AXI-Lite 配置，输出是 **m_axi DDR 写入**，没有 AXI Stream；这只是 WZH 独立 HLS IP 的接口定义，不代表已接入 Master BD。所有 PS cache flush/invalidate、物理地址、三模块启动顺序仍属待实施集成工作。

## 3. CNN 输入、权重与逐层运算

`zero_dce_cnn_top.h:4-53` 将 `zero_dce_q16_t=ap_int<16>`、`zero_dce_q8_t=ap_int<8>`、`zero_dce_q32_t=ap_int<32>`；C++ `long long` 用于有符号重缩放。CNN `input_q14` **只接收已经裁剪、缩小并量化**的 `[1,3,60,106]`，不是 720×1280/720×1272 图。其 19,080 个 signed int16 Q14 数值是 `raw/16384`，原始 DDR 字节仍是小端二补码。crop、下采样和转 Q14 **均不在 CNN HLS top 内**。WZH 软件 `deployment/zero_dce_integer_ptq.py:192-209` 先将裁后 uint8 原图每像素按 `round_nearest_even(uint8*16384/255)` 变 Q14，再利用 `align_corners=False` 的 1/12 坐标取每个低分辨率点四个中心邻居 `(12y+5/6, 12x+5/6)`，求和后用 nearest-even 除以 4，最后饱和到 int16。软件 FP32 下采样与这条**整数输入 producer 规则**应分别保留，不能混写。

每层卷积在 `zero_dce_cnn_top.cpp:127-184`：先将当前特征从旧 F 缩放到本层 `input_frac` 并 saturate INT16；权重 signed INT8（存储范围 `[-128,127]`，导出量化器在 `zero_dce_integer_ptq.py:126-136` 先对 float64×`2^F_weight[c]` 用 `torch.round` 最近偶数，再把权重实际裁到 `[-127,127]`），**每个输出通道**各有 `weight_frac`；偏置 signed INT32，由 Python `round(bias_float*2^(F_in+F_weight[c]))` 最近偶数生成，原码小数位 `F_in+F_weight[c]`。`weight_frac` 与打包权重/偏置是当前已导出模型的**冻结输入数据**，golden 不应在运行时重新校准。源码把两乘数先显式转成 signed `ap_int<32>`，AMD `ap_int` 的乘法运算返回 **signed 64-bit 临时积**，再由 `accumulator +=` 累入 signed **`ap_int<32>` accumulator**（同一小数位/scale、零点 0）。accumulator 的原码合法范围 `[-2^31,2^31-1]`，权重零点 0、输入/输出激活零点 0；其 INT32 上界由导出规则约束，越界不是饱和而会丢失高位。源码以 `shift=F_in+F_weight[c]−F_out` 将 accumulator 转 `long long`，调用 `round_shift_even(...,shift)`，随后 `clamp_q16` 至 `[-32768,32767]`；卷积中**每个输出通道的 scale 可能不同**，不可用一个全层 weight Q 位替代。导出器也检查本层 INT32 最坏累计界；JSON 中保留该界、全 486 个通道的 `weight_frac`/bias frac/shift。

| index | layer | F_in | 每通道 F_weight 范围¹ | accumulator W | F_out | 每通道 shift 范围¹ | 输出存储 |
|---:|---|---:|---:|---:|---:|---:|---|
| 0 | `e_conv1.depth_conv` | 14 | 8 | 32 | 14 | 8 | signed INT16 Q14 |
| 1 | `e_conv1.point_conv` | 14 | 7–16 | 32 | 14 | 7–16 | signed INT16 Q14 |
| 2 | `e_conv2.depth_conv` | 14 | 8–16 | 32 | 13 | 9–17 | signed INT16 Q13 |
| 3 | `e_conv2.point_conv` | 13 | 8–16 | 32 | 14 | 7–15 | signed INT16 Q14 |
| 4 | `e_conv3.depth_conv` | 14 | 7–16 | 32 | 14 | 7–16 | signed INT16 Q14 |
| 5 | `e_conv3.point_conv` | 14 | 7–16 | 32 | 14 | 7–16 | signed INT16 Q14 |
| 6 | `e_conv4.depth_conv` | 14 | 7–16 | 32 | 12 | 9–18 | signed INT16 Q12 |
| 7 | `e_conv4.point_conv` | 12 | 7–16 | 32 | 12 | 7–16 | signed INT16 Q12 |
| 8 | `e_conv5.depth_conv` | 12 | 7–16 | 32 | 13 | 6–15 | signed INT16 Q13 |
| 9 | `e_conv5.point_conv` | 13 | 7–16 | 32 | 13 | 7–16 | signed INT16 Q13 |
| 10 | `e_conv6.depth_conv` | 13 | 7–16 | 32 | 13 | 7–16 | signed INT16 Q13 |
| 11 | `e_conv6.point_conv` | 13 | 8–16 | 32 | 14 | 7–15 | signed INT16 Q14 |
| 12 | `e_conv7.depth_conv` | 14 | 8–16 | 32 | 14 | 8–16 | signed INT16 Q14 |
| 13 | `e_conv7.point_conv` | 14 | 9 | 32 | 16 | 7 | signed INT16 Q16 |

¹ 范围只是阅读摘要，**精确值按输出通道索引取 JSON `cnn_layers[i].weight.fractional_bits_per_output_channel[c]`**；`shift` 同样取该 `c` 的数组。逐层 F_in/F_out、shape/groups/offset 与 WZH `kZeroDceLayers[14]` 和其整数规则 JSON 逐项核对；全 486 个 F_weight 原码又与 WZH 实际打包的 `weight_frac.bin` **486/486 一致**（SHA-256 `54a14af94229aee7c9ac574b6f024b11a340ac07146657b4209366d070cf045d`）。激活统一 signed INT16 原码范围 `[-32768,32767]`，不同 F 对应真实范围 `[-32768/2^F,32767/2^F]`：Q12 为 `[-8,7.999755859375]`、Q13 为 `[-4,3.9998779296875]`、Q14 为 `[-2,1.99993896484375]`、Q16 为 `[-0.5,0.4999847412109375]`；LSB 均为 `2^-F`。权重真实值 `raw/2^F_weight[c]`；偏置与 accumulator 真实值 `raw/2^(F_in+F_weight[c])`。

块 1–6 的 pointwise 后按 `max(raw,0)` ReLU，再以 INT16 原码存 skip。块 5/6/7 的拼接顺序分别为 `[block3,block4]`、`[block2,block5]`、`[block1,block6]`；两侧若 F 不同，先按目标 depthwise 输入 F 用 nearest-even 缩放并 `clamp_q16`，再按前 32 通道/后 32 通道拼接。复制缓存本身不量化。`workspace_int16` 是 DDR 2,035,200 个 INT16（4,070,400 B），两块 64 通道工作区加六块 32 通道 skip；**其 F 随层变化，不可全部解释为 Q14**，本次调用 `ap_done` 前不得复用。

最终层的激活为 INT16 Q16。`zero_dce_cnn_top.cpp:203-222` 用 signed nearest-even `round_shift_even(features_raw,8)` 得 Q8 索引，先 clamp 索引至 `[-2048,2048]`，再加 2048 查询 4097 个 signed INT16 Q15 LUT；LUT 生成式见软件 `build_tanh_lut()`：`sat16(round_nearest_even(tanh(q8/256)*32768))`。LUT 输出再 `round_shift_even(tanh_q15_raw,1)` 得 Q14，`clamp_q16` 后写 `a_low_q14`。Tanh 索引 clamp 与最终 INT16 saturation 是**两个不同步骤**。A_low 零点 0、scale `2^-14`，是 CNN→Bilinear 唯一交接值。

## 4. CNN 最近偶数与 AMD `AP_RND`：不能互换

WZH `zero_dce_cnn_top.cpp:39-55` 的 `round_shift_even(v,s)`：`s>0` 时对绝对值取商/余，余数大于半步加一；恰好半步时仅商为奇数才加一；再恢复原符号。因此正负中点**均趋向偶数**。`s≤0` 时直接 `v*2^(-s)`，不产生舍入；调用处 `clamp_q16` 才作 signed INT16 saturation。合法输入与 shift 仍须满足源码的 `long long` 范围，Python 无界整数不能视作溢出证明。

AMD Vitis 2025.2 `include/etc/ap_fixed_base.h:366-381` 对 `AP_RND` 保留第一被丢弃位 `qb=1` 时加一；对二补码负数先算术右移的下界，再加一，所以**恰好半步朝正无穷方向**。`AP_RND_CONV` 才会在中点检查保留 LSB 以实现偶数规则。本次最小 Vitis CSim 已直接验证。下表以目标格式的一个 LSB 为单位，目标存储为整数原码：

| 输入实值/目标 LSB | WZH `nearest_even` | AMD `AP_RND` |
|---:|---:|---:|
| +0.5 | 0 | +1 |
| +1.5 | +2 | +2 |
| −0.5 | 0 | 0 |
| −1.5 | −2 | −1 |

`AP_SAT` 在**目标类型 cast** 的 rounding 后把原码夹到目标 signed/unsigned 可表示区间；没有额外 `[0,1]` clamp。对 Fixed16，+2.25→原码 +32767，−2.25→−32768。完全相同 F 且目标范围足够大的位宽扩展不改变数值。Python helper `nearest_even_shift`、`ap_rnd_shift`、`saturate_signed` 分别实现这些规则。

## 5. Bilinear Fixed16 的每一步 cast

源码 `bilinear_fixed16_buffered.cpp:6-12,32-110` 固定 batch=1、RGB/NCHW、channels=3、放大 12 倍、`align_corners=True` 的坐标式；两行片上缓存只改 DDR 访问，不改下表的四邻居计算顺序。有效 V1 `Hi=60,Wi=106,Ho=720,Wo=1272`；当前 top 允许 `Wi≤128` 且拒绝零尺寸。坐标使用**源角点对齐**：`sy=oy*(Hi−1)/(Ho−1)`、`sx=ox*(Wi−1)/(Wo−1)`，`y0/x0=floor`、`y1/x1=min(lower+1,last)`、`wy/wx=coord−lower`，最后一行/列强制精确端点；不能换成 `oy/12` 或 `ox/12`。

| stage | HLS 结果/存储类型 W,I,F | 精确操作及 cast 效果 |
|---|---|---|
| DDR 输入/row cache/四邻居 | signed `<16,2,14>` | 直接按 Q14 raw 读取 `A_low`；**无舍入、无再次 saturation**。 |
| 尺寸的 `coord_t` | unsigned `<48,16,32>` | 整数尺寸转 Q32 精确。`coord_t / coord_t` 运算结果为 unsigned `<80,48,32>`；正整数除法余数**截弃向下**。转 `ratio_t` unsigned `<33,1,32>` 时 F 相同，无 `AP_RND`；该 V1 比率 `<1`，不触发 `AP_SAT`。所以 `ratio_raw=floor((Hi−1)*2^32/(Ho−1))`，x 同理。 |
| 输出索引×ratio / `coord_t` | unsigned 运算 `<65,33,32>` → `<48,16,32>` | 乘法和转储 F 相同，当前尺寸无舍入或饱和；最后一行/列直接设最后源整数坐标，其余超出上界才 clamp。 |
| 邻居与 `weight_t` | `coord−integer` 运算 signed `<49,17,32>` → unsigned `<33,1,32>`；`weight_t(1)−weight` 运算 signed `<34,2,32>` → unsigned `<33,1,32>` | 坐标非负、差在 `[0,1)`，F 同为 32，值精确；范围内无舍入/饱和。 |
| 四个水平乘项 | unsigned Q32 weight × signed Q14 sample → signed `hproduct_t<49,3,46>` | 运算本身就是 `<49,3,46>`，显式构造同类型；乘法**全精度，无舍入**，范围内不饱和。 |
| `top`/`bottom` 水平和 | signed `<49,3,46>+<49,3,46>` → `hsum_t<50,4,46>` | 运算本身是 `<50,4,46>`，**精确加法**。先分别算上排和下排，不能提前各自回压 Q14。 |
| `upper`/`lower` 垂直乘项 | unsigned Q32 weight × signed Q46 sum 运算 `<83,5,78>` → `vproduct_t<65,5,60>` | **此处丢 18 个小数位，以 `AP_RND` 舍入**；目标有 `AP_SAT`，V1 法定输入范围内该中间范围足够。两项各自分别舍入，然后相加。 |
| 垂直和 `result` | signed `<65,5,60>+<65,5,60>` → `vsum_t<66,6,60>` | 运算本身是 `<66,6,60>`，精确加法，无额外舍入。 |
| DDR `A_full` | signed `<66,6,60>` → `ap_fixed<16,2,AP_RND,AP_SAT>` | **最后丢 46 个小数位，按 `AP_RND` 舍入并按 Fixed16 范围 saturation**；只在这里写 Q14 输出。 |

上表运算返回类型由 AMD Vitis 2025.2 `ap_fixed_base.h` 的 `RType` 及实际 CSim 的 `decltype::width/iwidth` 核实，不把类型声明中的 `AP_RND` 错认为每次乘法都会舍入。两排计算顺序恰为 `(1-wx)*v00 + wx*v01` 与 `(1-wx)*v10 + wx*v11`，然后 `(1-wy)*top + wy*bottom`；这也决定最终少量 1 LSB 行为。Python 骨架在 Q14 整数域保留这一顺序和垂直项独立舍入。

## 6. Curve Fixed16 的每轮精度

源码 `curve_image_fixed16.hpp:6` 与 `.cpp:5-30`：外部 `x`、`A`、最终 `output` 全是 signed `ap_fixed<16,2,AP_RND,AP_SAT>` Q14；逐元素读取一次 A，**八轮都用同一个 A**。对每个元素：

| stage | HLS 操作结果及显式存储 W,I,F | 舍入/饱和点 |
|---|---|---|
| `x`、`A` | `<16,2,14>` | DDR raw 原样解释，无输入端再量化。若从 FP32 reference 构造输入，TB 是 `curve_fixed16_t(float)`，此**生产环节**用 `AP_RND/AP_SAT`。 |
| `square=x*x` | `<32,4,28>` | 同型保存；精确乘法，不提前截回 16 bit。 |
| `delta=square−x` | `<33,5,28>` | x 精确扩展到 F28，减法精确，无舍入。 |
| `term=A*delta` | `<49,7,42>` | 精确乘法，A 精确扩展；无舍入。 |
| `updated=x+term` | `<50,8,42>` | x 精确扩展到 F42，加法精确。 |
| `x=curve_fixed16_t(updated)` | `<50,8,42>` → `<16,2,14>` | **每轮末丢 28 个小数位，`AP_RND`；随后 `AP_SAT` 到 `[-2,2−2^-14]`**。此 x 进入下一轮；总共量化八次。 |
| `output[index]=x` | `<16,2,14>` → 同型 DDR | 无额外舍入。 |

四个中间别名虽然声明 `AP_RND,AP_SAT`，但运算返回宽度恰好与别名一致，当前逐操作 cast 不丢小数位；**真正可能改变数值的量化点是每轮最后的 Fixed16 cast**。不作 `[0,1]` clamp，超范围时只有类型的 `AP_SAT`。RGB 三通道只按相同线性下标一一配对，无跨通道混合。

## 7. 不能把 WZH 软件整数整链直接当作本协议后级 golden

WZH `deployment/zero_dce_integer_ptq.py:223-254` 中的软件整数 `upsample_align_corners` 是**水平先 nearest-even 回整数、垂直再 nearest-even 回整数**；其 `enhance_integer` 是 **Q15** 状态，每轮平方/项另行 nearest-even，并把 `current` clamp 到 `[0,Q15]`。这适合 WZH 自己的整数原型，却与当前 Master 的 Bilinear `Q32→Q46→Q78/AP_RND→Q60/AP_RND→Q14`、Curve `Q14→Q42/AP_RND→Q14` 且不 clamp 的 HLS 源码**不一致**。这是本次发现的真正数值口径差异。刘子铭的三模块 Fixed-point Golden 必须以**WZH CNN 已生成 Q14 A_low 之后接本协议的两个后级**为准，不能直接复用 WZH 原型中的 `parameters_fullres` 或 `enhanced` 整数张量作为我们的 bit-exact golden。

当前未跟踪的旧文档 `fpga/docs/v1_three_module_integration_contract.md` 仍写“CNN HLS core 未实现/接口未冻结”，该状态已被 WZH `01580f0` 的源码和本次审计更新；旧文档可用于理解已有 Master 两模块基线，但**不作为本协议的 CNN 硬件现状依据**。

## 8. 两套 golden、验收指标与实施边界

**FP32 Golden**：`outputs/zero_dce_pp/reference/` 的原软件 FP32/NCHW `.npy`（或其它按同一模型/预处理生成的多场景 FP32 数据），用于衡量定点链路相对原算法的数值与图像质量损失。**Fixed-point Golden**：按本协议分别模拟 WZH CNN 的 per-layer INT16/INT8/INT32、signed nearest-even 和 clamp，Bilinear/Curve 的真实 `ap_fixed` cast 次序及 `AP_RND/AP_SAT`，并按相同 DDR raw/布局输出，用于判断数值硬件实现是否偏离当前源码。硬件 vs FP32 非零误差本身**不是 bug**；硬件 vs Fixed-point Golden 的原码差异才需要首先定位是软件模拟、RTL 还是接口问题。允许的 0/1 LSB 行为也须由多场景和 RTL 结果确认，本文不设阈值。

预留评估指标：Max Absolute Error、Mean Absolute Error、P99 Absolute Error、PSNR、SSIM、visual comparison；数值指标应同时明确比较对象、每个节点的 Q 格式和是否在显示 clamp 之前计算。FP32 软件拆分验证的 `1e-6` 不直接作为最终定点 FPGA 验收门限。最终 threshold 应在多场景 Fixed-point/FP32 Golden 和 RTL/板上数据完成后由团队决定。

随附 `fpga/reference/fixed_point_v1/` 是**可执行算术骨架，不是完整 CNN 推理**：整数舍入与饱和、Q14 原码编解码、FP32→Fixed16、CNN 单通道 requant/rescale/Tanh Q15→Q14、单点 Bilinear 和单点八轮 Curve。它的 Bilinear/Curve 小向量与**原 HLS 模块**在 Vitis 2025.2 CSim 的 24/8 个输出逐原码一致；含 WZH `night_01` 真正 Q14 A_low 的 16 值前缀 fixture。若要生成整图多场景 Fixed-point Golden，刘子铭还需补完整 CNN 每层计算/权重加载、向量化整图与数据 provenance、每节点原码保存及统一质量指标。WZH/集成侧仍需用 RTL Co-sim 和真实 DDR dump 证明生成 IP 的原码符合此 C 级合同；本任务没有实施该阶段。
