# Fixed16 Curve / Bilinear RTL Co-simulation

## 1. 目标与范围

验证现有 `curve_image_fixed16` 与 `bilinear_fixed16_buffered` 的 Vitis HLS 2025.2 Verilog RTL，在小尺寸、有代表性的输入上是否逐元素等于各自现有 Fixed16 C/HLS 实现。两项测试各调用顶层一次，C 模型输出作为 golden；另读取 Vitis 生成的 C/RTL 输出向量，逐个比较 16-bit 原始值。

本次未修改算法、坐标公式、八轮 Curve 公式、`ap_fixed<16,2,AP_RND,AP_SAT>`、两行缓存或性能 pragma。未运行全分辨率 RTL 仿真、联合 RTL top、Vivado Block Design / Implementation、PS/DDR 软件、KV260 板上测试；未连接 CNN，未做新位宽实验或性能优化。

## 2. 基线与环境

| 项目 | 实际信息 |
| --- | --- |
| Git 分支 | `codex/curve-fp32-baseline` |
| 本次开始及报告时 HEAD | `5f00c858a61b6ee1fa4abdb3283ceeefa2a33a00` |
| 原有模块 | `fpga/hls/curve_image_fixed16/`、`fpga/hls/bilinear_fixed16_buffered/`；原文件未修改 |
| 工具 | Vitis HLS 2025.2，Build 6295257（综合报告所载） |
| 环境脚本 | `E:\Xilinx\2025.2\data\settings64.bat` |
| RTL 仿真器 / 语言 | xsim / Verilog；VHDL 未运行（报告为 NA） |
| 目标器件 | `xck26-sfvc784-2LV-c` |
| HLS 时钟目标 | 10.00 ns / 100 MHz；综合估计 7.300 ns，仅 HLS 估计 |
| 固定点格式 | 所有对外样本与输出均为 `ap_fixed<16,2,AP_RND,AP_SAT>`；LSB = 2^-14 |

原先的全图 CSim、C Synthesis 和软件 reference 比对结果仍见 `curve_fixed16_baseline.md`、`bilinear_fixed16_buffered.md`。本报告的零差异是**小尺寸 C 模型 vs RTL**，并非全图输出 vs FP32 reference 的误差。

## 3. 输入、Testbench 与接口

### Curve

`curve_tb.cpp` 从 `outputs/zero_dce_pp/curve_fp32_raw/model_input.f32` 与 `parameters_fullres.f32` 读取各 2,747,520 个 `float32`，按相同索引均匀抽取 448 对真实元素并量化为 Fixed16；再加入 8 对边界/中间值（`x=0`、`1`、`0.125`、`0.25`、`0.5`、`0.75`、`0.875`、`0.9999`，A 在约 -0.35 到 -0.05）和 56 对固定种子 LCG 随机值。共 512 对，单次调用现有 `curve_image_fixed16(input, parameter, output, 512)`。对照的是该调用产生的 C 模型 golden，不在 Testbench 中重写 Curve。

原始 raw 对应参考数组的全图布局为 NCHW `[1,3,720,1272]`；本次 Curve 输入仅为一维配对抽样。抽样覆盖数据位置和特殊值，不保证穷尽所有 Fixed16 输入组合。

### Bilinear

`bilinear_tb.cpp` 构造 `[1,3,3,4]` NCHW 的 36 个不同空间位置 Fixed16 输入，数值由 `-0.35 + 0.06*c + 0.04*y + 0.03*x + 0.005*((x+y)&1)` 生成并量化，范围接近当前参数图的实际取值。单次调用现有 `bilinear_fixed16_buffered(input, output, 3, 4)`，按 scale factor 12 输出 `[1,3,36,48]`，共 `3×36×48 = 5,184` 个值。四角与内部位置均参与 C/RTL 全量比较，Testbench 另检查三通道的 12 个角点。实际算法仍按 `align_corners=True` 的 `oy*(Hi-1)/(Ho-1)`、`ox*(Wi-1)/(Wo-1)` 坐标规则执行；测试代码没有重写插值计算。

这组 Bilinear 输入是合成小图，不是完整 `parameters_lowres` reference。此次测试目标是 RTL 与当前 C 模型的一致性，不重新测量全分辨率 FP32 reference 误差。

### 仿真专用 depth 处理

最初直接使用原模块源码进行 Co-sim，Vitis 分别报：

```text
ERROR: A depth specification is required for interface port 'input_r' for cosimulation.
ERROR: A depth specification is required for interface port 'parameters_lowres' for cosimulation.
```

错误分别保留在 `E:\HLS\fpga_curve_fixed16_cosim\fpga_curve_fixed16_cosim\logs\hls_run_cosim_30788.backup.log` 与 `E:\HLS\fpga_bilinear_fixed16_cosim\fpga_bilinear_fixed16_cosim\logs\hls_run_cosim_47800.backup.log`。尝试只在 HLS 配置中加入 `syn.directive.interface=depth=...` 后仍出现相同错误；现有源码的接口 pragma 未被该设置有效覆盖，因此最终配置移除了这些无效 directive。

为保持已验证 baseline 原样，`fpga/hls/fixed16_rtl_cosim/` 中建立**仅用于 Co-sim 的源码副本**。通过 `git diff --no-index` 对比确认：头文件与原版相同；CPP 只有说明注释和 m_axi pragma 的 `depth` 属性不同，计算、接口 bundle、缓存和其他 pragma 完全相同：

| 顶层 | 仿真专用 `m_axi` depth | 作用 |
| --- | --- | --- |
| Curve | `input=512`、`parameter=512`、`output=512` | 配置一次 512 元素事务的 Co-sim memory adapter |
| Bilinear | `parameters_lowres=36`、`parameters_fullres=5184` | 配置小图输入和放大输出的 Co-sim memory adapter |

`depth` 是本次小样本验证适配器所需的指针容量声明；此副本不是可直接用于全分辨率 Co-sim 的配置。独立副本参与了本次 RTL 生成，因此本次 PASS 严格对应这些副本。综合资源与原 baseline 相同，未见计算硬件变化；未来若对原版进行全图 Co-sim，须按其测试容量另配 depth，而不是复用 512/5184。

首次 Curve Co-sim 还因 Testbench 使用 `std::filesystem` 无法通过 Co-sim 编译器而失败：`error: no member named 'filesystem' in namespace 'std'`。原始日志为 `...\hls_run_cosim_44024.backup.log`。仅将 Testbench 的 raw 文件读取改为 `fopen/fread/fgetc`，没有改动顶层算法。

## 4. 新增文件与实际命令

| 文件 | 用途 |
| --- | --- |
| `fpga/hls/fixed16_rtl_cosim/curve_tb.cpp` | Curve 的 512 样本 C/RTL 共同 Testbench |
| `fpga/hls/fixed16_rtl_cosim/bilinear_tb.cpp` | Bilinear 的 3×3×4 小图 Testbench |
| `fpga/hls/fixed16_rtl_cosim/curve_image_fixed16.cpp/.hpp` | Curve Co-sim-only 源码副本，仅增加指针 depth |
| `fpga/hls/fixed16_rtl_cosim/bilinear_fixed16_buffered.cpp/.hpp` | Bilinear Co-sim-only 源码副本，仅增加指针 depth |
| `fpga/hls/fixed16_rtl_cosim/curve_hls_config.cfg` | 独立 Curve HLS Component 配置 |
| `fpga/hls/fixed16_rtl_cosim/bilinear_hls_config.cfg` | 独立 Bilinear HLS Component 配置 |
| `fpga/hls/fixed16_rtl_cosim/verify_outputs.py` | 读取 Vitis C/RTL 输出向量、逐个比较 16-bit 值 |
| `fpga/scripts/curve_fixed16_cosim.cmd` | 加载工具环境，依次运行 CSim、C Synthesis、RTL Co-sim |
| `fpga/scripts/bilinear_fixed16_buffered_cosim.cmd` | 同上，针对 Bilinear |
| `fpga/reports/fixed16_rtl_cosim.md` | 本报告 |

从仓库根目录实际运行的入口命令（在解决上文错误后各完成一次最终成功运行）：

```powershell
cmd /c fpga\scripts\curve_fixed16_cosim.cmd
cmd /c fpga\scripts\bilinear_fixed16_buffered_cosim.cmd
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' fpga/hls/fixed16_rtl_cosim/verify_outputs.py E:/HLS/fpga_curve_fixed16_cosim/fpga_curve_fixed16_cosim/hls/sim/tv curve_image_fixed16 512
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' fpga/hls/fixed16_rtl_cosim/verify_outputs.py E:/HLS/fpga_bilinear_fixed16_cosim/fpga_bilinear_fixed16_cosim/hls/sim/tv bilinear_fixed16_buffered 5184
```

两个 CMD 均实际加载 `E:\Xilinx\2025.2\data\settings64.bat`，随后调用 `vitis-run.bat --mode hls --csim`、`v++.bat -c --mode hls`、`vitis-run.bat --mode hls --cosim`，分别使用上述 `.cfg` 和 `E:\HLS\fpga_curve_fixed16_cosim` / `E:\HLS\fpga_bilinear_fixed16_cosim` 独立工作目录。Vitis 在早期 Co-sim 失败时仍曾返回进程退出码 0，因此最终脚本增加了从当前 `hls_run_cosim.log` 查找明确 PASS 行的检查；该检查已对两份最终日志分别试运行通过。完整 CSim、综合和 Co-sim 的最终成功运行发生在此检查加入之前，最终结果同时由 `.rpt` 和原始输出向量确认。

本次实际运行的是普通 HLS C Simulation、C Synthesis 与 Verilog RTL Co-simulation；Vivado Implementation 和板上测试未运行。

## 5. C 模型 vs RTL 数值结果

| 模块 | RTL Co-sim | CSim | 比较输出数 | 原始 16-bit 不同数 | max absolute difference | mean absolute difference | bit-exact |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Curve Fixed16 | PASS | 0 errors | 512 | 0 | 0 | 0 | 是，C/RTL 向量逐字节相同 |
| Bilinear Fixed16 Buffered | PASS | 0 errors | 5,184 | 0 | 0 | 0 | 是，C/RTL 向量逐字节相同 |

比较脚本检查 Vitis `cdatafile` 和 `rtldatafile` 的单事务数据长度与头部，再将每个输出按 little-endian signed int16 解析。差值除以 16,384 转为实际 Fixed16 数值。两项输出都显示 `mismatches=0`、`max_abs_difference=0`、`mean_abs_difference=0`。本次没有另设 FP32 reference 容差；这里的 PASS 来自 Vitis C/RTL Co-sim 及 bit-exact 核对。Fixed16 类型本身不表示 NaN/Inf；转换成 double 后，两个 C 模型 Testbench 的非有限计数均为 0。

Curve C 模型样本输出 `min=0`、`max=1`，Fixed16 表示边界计数为 0。Bilinear C 模型输出 `min=-0.349975586`、`max=-0.0549926758`，12/12 角点精确保留。由于所有 RTL 输出 bit-exact，这些角点和范围也适用于本次 RTL 输出。

### Bilinear 三通道角点核对

下表是量化后的输入角点值；C 输出与对应输入完全相同，RTL 输出又与 C 逐位相同。

| Channel | `(0,0)` | `(0,47)` | `(35,0)` | `(35,47)` |
| ---: | ---: | ---: | ---: | ---: |
| 0 | -0.349975586 | -0.255004883 | -0.270019531 | -0.174987793 |
| 1 | -0.289978027 | -0.195007324 | -0.210021973 | -0.114990234 |
| 2 | -0.229980469 | -0.135009766 | -0.150024414 | -0.0549926758 |

## 6. RTL 周期、综合估计与缓存检查

| 指标 | Curve Fixed16 | Bilinear Fixed16 Buffered |
| --- | ---: | ---: |
| Co-sim 顶层单事务 latency（cycle） | 620 | 8,537 |
| Co-sim Total Execution Time（cycle） | 620 | 8,537 |
| Co-sim 顶层 transaction interval | NA / unknown；仅一次事务 | NA / unknown；仅一次事务 |
| HLS 目标 / 估计时钟 | 10.00 / 7.300 ns | 10.00 / 7.300 ns |
| DSP / LUT / FF | 24 / 4,902 / 3,916 | 33 / 7,985 / 5,470 |
| BRAM_18K / URAM | 4 / 0 | 4 / 0 |
| HLS 顶层静态 latency | ?，`count` 为运行时参数 | ?，H/W 为运行时参数 |
| 关键循环 | pixel loop `VITIS_LOOP_25_1`：iteration latency 49，target/achieved II 1/1，trip count ? | row loader `VITIS_LOOP_64_3`：iteration latency 12，target/achieved II 1/2；另一 loader `VITIS_LOOP_72_4`：3，1/1；output pixel `VITIS_LOOP_85_5`：5，1/1 |

上述资源/时钟/循环是为此次 Co-sim 生成 RTL 时实际运行的 **HLS C Synthesis 估计**，并非 Vivado Implementation 或板上数据。Vitis 报告明确提示：只有超过一个顶层事务才可测量 transaction interval；本次每模块一次调用，所以报告为 NA，`result.transaction.rpt` 的单条 `interval=0` 不作为吞吐结论。Curve 与 Bilinear 的整图静态总延迟因运行时参数而为 `?`，本次小样本 Co-sim 分别给出了该测试事务的实际仿真周期。

Bilinear 综合报告中 `row_a_U`、`row_b_U` 分别映射为 `RAM_2P_BRAM_1R1W`，各占 1 个 BRAM_18K；其余 BRAM 用于接口等。小图 RTL 仿真成功读取、切换缓存并写出全部 5,184 个结果；日志未发现 RAM port conflict、地址越界、行缓存切换或 AXI memory transaction 错误。这个结论只覆盖本次 `3×4 → 36×48` 的输入，不等于所有尺寸、所有 AXI 系统场景已验证。

## 7. Warning 与失败排查记录

| 来源 | 实际信息 | 本次处理 / 解释 |
| --- | --- | --- |
| 早期 Curve Co-sim TB 编译 | `no member named 'filesystem' in namespace 'std'` | 仅改 Testbench raw 读取实现，之后 CSim 与 Co-sim 通过 |
| 早期原接口 Co-sim | `A depth specification is required for interface port 'input_r' ...`；Bilinear 为 `parameters_lowres` | 在独立仿真副本的 m_axi pragma 增加测试容量对应 depth，原基线不动 |
| Curve Co-sim | `[HLS 200-626] This design is unable to schedule all read ports in the first II cycle. The RTL testbench may treat the design as non-pipelined` | Co-sim 最终 PASS；保留警告，不据此声称事务吞吐 |
| Bilinear C Synthesis | `[HLS 200-448] Lower bound of II is 2 due to multiple bus read operation ... on port 'gmem_input'` | 指向 row loader 的两次外部读；其 achieved II=2，output pixel loop 仍为 II=1；不是本地 BRAM port conflict |
| Bilinear RTL 生成 | 多条 `[RTGEN 206-101] Setting dangling out port ... to 0`，涉及子模块 AXI 引脚；并有 AXI reset 同步低有效警告 | 如实保留；本次 RTL Co-sim PASS，尚无 Vivado/板级验证 |
| 两个 xsim 仿真 | `[XSIM 43-4099]` UVM package timescale 警告 | 两项 Co-sim 均 PASS |
| 两个 Co-sim | `[COSIM 212-211] II is measurable only when transaction number is greater than 1 ...` | 顶层 interval 报告为 NA |

未发现最终成功运行中的 fatal error。早期失败日志仍留在各独立 `E:\HLS` 工作目录，便于复查。合成报告中的 warning 不因本次数值 PASS 而被视为已解决。

## 8. 结论与审核建议

本次在 xsim/Verilog 下，Curve 512 个输出和 Bilinear 5,184 个输出均与当前 Fixed16 C/HLS golden **bit-exact**，两项 Vitis HLS RTL Co-simulation 均 PASS。小图上未观察到两行 BRAM 缓存切换或 AXI 事务造成的数值错误。当前两个模块可以作为进入下一阶段 Vivado 集成**评审**的候选基线；本报告不代表全分辨率 RTL、联合 RTL、Vivado Implementation、PS/DDR 或 KV260 板上行为已经通过。

下一步仅建议 Master 审核仿真专用 depth 的处理方式、现存 AXI/II 警告和测试覆盖范围，再决定是否进入 Vivado 集成。本次不继续实施集成，不 commit，不 push。

建议 Commit Message（仅供审核，未执行提交）：`test(fpga): add Fixed16 Curve and Bilinear RTL co-simulation harnesses`。报告完成时仍在 `codex/curve-fp32-baseline`；本次文件均为新增未跟踪文件，原 baseline 无修改。

## 9. 结果位置

- Curve Co-sim：`E:\HLS\fpga_curve_fixed16_cosim\fpga_curve_fixed16_cosim\hls\sim\report\curve_image_fixed16_cosim.rpt`
- Bilinear Co-sim：`E:\HLS\fpga_bilinear_fixed16_cosim\fpga_bilinear_fixed16_cosim\hls\sim\report\bilinear_fixed16_buffered_cosim.rpt`
- 对应 CSim：各工作目录 `hls\csim\report\*_csim.log`
- 对应 HLS C Synthesis：各工作目录 `hls\syn\report\*_csynth.rpt`
- C/RTL 输出向量：各工作目录 `hls\sim\tv\cdatafile` 与 `rtldatafile`
