# Curve Image Fixed16 AXI baseline 实验报告

## 1. 任务目标与范围

基于已通过验证的 `curve_image_fp32` AXI image-level baseline，新增独立的 Fixed16 Curve 顶层及 Testbench，使用 `ap_fixed<16,2,AP_RND,AP_SAT>` 表示外部 input、parameter、output，并实际运行 Vitis HLS 2025.2 C Simulation 与 C Synthesis。每个元素使用同一个参数 A，连续八轮执行 `x = x + A * (x*x - x)`，仅输出第八轮结果。

本次没有覆盖或修改 FP32 baseline，没有设置新的数值验收阈值；没有定点格式搜索、RGB 三通道并行、额外的 PIPELINE/UNROLL 性能 pragma、Bilinear/CNN 修改、Co-simulation、Vivado Implementation 或板上测试。没有 commit 或 push。

## 2. 基线、版本与数据

- Git 分支：`codex/curve-fp32-baseline`；起点 HEAD：`d88dc0a`。本次文件均未提交。
- 工具：Vitis HLS 2025.2，Build 6295257。使用 `E:\Xilinx\2025.2\data\settings64.bat` 加载环境。
- 目标器件：`xck26-sfvc784-2LV-c`，Vivado IP flow；HLS 目标时钟 10.00 ns。
- FP32 对照：`E:\HLS\fpga_curve_image_fp32\fpga_curve_image_fp32\hls\syn\report\curve_image_fp32_csynth.rpt`，同一器件与目标时钟，AXI 接口 baseline；其先前 CSim 对 `enhanced` 的 max/mean absolute error 均为 0。
- 软件参考：`outputs/zero_dce_pp/reference/model_input.npy`、`parameters_fullres.npy`、`enhanced.npy`，以及同目录 `metadata.json`。本次 Testbench 实际读取的是这些参考数据已转换出的 `outputs/zero_dce_pp/curve_fp32_raw/model_input.f32`、`parameters_fullres.f32`、`enhanced.f32`，而非在 HLS 中解析 `.npy`。原始 reference metadata 记录 FP32、NCHW、shape `[1,3,720,1272]`，即 2,747,520 个元素；Testbench 检查三份 raw 文件各自的元素数。
- 先前范围报告 `fpga/reports/curve_fixed_range_analysis.md` 记录本组参考数据 input 范围 `[0,1]`、A 范围约 `[-0.350147754,-0.057052601]`。这些范围只描述当前数据，不代表未来图像。

## 3. 实际修改与定点设计

新增文件：

| 文件 | 作用 |
|---|---|
| `fpga/hls/curve_image_fixed16/curve_image_fixed16.hpp` | 定义外部 Fixed16 类型及独立顶层签名。 |
| `fpga/hls/curve_image_fixed16/curve_image_fixed16.cpp` | 实现逐元素八轮 Curve，明确宽中间类型和每轮 x 的 16 bit 量化；保留与 FP32 baseline 对应的三路独立 m_axi bundle 和 AXI-Lite 控制。 |
| `fpga/hls/curve_image_fixed16/tb_curve_image_fixed16.cpp` | 读取 FP32 raw，显式量化 input/A，一次调用处理整图，转换输出并统计误差、输入饱和、输出范围和饱和边界。 |
| `fpga/hls/curve_image_fixed16/hls_config.cfg` | 独立 HLS component 配置，top 为 `curve_image_fixed16`。 |
| `fpga/scripts/curve_fixed16_csim.cmd` | 加载 Vitis 2025.2 环境并运行 CSim。 |
| `fpga/scripts/curve_fixed16_synth.cmd` | 加载同一环境并运行 C Synthesis。 |
| `fpga/reports/curve_fixed16_baseline.md` | 本报告。 |

外部类型 `ap_fixed<16,2,AP_RND,AP_SAT>`：16 bit 总宽、2 bit 整数（含符号）、14 bit 小数，步长 `2^-14 = 0.00006103515625`，可表示范围 `[-2, 2-2^-14]`。输入、参数、输出各为 16 bit m_axi 数据，三个 bundle 分别为 `gmem_input`、`gmem_parameter`、`gmem_output`；基地址、`count` 及控制信号在 `control` AXI4-Lite。三路分开允许输入、参数读取与输出写入使用独立 AXI master，同时与 FP32 对照保持相同的接口划分。`count` 仍为运行时 `unsigned int`，控制外层循环。

| 变量 | 显式类型 | 整数位 | 小数位 | 用途 |
|---|---|---:|---:|---|
| `x`, `a`, 外部 I/O | `ap_fixed<16,2,AP_RND,AP_SAT>` | 2 | 14 | 每轮 x 更新后量化回此格式；同一 A 保持不变。 |
| `square` | `ap_fixed<32,4,AP_RND,AP_SAT>` | 4 | 28 | 保存 `x*x`。 |
| `delta` | `ap_fixed<33,5,AP_RND,AP_SAT>` | 5 | 28 | 保存 `x*x-x`。 |
| `term` | `ap_fixed<49,7,AP_RND,AP_SAT>` | 7 | 42 | 保存 `A*(x*x-x)`。 |
| `updated` | `ap_fixed<50,8,AP_RND,AP_SAT>` | 8 | 42 | 保存 `x+term`，然后显式转换回 Fixed16。 |

这些显式中间类型保留乘法、加减所需的小数精度，并提供比本组参考数据实测范围更宽的整数范围；没有在每一步立即压回 16 bit。每轮更新后的 x 则明确按 AP_RND / AP_SAT 量化。代码中没有额外性能 pragma，仅有保持 AXI 接口所需的 INTERFACE pragma。

## 4. 实际执行

在仓库根目录 `E:\github\-` 实际运行：

```powershell
cmd /c fpga\scripts\curve_fixed16_csim.cmd
cmd /c fpga\scripts\curve_fixed16_synth.cmd
cmd /c fpga\scripts\curve_fixed16_csim.cmd
```

最后一次 CSim 是在 Testbench 增加输出边界诊断后复跑；算法源码未变，综合报告仍对应同一顶层源码。脚本分别实际调用 `E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat --mode hls --csim --config E:\github\-\fpga\hls\curve_image_fixed16\hls_config.cfg --work_dir fpga_curve_fixed16` 与 `E:\Xilinx\2025.2\Vitis\bin\v++.bat -c --mode hls --config E:\github\-\fpga\hls\curve_image_fixed16\hls_config.cfg --work_dir fpga_curve_fixed16`，工作目录为 `E:\HLS\fpga_curve_fixed16`。两脚本先调用 `settings64.bat`。

未运行：普通独立 C++ 测试、RTL Co-simulation、Vivado Implementation、板上验证。

## 5. C Simulation 数值结果

Vitis HLS CSim 成功，最终日志显示 **`CSim done with 0 errors`**。Testbench 一次调用 `curve_image_fixed16()` 处理全部 **2,747,520** 个元素；FP32 input/A 先显式转换为 Fixed16，输出转换为 double 后对比 FP32 `enhanced` reference。

| 指标 | 实际结果 |
|---|---:|
| max absolute error | `0.000706814229` |
| mean absolute error | `0.0000745493943` |
| input 量化时越过 Fixed16 可表示范围的数量 | 0 |
| parameter 量化时越过 Fixed16 可表示范围的数量 | 0 |
| Fixed16 输出 min / max | `0 / 1` |
| 输出落在 Fixed16 上下饱和边界的数量 | 0 |
| 检测到的输入、参数、reference、输出 NaN/Inf | 0 |

未设数值验收阈值，因此“CSim 0 errors”只表示仿真执行和 Testbench 检查完成，不代表已通过某个精度门限。当前 Testbench 检查了输入量化越界与输出饱和边界，未逐轮直接计数内部饱和；结合本组参考输入范围及输出范围，未观察到饱和或明显异常。没有对所有未来输入作无溢出保证。FP32 AXI baseline 的同一参考对比误差为 0，Fixed16 的非零误差来自输入/A 量化及八轮逐轮量化。

## 6. C Synthesis 与 FP32 AXI 对照

Vitis HLS C Synthesis 成功，Vivado IP 导出完成。资源取两份 `*_csynth.rpt` 的 Utilization Estimates `Total` 行，均为综合估计值，尚非实现后的实际占用。

| 指标 | FP32 AXI baseline | Fixed16 baseline | 变化 |
|---|---:|---:|---:|
| DSP | 80 | 24 | −56（−70.0%） |
| LUT | 8694 | 4902 | −3792（约 −43.6%） |
| FF | 10479 | 3916 | −6563（约 −62.6%） |
| BRAM_18K | 4 | 4 | 0 |
| URAM | 0 | 0 | 0 |
| Target Clock | 10.00 ns | 10.00 ns | 相同 |
| Estimated Clock | 7.300 ns | 7.300 ns | 相同的 HLS 估计 |
| pixel loop achieved II | 1 | 1 | 相同 |
| pixel loop iteration latency | 128 cycles | 49 cycles | −79 cycles |
| pixel loop Trip Count / 整图 Latency | `?` / `?` | `?` / `?` | `count` 为运行时参数 |

Fixed16 的 `csynth.rpt` 模块层级汇总 LUT 为 4904、FP32 同类汇总为 8696，均比各自详细资源报告的 Total 多 2；上表统一采用详细资源报告的 Total 口径。预计时钟相同是 HLS 的时序估计，不能据此宣称上板频率或整图吞吐已经验证。

关键 loop 层级：顶层 `curve_image_fixed16` → 外层 pixel loop `VITIS_LOOP_22_1` → 内层 8 次 iteration loop `VITIS_LOOP_25_2`。综合器因默认 `pipeline_loops` threshold **自动**给 pixel loop 加 pipeline，并将内层 iteration loop 完全展开；源码没有添加 PIPELINE/UNROLL pragma。综合后的报告只列外层 `VITIS_LOOP_22_1`：Pipelined `yes`，achieved/target II `1/1`，Iteration Latency `49 cycles`，Trip Count、loop min/max Latency 均为 `?`。内层 loop 已展开，没有独立 II/Latency 报告值。顶层 min/max Latency 亦为 `?`；汇总表里的顶层 Interval `0` 属于 `loop auto-rewind stp` 控制描述，不是整图像素 II。FP32 baseline 的外层 loop `VITIS_LOOP_14_1` 同样 II 1、自动 pipeline、Iteration Latency 128 cycles。

综合报告显示三路 m_axi 的数据宽度均为 16 bit，分别推断 variable length burst；AXI-Lite 中 `count` 为 32 bit 寄存器。因为 `count` 运行时提供，工具不能静态确定外层迭代次数及整图 Latency；没有人为设置 tripcount。接口由 FP32 的 32 bit 元素改成 Fixed16 的 16 bit 元素，因此数据传输位宽也改变；本次未实测 DDR 带宽。

## 7. Warning 与限制

- CSim 编译器在 AMD/Xilinx 自带头文件 `gmp.h` 与 `floating_point_v7_1_bitacc_cmodel.h` 中报告 `__GMP_LIBGMP_DLL` macro redefined；非算法代码告警，CSim 仍 0 errors。
- C Synthesis 有 `WARNING: [RTGEN 206-101] Design contains AXI ports. Reset is fixed to synchronous and active low.`，表示 AXI 设计复位形式由工具固定。
- `csynth.rpt` 的 M_AXI Variable Accesses 将三路接口标为 `Widen Fail`（214-353），原因是本次配置 `max_widen_bitwidth` threshold 为 0；它们仍均成功推断 variable length burst。没有发现数组指针索引被忽略或 `count` 仅作零判断的旧警告。
- HLS 自动展开 8 轮使本次综合为八轮并行硬件资源布局；未作额外性能 pragma，但不能把资源下降理解为串行复用一个乘法器。
- 数值结论限于当前参考数据与 HLS CSim；未运行 RTL Co-sim、实现或 KV260 板上测试。

## 8. 结论与下一步建议

独立 Fixed16 AXI Curve 版本已经通过 2,747,520 元素的 Vitis HLS CSim（0 errors）与 C Synthesis。它保留了八轮公式，数值误差已实测并如实记录；相较 FP32 baseline，综合估计 DSP/LUT/FF 下降，pixel loop II 仍为 1，iteration latency 从 128 降为 49 cycles。当前版本适合保留作第一版定点对照，但精度是否满足项目要求尚无已批准的阈值，整图真实时延与上板行为也未验证。

下一步仅建议由 Master 审核本次误差与综合报告，决定是否需要精度门限或后续格式实验；本次停止在 C Synthesis，不继续实施下一阶段。

## 9. 审核与 Git 状态

当前仍在 `codex/curve-fp32-baseline`，HEAD `d88dc0a`；本次新增源码、配置、脚本和报告均为未跟踪文件，既未 `git add`，也未 commit/push。工作区原有未跟踪的 `evaluation/curve_range_analysis.py` 与 `fpga/reports/curve_fixed_range_analysis.md` 保持原样；FP32 baseline 文件无差异。本次变更可供人工审核的建议 Commit Message：`feat(fpga): add independent fixed16 curve axi baseline`。此处仅给出建议，没有执行 Git 提交。
