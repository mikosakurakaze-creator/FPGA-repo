# V1 三模块定点数值协议整理与 reference 骨架报告

日期：2026-09-25。**任务完成**：已从三模块实际源码生成 Markdown 协议、含 14 层/486 个通道小数位的机器 JSON、标准库 Python 算术骨架及 11 项单元测试。AMD `AP_RND` 中点和中间表达式类型经过实际 Vitis 2025.2 C Simulation 核实；Python Bilinear/Curve 小向量与未修改的原 HLS 模块逐原码一致。此报告只冻结**源码级数值规则**；不声明 CNN 已进入现有 KV260 Vivado V1，不制定最终画质验收门限。

## 1. 目标、版本与执行范围

目标是为刘子铭的三模块 Fixed-point Golden 提供唯一、可实施的 V1 数值依据：软件 FP32 参考、WZH CNN→Q14 A_low、当前 Bilinear Fixed16、当前 Curve Fixed16 的每个格式、cast、rounding、saturation、layout 与 DDR 缓冲关系。

| 项目 | 实际基线 |
|---|---|
| Master 分支/HEAD | `codex/curve-fp32-baseline` / `7b86ca168352c8f2d1bf605184f720c3e2c32527` |
| WZH 分支/审计 commit | `origin/feat/zero-dce-quantization` / `01580f026a9d14145cad91e8957143c120928a0d`；隔离 detached worktree `E:/HLS/wzh_cnn_latest_01580f0`，其跟踪文件未修改 |
| 工具 | AMD Vitis HLS 2025.2 Build 6295257；Python 3.12.10（本机隔离 venv）；Python helper 仅标准库 |
| 目标 | KV260 `xck26-sfvc784-2LV-c`、100 MHz/10 ns 为现有 V1；本次只用该 part 跑极小 CSim oracle，**未做综合** |
| 当前参考 | `outputs/zero_dce_pp/reference/metadata.json`、FP32 `.npy/.f32`；WZH `night_01` Q14 A_low 原码向量及 manifest，19,080 个、38,160 B，SHA-256 `31abdd23520d32efe75928ef394017bd2f515b2805144a85735eebc9481dddd1` |

没有修改 CNN/Bilinear/Curve HLS 算法、pragma、AXI 接口或 Fixed16 格式；没有修改 Vivado BD、重新生成 bitstream/XSA、merge/cherry-pick WZH、commit 或 push。既有 routed/bitstream/XSA baseline 保持原状。

## 2. 实际读取的源码和事实依据

- FP32 前处理及输出：`model/zero_dce_pp/preprocessing.py:33-49`、`enhancement.py:20-32,35-60,63-100`、`upstream/model.py:35-40,66-80`、`io_utils.py:43-63`、reference `metadata.json`；此前 `fpga/reports/bilinear_coordinate_oracle.md` 的本机 PyTorch 坐标验证用于核对 `UpsamplingBilinear2d` 有效 `align_corners=True`。
- WZH CNN 真正代码：隔离 worktree 的 `fpga/hls/zero_dce_cnn_top.h`、`zero_dce_cnn_top.cpp:8-299`；逐层规则 `configs/zero_dce_pp_integer_rules.json`、输出/DDR 声明 `configs/zero_dce_pp_hls_interface.json`、软件量化规则 `deployment/zero_dce_integer_ptq.py:30-60,110-209,212-254`。逐层 C++ table 与规则 JSON 中的 F、groups、kernel、padding、通道数、权重偏移都已程序核对。
- Master 后级现行实现：`fpga/hls/bilinear_fixed16_buffered/bilinear_fixed16_buffered.hpp:7` 与 `.cpp:6-110`、`fpga/hls/curve_image_fixed16/curve_image_fixed16.hpp:6` 与 `.cpp:5-32`，及各自原 Testbench 的 FP32→Fixed16 输入构造。旧报告仅辅助交叉检查，类型/cast 仍以这些源码为准。
- AMD 官方本地 HLS 头文件 `E:/Xilinx/2025.2/Vitis/include/etc/ap_fixed_base.h:120-168,366-381,690-725,1273-1335`：运算返回类型、`AP_RND` 量化与 unsigned division 的实际规则；用最小 Vitis CSim `decltype::width/iwidth` 和正负中点再次确认。`AP_RND` **不是**最近偶数，`AP_RND_CONV` 才在中点检查 LSB。

## 3. 新增文件及核心内容

| 新增文件 | 用途与关键设计 |
|---|---|
| `fpga/docs/v1_fixed_point_protocol.md` | 完整人读合同：FP32 口径、CNN 14 层/缩放/ReLU/skip/Tanh、WZH 最近偶数与 AMD `AP_RND`、Bilinear/Curve 逐 cast 点、四块 DDR buffer、两套 golden 和待办边界。 |
| `fpga/docs/v1_fixed_point_protocol.json` | 机器可读合同，字段含 `software_reference`、`cnn_input`、`cnn_layers`（14 层各输出通道 weight frac/bias frac/shift，共 486 值）、`cnn_output`、`bilinear`、`curve`、`buffers`、`rounding_modes`、`saturation_modes`、`layout`；bitwidth、Q、raw 范围、零点、字节序和 cast 枚举均明确。 |
| `fpga/reference/fixed_point_v1/__init__.py`, `arithmetic.py` | 标准库实现 signed nearest-even、AMD `AP_RND`、INT16 saturation、raw Q14 little-endian 编解码、FP32→Fixed16、CNN 单通道 requant/rescale/Tanh 边界、Bilinear 单点与 Curve 八轮单点。不是完整 CNN/整图性能实现。 |
| `fpga/reference/fixed_point_v1/test_arithmetic.py` | 正负中点、饱和边界、signed 负数舍入、CNN Tanh/重缩放、真实 WZH Q14 A_low 前 16 值、三通道 Bilinear 四角/内点、Curve 已验证简单输入、JSON 结构共 **11 项**。 |

机器 JSON 由本次隔离审计脚本从 WZH **提交版本**的逐层规则/源码 table 生成，且全 486 个 `weight_frac` 与其实际打包的 `weight_frac.bin` **486/486 相同**（该文件 SHA-256 `54a14af94229aee7c9ac574b6f024b11a340ac07146657b4209366d070cf045d`）；写入后 JSON 自身不依赖外部 worktree。它不是把整份 WZH 软件整数原型直接作为当前后级 golden。JSON 的 `validation` 只记本次有证据的小样本；不暗示全图 Python helper 已通过位级验证。新增文件均未 staged 或提交。

## 4. 已确认的数值规则与发现的口径差异

| 边界/步骤 | 源码确认的定点规则 |
|---|---|
| CNN 输入 | CNN top 仅接已 crop、缩小、量化后的 RGB planar NCHW `[1,3,60,106]`，signed INT16 Q14，raw/16384，小端 2 B；原图 720×1280→720×1272 的前处理不在 IP 内。WZH 软件整数 producer 用 uint8→Q14 nearest-even，再按 `align_corners=False` 中心四点平均 nearest-even。 |
| CNN 14 层 | 激活 signed INT16，F 每层 12/13/14/16；权重 signed INT8，**每输出通道** F 为 7–16（逐层各有差别，最后层固定 9）；偏置/accumulator signed INT32，F=`F_in+F_weight[c]`。两乘数转 INT32，乘法临时积为 64 bit，累加寄存器 INT32，`shift=F_in+F_weight[c]−F_out` 后 nearest-even，再 saturate INT16；ReLU 和 concat 按源码顺序。 |
| Tanh→A_low | 最终 INT16 Q16 激活 nearest-even 右移 8 得 Q8 索引，索引 clamp `[-2048,2048]`，查 4097 点 INT16 Q15 LUT，再 nearest-even 右移 1、saturate INT16，形成 19,080 个 Q14 raw。 |
| CNN→Bilinear | DDR raw 16 bit **原样解释**为 `ap_fixed<16,2,AP_RND,AP_SAT>`，无需 float 中转或重新量化。Q14 可表示 `[-2,1.99993896484375]`，LSB `2^-14`。 |
| Bilinear | 有效 `align_corners=True`，Q32 ratio 由 unsigned 除法**截余数**得到；Q32 坐标/权重。水平乘法 Q46、和 Q46 均精确；垂直乘法原始 Q78，各自以 `AP_RND` 收至 Q60；垂直和 Q60 精确；最终以 `AP_RND/AP_SAT` 收至 Q14。两行 BRAM 缓存只改访问架构。 |
| Curve | 每个元素 A 固定；Q14 `x*x`→Q28，`square−x`→Q28，`A*delta`→Q42，`x+term`→Q42，**每轮末**以 `AP_RND/AP_SAT` 收回 Q14，共 8 轮；无 `[0,1]` clamp。 |
| DDR | A_low 19,080×2=38,160 B；A_full/model_input/enhanced 各 2,747,520×2=5,495,040 B；RGB planar NCHW、C 连续、小端、无 row padding。当前 Master BD 含 Bilinear+Curve，不含 CNN。 |

与已有文档/代码的差异须特别保留：

1. WZH `deployment/zero_dce_integer_ptq.py` 的 **软件整数整链**中，Bilinear 在水平与垂直两阶段均 nearest-even 回整数，Curve 使用 Q15 状态并逐轮 clamp `[0,Q15]`。这**与当前 Master 后级 HLS** 的宽中间 `AP_RND/AP_SAT` Bilinear、Q14 八轮且不 `[0,1]` clamp 的 Curve 不一致。刘子铭必须从 WZH Q14 A_low 边界开始按本协议另建后级 Fixed-point Golden；不能直接把 WZH 软件 prototype 的 A_full/enhanced 当作这两个 HLS IP 的位级真值。
2. 旧的未跟踪 `fpga/docs/v1_three_module_integration_contract.md` 称 CNN 硬件尚不存在；WZH 最新 `01580f0` 已有 HLS top 和 DDR writer，旧文档的此状态陈述过时。本任务未改旧文档，以当前 commit 源码为准。
3. FP32 downsample `align_corners` **在源码中省略**，本机 PyTorch 有效值 `False`；A 图 `UpsamplingBilinear2d` 当前有效值 `True`。文档把“显式源码参数”和“实际行为”分开描述。
4. 现有 Curve Testbench 从 FP32 raw 经 `curve_fixed16_t(float)` 构造 `model_input`。WZH 软件整数 prototype 的 uint8→Q14 nearest-even 原码不能未经核对就当作这条生产路径；未来 PS 数据提供者需复现选定的当前 Fixed16 cast 规则。

## 5. 实际运行、正确性与可复核结果

实际运行的命令（外部 oracle 文件保存在 `E:/HLS/fixed_point_protocol_oracle/`；不属于 Master 仓库）：

```powershell
git status --short --untracked-files=all
git branch --show-current
git rev-parse HEAD
& 'E:\HLS\fixed_point_protocol_oracle\run.cmd'
& 'E:\HLS\fixed_point_protocol_oracle\run_modules.cmd'
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' 'E:\HLS\fixed_point_protocol_oracle\build_json.py'
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' -m unittest discover -s 'fpga/reference/fixed_point_v1' -p 'test_*.py' -v
```

两个 `.cmd` 均先加载 `E:/Xilinx/2025.2/data/settings64.bat`，再调用 `vitis-run.bat --mode hls --csim`；目标 `xck26-sfvc784-2LV-c`，10 ns，仅 **C Simulation**。中点/type oracle `CSim done with 0 errors`：`AP_RND` 的 +0.5/+1.5/−0.5/−1.5 LSB 分别输出 +1/+2/0/−1 原码；超量输入 +2.25/−2.25 饱和至 +32767/−32768。C++ `decltype` 确认 Bilinear division `<80,48>` F32、输出索引×ratio `<65,33>` F32、水平乘/和 `<49,3>`/`<50,4>` F46、垂直乘运算 `<83,5>` F78、目标垂直乘 `<65,5>` F60，以及 Curve 运算 `<32,4>` F28、`<33,5>` F28、`<49,7>` F42、`<50,8>` F42。

第二个 oracle **实际调用当前未修改的 `bilinear_fixed16_buffered` 和 `curve_image_fixed16`**，`CSim done with 0 errors`：输入三通道 2×3，输出 24×36；抽查每通道四角+四内点共 **24 个 Bilinear output raw**，与 Python helper 24/24 完全一致；Curve 8 个不同 x/A 输入的八轮结果 **8/8 raw 相同**。该例覆盖负数权重输入、各方向插值、端点、0、1、A 正负、Fixed16 轨道边界，仍不是全域形式化证明。完整向量样例嵌于单元测试。

Python 标准库 unit tests **11 tests，全部 PASS**。WZH `night_01` A_low fixture 取该 commit 实际导出、经上一轮审计 SHA 校验的 `.bin` 前 16 个 raw；测试不需要外部 38,160 B 数据包。本任务不重新跑 2,747,520 元素整图，也不重新跑 WZH CNN 大型 CSim；其既有整图/19,080 输出验证见 `wzh_latest_cnn_fpga_review.md` 等独立报告。HLS CSim 过程中工具自带 `gmp.h` 对 `__GMP_LIBGMP_DLL` 的宏重定义 warning 仍出现，但均为 **0 errors**；没有本任务的 HLS C Synthesis 报告和资源值。

## 6. FP32 Golden、Fixed-point Golden 和后续责任

FP32 Golden 是原算法参考，用于评估定点损失；Fixed-point Golden 是本协议按位模拟，用于核对硬件计算与 DDR 交接。硬件与 FP32 有非零误差不等于实现 bug；硬件与 Fixed-point Golden 不同才应逐级排查，并先排除软件模拟/生成向量口径错误。**当前不设最终 acceptance threshold**，特别不能把 FP32 软件拆分的 `1e-6` 套到定点 FPGA。

仅预留 Max Absolute Error、Mean Absolute Error、P99 Absolute Error、PSNR、SSIM、visual comparison。刘子铭还需实现完整 CNN 14 层的软件 golden（含 WZH 固定权重、每通道 F 和 LUT）、整图向量化 Bilinear/Curve、多个独立场景的 FP32 与 Fixed-point 节点导出，保存每节点原码/布局/散列并报告这些指标，然后与 Master 一起确定最终阈值。WZH/硬件侧仍需完成 CNN RTL Co-sim、KV260 100 MHz timing 可行性和真实 m_axi DDR 输出 bit pattern；三模块 Vivado/PS/板端集成尚未执行。

**当前结论**：这版协议与 Python 算术骨架值得作为刘子铭软件 golden 的数值基础保留；全链、全图、RTL 和实际 DDR 的位级一致性仍待验证。主工作树本轮新增文档、JSON、Python 文件和本报告，原有未跟踪文件保留；未执行 `git add`、commit 或 push。建议审核时重点确认 WZH per-channel 模型参数来源及未来 PS `model_input` 的量化 producer；本轮停止，不进入下一阶段。
