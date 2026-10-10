# Curve Fixed14 / Fixed12 AXI 位宽 sweep 报告

## 1. 目标与边界

以已验证的 `curve_image_fixed16` AXI baseline 为起点，新增彼此独立的 Fixed14、Fixed12 Curve 实验版本，对同一组软件 FP32 参考数据分别运行 Vitis HLS C Simulation 和 C Synthesis，并与 FP32、Fixed16 形成统一比较。两个版本都保持逐元素读取同一个 A，执行八轮 `x = x + A * (x*x - x)`，每轮更新后才量化 x；保留三路 m_axi、AXI-Lite、运行时 `count`、目标器件及 100 MHz 目标时钟。

本次没有修改既有 FP32/Fixed16 baseline 或软件模型，没有添加性能 pragma、RGB 并行、定点验收阈值，也没有决定最终采用的位宽。未运行 RTL Co-simulation、Vivado Implementation、板上测试；未 commit 或 push。

## 2. 基线与输入

- 当前分支：`codex/curve-fp32-baseline`；执行前 HEAD `6bdceba`。本次新增文件尚未提交。
- 工具：AMD Vitis HLS 2025.2（Build 6295257），通过 `E:\Xilinx\2025.2\data\settings64.bat` 加载环境。
- 目标：`xck26-sfvc784-2LV-c`，Vivado IP flow，Target Clock 10.00 ns（100 MHz）。配置沿用 Fixed16 的默认综合选项，未人为设置 tripcount。
- 软件真值：`outputs/zero_dce_pp/reference/` 下的 `model_input.npy`、`parameters_fullres.npy`、`enhanced.npy` 与 `metadata.json`。元数据记录 FP32、NCHW、shape `[1,3,720,1272]`，每个数组 2,747,520 元素。本次 Testbench 实际读取由这些参考数组预先转换的 `outputs/zero_dce_pp/curve_fp32_raw/model_input.f32`、`parameters_fullres.f32`、`enhanced.f32`；三份 raw 文件各为 10,990,080 字节。未在 HLS 内解析 `.npy`。
- 对照报告与综合原始文件：`fpga/reports/curve_fixed16_baseline.md`、`E:\HLS\fpga_curve_image_fp32\fpga_curve_image_fp32\hls\syn\report\curve_image_fp32_csynth.rpt`、`E:\HLS\fpga_curve_fixed16\fpga_curve_fixed16\hls\syn\report\curve_image_fixed16_csynth.rpt`。

## 3. 新增实现

| 新增文件 | 作用 |
|---|---|
| `fpga/hls/curve_image_fixed14/curve_image_fixed14.hpp`、`curve_image_fixed14.cpp` | 独立 Fixed14 顶层、宽中间类型与 AXI 接口。 |
| `fpga/hls/curve_image_fixed14/tb_curve_image_fixed14.cpp`、`hls_config.cfg` | FP32 raw Testbench 与独立 HLS component 配置。 |
| `fpga/hls/curve_image_fixed12/curve_image_fixed12.hpp`、`curve_image_fixed12.cpp` | 独立 Fixed12 顶层、宽中间类型与 AXI 接口。 |
| `fpga/hls/curve_image_fixed12/tb_curve_image_fixed12.cpp`、`hls_config.cfg` | FP32 raw Testbench 与独立 HLS component 配置。 |
| `fpga/scripts/curve_fixed14_csim.cmd`、`curve_fixed14_synth.cmd` | Fixed14 的 Vitis 环境加载和实际运行入口。 |
| `fpga/scripts/curve_fixed12_csim.cmd`、`curve_fixed12_synth.cmd` | Fixed12 的 Vitis 环境加载和实际运行入口。 |
| `fpga/reports/curve_fixed_width_sweep.md` | 本次实际结果及比较。 |

外部 input、parameter、output 分别使用 `ap_fixed<14,2,AP_RND,AP_SAT>` 与 `ap_fixed<12,2,AP_RND,AP_SAT>`；均为有符号、2 整数位，显式 AP_RND 和 AP_SAT。Fixed14 有 12 小数位、步长 `2^-12 = 0.000244140625`；Fixed12 有 10 小数位、步长 `2^-10 = 0.0009765625`。两者可表示区间分别是 `[-2, 2-2^-12]` 与 `[-2, 2-2^-10]`。

| 计算量 | Fixed14 显式类型（小数位） | Fixed12 显式类型（小数位） |
|---|---|---|
| x、A、外部 I/O | `ap_fixed<14,2,AP_RND,AP_SAT>`（12） | `ap_fixed<12,2,AP_RND,AP_SAT>`（10） |
| `square = x*x` | `ap_fixed<28,4,AP_RND,AP_SAT>`（24） | `ap_fixed<24,4,AP_RND,AP_SAT>`（20） |
| `delta = square-x` | `ap_fixed<29,5,AP_RND,AP_SAT>`（24） | `ap_fixed<25,5,AP_RND,AP_SAT>`（20） |
| `term = A*delta` | `ap_fixed<43,7,AP_RND,AP_SAT>`（36） | `ap_fixed<37,7,AP_RND,AP_SAT>`（30） |
| `updated = x+term` | `ap_fixed<44,8,AP_RND,AP_SAT>`（36） | `ap_fixed<38,8,AP_RND,AP_SAT>`（30） |

中间类型沿着乘法、减法和加法扩宽，只有每轮末尾的 `x = fixed_type(updated)` 明确量化回外部位宽。代码保留三个独立 AXI master bundle：`gmem_input`、`gmem_parameter`、`gmem_output`；三个基地址、`count` 与控制均在 `control` AXI4-Lite。源码只有 INTERFACE pragma，没有新增 PIPELINE/UNROLL pragma。

## 4. 实际执行

在 `E:\github\-` 实际运行以下命令；Fixed14 与 Fixed12 使用各自独立的 `E:\HLS\fpga_curve_fixed14`、`E:\HLS\fpga_curve_fixed12` 组件目录：

```powershell
cmd /c fpga\scripts\curve_fixed14_csim.cmd
cmd /c fpga\scripts\curve_fixed12_csim.cmd
cmd /c fpga\scripts\curve_fixed14_synth.cmd
cmd /c fpga\scripts\curve_fixed12_synth.cmd
```

两项 CSim 在各自 component 中调用 `vitis-run.bat --mode hls --csim --config <对应 hls_config.cfg> --work_dir fpga_curve_fixed14/12`；两项 C Synthesis 调用 `v++.bat -c --mode hls --config <对应 hls_config.cfg> --work_dir fpga_curve_fixed14/12`。所有脚本先调用同一 `settings64.bat`。四项命令退出码均为 0；这是 Vitis HLS CSim/C Synthesis，不是普通 C++ 单测、RTL Co-sim 或 Vivado Implementation。

## 5. C Simulation 数值结果

两个独立 Testbench 均将 FP32 input/A 显式量化到相应外部定点类型，一次调用顶层处理全部 2,747,520 元素，将输出转为 double 后与 FP32 `enhanced.f32` 比较。两次 CSim 日志均显示 `CSim done with 0 errors`。没有设定新的精度 PASS/FAIL 阈值。

| 指标 | Fixed14 | Fixed12 |
|---|---:|---:|
| max absolute error | `0.00240680575` | `0.00941510499` |
| mean absolute error | `0.000284846118` | `0.00107771487` |
| input 越过外部定点可表示范围 | 0 | 0 |
| parameter 越过外部定点可表示范围 | 0 | 0 |
| 输出 min / max | `0 / 1` | `0 / 1` |
| 输出落在定点上下饱和边界 | 0 | 0 |
| 检测到的输入、参数、reference、输出 NaN/Inf | 0 | 0 |

Testbench 直接计数输入/参数越界与输出端点，不逐轮计数内部饱和或溢出；本组输入范围和输出端点检查未显示饱和或明显异常，不能据此断言所有未来输入均安全。`CSim 0 errors` 表示执行成功，不能替代尚未制定的数值验收结论。

## 6. C Synthesis 及统一比较

资源统一取各 `*_csynth.rpt` 的 Utilization Estimates `Total` 行，均为 HLS 估计，非实现后结果。FP32 与 Fixed16 的误差取已有 baseline 报告；Fixed14/12 为本次实测。

| 指标 | FP32 AXI | Fixed16 AXI | Fixed14 AXI | Fixed12 AXI |
|---|---:|---:|---:|---:|
| max absolute error | 0 | 0.000706814229 | 0.00240680575 | 0.00941510499 |
| mean absolute error | 0 | 0.0000745493943 | 0.000284846118 | 0.00107771487 |
| 输入/参数越界 | 未记录 / 未记录 | 0 / 0 | 0 / 0 | 0 / 0 |
| 输出饱和边界计数 | 未记录 | 0 | 0 | 0 |
| DSP | 80 | 24 | 24 | 16 |
| LUT | 8694 | 4902 | 4934 | 4550 |
| FF | 10479 | 3916 | 3744 | 3654 |
| BRAM_18K | 4 | 4 | 4 | 4 |
| URAM | 0 | 0 | 0 | 0 |
| Target Clock | 10.00 ns | 10.00 ns | 10.00 ns | 10.00 ns |
| Estimated Clock | 7.300 ns | 7.300 ns | 7.300 ns | 7.300 ns |
| pixel loop achieved II | 1 | 1 | 1 | 1 |
| pixel loop iteration latency | 128 cycles | 49 cycles | 48 cycles | 48 cycles |
| 外部标量位宽 → AXI 数据宽度 | 32 → 32 bit | 16 → 16 bit | 14 → 16 bit | 12 → 16 bit |
| 整图 Latency / pixel loop Trip Count | `?` / `?` | `?` / `?` | `?` / `?` | `?` / `?` |

Fixed14 和 Fixed12 的 `csynth.rpt` HW Interfaces 均明确显示 **14→16** 与 **12→16**：逻辑元素位宽降低，但实际 AXI 数据宽度仍为 16 bit，不能宣称相对 Fixed16 的 DDR 每元素传输位数继续下降。三路接口均推断 variable length AXI burst。Fixed14 的 LUT 估计 4934，比 Fixed16 的 4902 多 32；资源不是随外部位宽严格单调减少，具体综合映射也受运算绑定与外围逻辑影响。Fixed12 的 DSP 降到 16。相同的 7.300 ns 是 HLS 估计，尚未验证实现时钟或 DDR 有效带宽。

两个新顶层的 loop 层级均为：`curve_image_fixed14/12` → 外层 pixel loop `VITIS_LOOP_22_1` → 内层八轮 loop `VITIS_LOOP_25_2`。Vitis 默认 `syn.compile.pipeline_loops=64` 自动 pipeline 外层，导致内层完全展开 factor 8；两项日志均明确记录此行为。综合报告只保留外层 loop 行：Pipelined `yes`，achieved/target II `1/1`，Iteration Latency `48 cycles`，Trip Count 与 min/max Latency `?`；内层完全展开后无独立 II/Latency 行。`count` 是运行时参数，顶层与整图 min/max Latency 亦为 `?`。顶层汇总的 Interval `0` 属于 auto-rewind 控制报告值，不能解释为图像 II=0。FP32 与 Fixed16 的外层迭代延迟分别为 128、49 cycles，II 都为 1。

## 7. Warning 与验证边界

- 两版 CSim 编译时均在 AMD/Xilinx 头文件中出现 `__GMP_LIBGMP_DLL macro redefined`；不影响 CSim 0 errors。
- 两版综合均有 `WARNING: [RTGEN 206-101] Design contains AXI ports. Reset is fixed to synchronous and active low.`。
- 两份 `csynth.rpt` 的 M_AXI Variable Accesses 对三个端口均显示 `Widen Fail`（214-353，`max_widen_bitwidth` threshold 为 0），同时显示 variable burst `Inferred`。没有看到数组索引地址被忽略或 `count` 仅作零判断的旧 warning。
- 综合日志的 `Design has inferred MAXI bursts and missed bursts` 为提示；具体三路逐元素访问均推断 variable burst，未对实际 DDR 传输效率做测量。
- 未运行 RTL Co-simulation、Vivado Implementation、KV260 板上验证或实际吞吐测试。由于 `count` 运行时确定，报告的整图延迟保持 unknown，没有填入虚构 tripcount。

## 8. 结论、审核状态与下一步

Fixed14、Fixed12 的整图 HLS CSim 与 C Synthesis 均完成。相对 Fixed16，数值误差随位宽缩小而增大；Fixed14 的 DSP 估计不变、LUT 略增，Fixed12 的 DSP/LUT/FF 下降。两版 AXI 物理数据宽度都仍为 16 bit，像素循环 II 都为 1。以上只构成准备阶段的客观比较，**不据此选择最终位宽**，也不制定验收阈值。

当前工作区仅有本次新增的 Fixed14/12 源码、配置、脚本，以及本报告和同时进行的 `bilinear_software_spec.md` 尚未跟踪；既有 FP32/Fixed16 文件无修改。建议供审核的 Commit Message 为 `feat(fpga): add fixed14 and fixed12 curve sweep baselines`，仅为建议，未执行 Git 操作。下一步交由 Master 审阅数值误差、资源以及 16 bit AXI 数据宽度事实后再决定设计方向；本次停止，不实施下一阶段。
