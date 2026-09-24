# Bilinear Fixed16 两行缓存实验报告

## 1. 目标与范围

在已验证的 `bilinear_fp32_buffered` 之外建立独立 `bilinear_fixed16_buffered`，把低分辨率参数输入与全分辨率参数输出统一为 `ap_fixed<16,2,AP_RND,AP_SAT>`，与当前 Curve Fixed16 baseline 的 parameter 输入格式一致。保持 batch=1、channels=3、NCHW、12 倍放大、`align_corners=True`、两行片上缓存、分开的 input/output `m_axi` 和 AXI4-Lite 控制；用 Vitis HLS CSim 与 C Synthesis 检查数值、资源及 output pixel loop II=1。

本次没有修改原始 `bilinear_fp32` 或 `bilinear_fp32_buffered`，没有更改插值坐标公式、做 RGB 并行、连接 Curve/CNN、设立新的精度验收门限、运行 RTL Co-simulation、Vivado Implementation、KV260 板上测试或实测 DDR 带宽；没有 commit 或 push。

## 2. 分支、工具与数据

- 当前分支 `codex/curve-fp32-baseline`；报告时 HEAD `a5d2d3c68fae4821b20f82a220438c373d67d455`，本次文件均未提交。
- Vitis HLS 2025.2，Build 6295257；`E:\Xilinx\2025.2\data\settings64.bat`；Vivado IP flow；器件 `xck26-sfvc784-2LV-c`；Target Clock 10.00 ns（100 MHz）。
- 原始数据：`outputs/zero_dce_pp/reference/parameters_lowres.npy`，FP32 NCHW `[1,3,60,106]`、19,080 元素；`parameters_fullres.npy`，FP32 NCHW `[1,3,720,1272]`、2,747,520 元素。Testbench 实际读取先前从这些 reference 转出的 `outputs/zero_dce_pp/bilinear_fp32_raw/parameters_lowres.f32` 和 `parameters_fullres.f32`；本次没有重生 reference，也没有在 HLS 中解析 `.npy`。
- FP32 buffered 对照数据来自已验证的 `fpga/reports/bilinear_fp32_buffered.md` 和其 HLS 原始综合报告。该 baseline 的相同 reference CSim max/mean absolute error 均为 0。

## 3. 新增文件与实现

| 文件 | 作用 |
|---|---|
| `fpga/hls/bilinear_fixed16_buffered/bilinear_fixed16_buffered.hpp` | 独立 Fixed16 顶层签名与外部类型。 |
| `fpga/hls/bilinear_fixed16_buffered/bilinear_fixed16_buffered.cpp` | 宽定点坐标/权重/乘加、两条 Fixed16 source-row 缓存、AXI 接口。 |
| `fpga/hls/bilinear_fixed16_buffered/tb_bilinear_fixed16_buffered.cpp` | 显式量化 FP32 输入、一次调用整图、对比 FP32 reference 与检查边界。 |
| `fpga/hls/bilinear_fixed16_buffered/hls_config.cfg` | 独立 HLS Component，top 为 `bilinear_fixed16_buffered`。 |
| `fpga/scripts/bilinear_fixed16_buffered_csim.cmd`、`bilinear_fixed16_buffered_synth.cmd` | Vitis 2025.2 CSim / C Synthesis 入口。 |
| `fpga/reports/bilinear_fixed16_buffered.md` | 本报告。 |

外部 Fixed16 为 16 bit 总宽、2 bit 整数（含符号）、14 bit 小数，量化步长 `2^-14 = 0.00006103515625`，可表示 `[-2, 2-2^-14]`。输入和输出 `m_axi` 数据宽度均为 16 bit，基地址、`input_height`、`input_width` 与控制在 AXI4-Lite。片上 `row_a[128]`、`row_b[128]` 复用 FP32 buffered 的逻辑：当前输出行所需 `y0/y1` 首次装入，连续相同 source-row pair 直接复用，`y0` 前进时逻辑交换缓存并仅补读新的 `y1`；pixel loop 只从本地缓存读取四邻居。两数组使用 `BIND_STORAGE type=ram_2p impl=bram`；没有手动 PIPELINE、UNROLL 或通道并行。

坐标仍是 `sy=oy*(Hi-1)/(Ho-1)`、`sx=ox*(Wi-1)/(Wo-1)`，而非 `oy/12` 或 `ox/12`；`y0/x0=floor`，`y1/x1` 向输入边界截住，`wy/wx` 为源坐标小数部分。最后一个输出行/列直接置为最后一个输入行/列的精确坐标，这是原公式在端点的精确值，用于避免定点 ratio 舍入造成角点漂移。加权和仍按先水平两行、再垂直合成的顺序计算。

| 显式类型 | 总位宽 W | 整数位 I | 小数位 F | 用途 |
|---|---:|---:|---:|---|
| `bilinear_fixed16_t = ap_fixed<16,2,AP_RND,AP_SAT>` | 16 | 2 | 14 | 外部输入/输出、两行缓存、四邻居样本；最终输出才量化回 Fixed16。 |
| `coord_t = ap_ufixed<48,16,AP_RND,AP_SAT>` | 48 | 16 | 32 | 输入/输出尺寸参与比例计算、`sx/sy` 源坐标。 |
| `ratio_t = ap_ufixed<33,1,AP_RND,AP_SAT>` | 33 | 1 | 32 | `(Hi-1)/(Ho-1)`、`(Wi-1)/(Wo-1)` 的缓存比例。 |
| `weight_t = ap_ufixed<33,1,AP_RND,AP_SAT>` | 33 | 1 | 32 | `wx/wy` 与 `1-wx/1-wy`。 |
| `hproduct_t = ap_fixed<49,3,AP_RND,AP_SAT>` | 49 | 3 | 46 | 水平每项 `weight×sample`。 |
| `hsum_t = ap_fixed<50,4,AP_RND,AP_SAT>` | 50 | 4 | 46 | 水平两项之和。 |
| `vproduct_t = ap_fixed<65,5,AP_RND,AP_SAT>` | 65 | 5 | 60 | 垂直每项 `weight×hsum`；从全精度乘积在 60 个小数位舍入。 |
| `vsum_t = ap_fixed<66,6,AP_RND,AP_SAT>` | 66 | 6 | 60 | 垂直两项之和，再显式转换为外部 Fixed16。 |

上述坐标/权重保留 32 个小数位，计算中没有每步回压到 14 个小数位。HLS 运行时输入宽度须为 `<=128`，与 FP32 buffered 实验容量相同；零尺寸或超过该宽度则不写输出。`coord_t` 的 16 个整数位也是当前 V1 以外的尺寸范围限制，超大尺寸及 `unsigned int` 输出尺寸乘 12 的溢出均未验证。

## 4. 实际运行及 CSim 数值结果

在 `E:\github\-` 运行：

```powershell
cmd /c fpga\scripts\bilinear_fixed16_buffered_csim.cmd
cmd /c fpga\scripts\bilinear_fixed16_buffered_synth.cmd
```

脚本均先调用 `settings64.bat`，在 `E:\HLS\fpga_bilinear_fixed16_buffered` 工作目录分别调用：

```text
E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat --mode hls --csim --config E:\github\-\fpga\hls\bilinear_fixed16_buffered\hls_config.cfg --work_dir fpga_bilinear_fixed16_buffered
E:\Xilinx\2025.2\Vitis\bin\v++.bat -c --mode hls --config E:\github\-\fpga\hls\bilinear_fixed16_buffered\hls_config.cfg --work_dir fpga_bilinear_fixed16_buffered
```

两项命令退出码均为 0。Vitis CSim 日志 `E:\HLS\fpga_bilinear_fixed16_buffered\fpga_bilinear_fixed16_buffered\hls\csim\report\bilinear_fixed16_buffered_csim.log` 显示 **`CSim done with 0 errors`**。Testbench 将 19,080 个低分辨率 FP32 值显式量化为外部 Fixed16，单次调用处理 2,747,520 个输出，转为 double 后对比 FP32 reference：

| 指标 | 实际结果 |
|---|---:|
| 输出 shape / 元素 | `[1,3,720,1272]` / **2,747,520** |
| max absolute error | **`6.0498714447e-05`** |
| mean absolute error | **`1.75228651079e-05`** |
| 输入 FP32 超出 Fixed16 可表示范围 | **0** |
| 输入 / reference / 输出 NaN、Inf | **`0 / 0 / 0`** |
| 输出 min / max | `-0.350158691 / -0.0570068359` |
| 输出落在 Fixed16 饱和边界的元素 | **0** |
| 三通道四角与量化后输入精确相等 | **12/12** |
| 四角最大绝对误差 vs 量化后输入 | **0** |
| 四角最大绝对误差 vs FP32 reference | `3.0055642128e-05` |

测试未设新的精度 PASS 门限；CSim 0 errors 表示整图计算完成、角点正确且没有非有限值，误差供 Master 判断。本组输出完全未落在 Fixed16 饱和边界，因此本组没有观察到输出饱和；没有对所有潜在输入证明不会在中间运算饱和。FP32 buffered 对同一 reference 的误差是 0，Fixed16 的非零误差包括输入量化、输出量化和定点坐标/插值计算的影响，本次未做逐来源误差分解。

## 5. C Synthesis 与 FP32 buffered 对比

C Synthesis 及 Vivado IP 导出成功。Fixed16 报告：`E:\HLS\fpga_bilinear_fixed16_buffered\fpga_bilinear_fixed16_buffered\hls\syn\report\bilinear_fixed16_buffered_csynth.rpt` 与相应 pipeline 子模块报告；`csynth.rpt` 含 AXI burst/接口表。以下资源取各顶层详细 `Utilization Estimates / Total` 行，均为 HLS 估计，不是 Vivado Implementation 实占。

| 指标 | FP32 buffered | Fixed16 buffered | 变化 |
|---|---:|---:|---:|
| DSP | 42 | **33** | -9 |
| LUT | 8,328 | **7,985** | -343 |
| FF | 6,497 | **5,470** | -1,027 |
| BRAM_18K | 6 | **4** | -2 |
| URAM | 0 | **0** | 0 |
| Target Clock | 10.00 ns | **10.00 ns** | 相同 |
| Estimated Clock | 7.300 ns | **7.300 ns** | 相同 |
| output pixel Achieved II | 1 | **1** | 保持目标 |
| output pixel Iteration Latency | 36 cycles | **5 cycles** | -31 cycles |
| initial two-row loader II | 2 | **2** | 相同 |
| incremental one-row loader II | 1 | **1** | 相同 |
| input/output m_axi 数据宽度 | 32/32 bit | **16/16 bit** | 均减半 |

Fixed16 `csynth.rpt` 模块汇总 LUT 为 7,989，比详细 Total 7,985 多 4；FP32 buffered 的对应两值为 8,332 / 8,328。比较统一使用详细 Total。Fixed16 两行本地缓存各占 1 个 BRAM_18K，输入 AXI 实例估计另外占 2 个；FP32 两行缓存各占 2 个，故 BRAM 合计减少 2 个。此资源变化是综合估计；相同时钟估计也不能替代实现后的时序或整图吞吐。

层级为 top `bilinear_fixed16_buffered` → `channel` (`VITIS_LOOP_44_1`) → `oy` (`VITIS_LOOP_51_2`) → 条件性的初始双行 loader (`VITIS_LOOP_61_3`) 或增量单行 loader (`VITIS_LOOP_69_4`) → 输出像素 `ox` (`VITIS_LOOP_82_5`)。HLS 因 `pipeline_loops` 默认阈值自动 pipeline 三个内层循环；没有记录自动 flatten 或 unroll，也没有源码性能 pragma。

| 顶层 / loop | Pipelined | Target II | Achieved II | Iteration Latency | Trip Count | min/max Latency (cycles) |
|---|---|---:|---:|---:|---|---|
| top | no | unknown | unknown | unknown | unknown | `? / ?` |
| channel `44_1` | no | - | - | `?` | 3 | `? / ?` |
| output row `51_2` | no | - | - | `?` | `0 ~ 4294967292`（报告原值） | `? / ?` |
| initial loader `61_3` | yes, auto | 1 | **2** | 12 | `1 ~ ?` | `11 / ?` |
| incremental loader `69_4` | yes, auto | 1 | **1** | 3 | `1 ~ ?` | `2 / ?` |
| output pixel `82_5` | yes, auto | 1 | **1** | 5 | `?` | `? / ?` |

`Hi/Wi` 是运行时参数，报告中的大范围 tripcount 不是当前图像实测次数；top 整图 Latency/Interval 和 output pixel loop 总 Latency/Trip Count 未静态确定，保留 `?`，没有伪造固定 tripcount。HLS 汇总中的 “All loop constraints were NOT satisfied” 对应初始双行 loader II=2，**不表示输出 pixel loop 失去 II=1**。

## 6. AXI burst、warning 与数据访问

HLS 的 M_AXI Burst Information 对增量 loader `VITIS_LOOP_69_4` 推断 variable-length、16 bit input read burst，对 output pixel `VITIS_LOOP_82_5` 推断 variable-length、16 bit output write burst。初始双行 loader 在源码第 62–63 行的两路读未推断 burst，显示 `214-231 Access is clobbered by load`；增量读取在外层条件分支显示 `214-232`，但内层仍为 `Inferred`；输出写在外层行循环显示 `214-230 Stride is incompatible`，内层像素循环仍为 `Inferred`。读写都显示 `214-353` AXI widening 未发生，实际接口维持 16 bit。报告提醒推断的 burst 在 RTL 生成时可能按最大 burst 长度进一步拆分。

`hls_compile.log` 的关键 `HLS 200-448` warning 指出初次双行 loader 对同一 `gmem_input` 同时发两次 bus read，因此该 loader 的 II 下界为 2；Fixed16 与 FP32 buffered 一样。没有看到本地 RAM port conflict warning，输出 pixel loop 的实际 II 为 1。CSim 编译器还在工具自带 `gmp.h` / `floating_point_v7_1_bitacc_cmodel.h` 报 `__GMP_LIBGMP_DLL` macro redefined；RTL 生成时有 RTGEN `206-101` dangling AXI 子模块端口及 AXI 复位固定为同步低有效的 warning。上述 warning 未阻止 CSim、综合和 IP 导出。

当前 reference 下沿用两行复用：每通道先装 2 行，后续仅在 source row 前进时装入新行，按当前 60×106×3 尺寸推导 180 次 source-row 装载、19,080 个 input scalar 读取表达式、2,747,520 个 output scalar 写入表达式。该数字由代码和坐标序列推导，非 DDR 实测事务或带宽；Fixed16 每个标量 16 bit，FP32 为 32 bit。

## 7. 结论与建议

Fixed16 两行缓存独立实验已通过整图 CSim（0 errors），实际 max/mean absolute error 为 `6.0498714447e-05` / `1.75228651079e-05`，无输入越界、无非有限值、无输出边界饱和，量化后的四角精确保持。C Synthesis 成功且 output pixel loop **Achieved II=1**，同时相较 FP32 buffered 减少 DSP 9、LUT 343、FF 1,027、BRAM 2；初始双行 loader 仍 II=2。可保留作为下一步评估的独立候选，尚无用户指定的精度验收门限或 RTL/板上总性能结论。

与本次直接相关的后续是由 Master 审核数值误差与资源代价；如需确认整图时间或实际 DDR 行为，再单独安排 RTL Co-simulation / 板上测试。本次不继续实施其他阶段。

建议 Commit Message（仅供审核，本次未提交）：`fpga: add buffered Fixed16 bilinear HLS experiment`

工作区状态：位于 `codex/curve-fp32-baseline`，本次仅新增上述 Fixed16 目录、两个脚本和报告；原 FP32 baseline 与 FP32 buffered 文件未改。没有 `git add`、commit 或 push。
