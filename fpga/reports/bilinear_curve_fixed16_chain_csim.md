# Bilinear → Curve Fixed16 联合 CSim 数值验证

## 1. 目标与范围

验证现有 `bilinear_fixed16_buffered` 产生的全分辨率 Fixed16 参数图，能否**不经 float 中转或再次量化**，直接作为现有 `curve_image_fixed16` 的 parameter 输入；统计 Bilinear 中间误差、Curve 既有独立基线误差、联合链最终误差，以及两条 Curve 路径的输出差异。本任务只运行联合 Vitis HLS C Simulation，没有新建可综合的联合 top、修改两模块算法、改变位宽或做性能优化；没有 C Synthesis、RTL Co-simulation、Vivado Block Design/Implementation、AXI Stream、DDR 性能/板上测试或 CNN 集成，也没有 commit、push。

## 2. 版本、数据和类型

- Git 分支 `codex/curve-fp32-baseline`；本次报告时 HEAD `1587c57ec40b1271ccbbdc20da05ae0051d78d4f`。本次仅新增 harness、CSim 配置/脚本与报告，现有 Bilinear/Curve 源码未改。
- Vitis HLS 2025.2，Build 6295257；环境脚本 `E:\Xilinx\2025.2\data\settings64.bat`。CSim 配置沿用 `xck26-sfvc784-2LV-c` 与 Vivado IP flow；本次**未综合**，因此没有新的资源、时钟、II 或硬件延迟结果。
- 软件 reference 及 `outputs/zero_dce_pp/reference/metadata.json` 记录的布局均为 FP32 NCHW、batch=1、channels=3：`parameters_lowres.npy` 为 `[1,3,60,106]`、19,080 元素；`parameters_fullres.npy`、`model_input.npy`、`enhanced.npy` 均为 `[1,3,720,1272]`、各 2,747,520 元素。
- Testbench 实际读取现有 raw：`outputs/zero_dce_pp/bilinear_fp32_raw/parameters_lowres.f32`、`parameters_fullres.f32`，以及 `outputs/zero_dce_pp/curve_fp32_raw/model_input.f32`、`enhanced.f32`；根据文件字节数校验全部元素数。两套 raw 目录中的 `parameters_fullres.f32` SHA-256 相同，均为 `DE927D687216F00A93D0A99136762E3CEA2A590046DEC40E24FA1386B2AFC8D9`，因此 B 路径使用的是既有 Curve Fixed16 基线的同一 FP32 参数真值。HLS 不解析 `.npy`，本次没有重生 reference。
- Bilinear 的 `bilinear_fixed16_t` 与 Curve 的 `curve_fixed16_t` 均为 `ap_fixed<16,2,AP_RND,AP_SAT>`，即 16 bit 总宽、2 bit 整数位（含符号）、14 bit 小数位；步长 `2^-14=0.00006103515625`，范围 `[-2,2-2^-14]`。联合 Testbench 用 `static_assert(std::is_same<...>)` 编译期检查类型一致。Bilinear 中间数组有 2,747,520 个元素，Curve parameter 输入也使用同一数量。

## 3. 新增文件与调用路径

| 文件 | 作用 |
|---|---|
| `fpga/hls/bilinear_curve_fixed16_chain/tb_bilinear_curve_fixed16_chain.cpp` | 独立联合 Testbench，读取四份 raw，量化输入并依次调用现有两个模块，统计 A/B/C/D。 |
| `fpga/hls/bilinear_curve_fixed16_chain/hls_config.cfg` | 仅用于 CSim 的独立 Component；包含两个**现有** `.cpp`，`syn.top` 指向现有 `bilinear_fixed16_buffered`，没有新联合 HLS top。 |
| `fpga/scripts/bilinear_curve_fixed16_chain_csim.cmd` | 加载 Vitis 2025.2 并运行联合 CSim。 |
| `fpga/reports/bilinear_curve_fixed16_chain_csim.md` | 本报告。 |

Testbench 先把 FP32 `parameters_lowres` 显式转为 `bilinear_fixed16_t`，调用现有 `bilinear_fixed16_buffered()`，得到 host memory 中的 `std::vector<bilinear_fixed16_t> generated_full_fixed`。`model_input` FP32 另行显式转为 `curve_fixed16_t`。真正联合路径直接执行：

```cpp
curve_image_fixed16(model_fixed.data(), generated_full_fixed.data(),
                    chain_output.data(), full_count);
```

这里 `generated_full_fixed.data()` 直接连接 Curve 的 `const curve_fixed16_t* parameter`；没有 Fixed16 → float → Fixed16。作为 B 对照，Testbench 还把 FP32 `parameters_fullres` **直接**量化为 `curve_fixed16_t`，使用相同的 `model_fixed` 调用同一个 Curve 模块。没有在 Testbench 重写任何 Bilinear 或 Curve 算法。

## 4. 实际执行及 CSim 状态

在 `E:\github\-` 实际执行：

```powershell
cmd /c fpga\scripts\bilinear_curve_fixed16_chain_csim.cmd
$a=(Get-FileHash -Algorithm SHA256 'outputs/zero_dce_pp/bilinear_fp32_raw/parameters_fullres.f32').Hash; $b=(Get-FileHash -Algorithm SHA256 'outputs/zero_dce_pp/curve_fp32_raw/parameters_fullres.f32').Hash; Write-Output "same_fullres_raw=$($a -eq $b) sha256=$a"
```

脚本先调用 `E:\Xilinx\2025.2\data\settings64.bat`，再于 `E:\HLS\fpga_bilinear_curve_fixed16_chain` 执行：

```text
E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat --mode hls --csim --config E:\github\-\fpga\hls\bilinear_curve_fixed16_chain\hls_config.cfg --work_dir fpga_bilinear_curve_fixed16_chain
```

命令退出码 0。Vitis CSim 日志 `E:\HLS\fpga_bilinear_curve_fixed16_chain\fpga_bilinear_curve_fixed16_chain\hls\csim\report\bilinear_fixed16_buffered_csim.log` 列出联合 Testbench 以及现有 `bilinear_fixed16_buffered.cpp`、`curve_image_fixed16.cpp` 均被编译，末尾为 **`CSim done with 0 errors`**。日志以现有 `syn.top` 命名，不能误读为只运行了 Bilinear：Testbench 的 A/B/C/D 输出证明本次实际顺序调用了两个函数。

四份 FP32 reference 的 NaN/Inf 均为 0。量化时低分辨率参数、`model_input`、直接量化的全分辨率参数超出 Fixed16 可表示范围的元素数依次为 **0 / 0 / 0**。中间参数和两条 Curve 输出的 NaN/Inf 计数均为 0；测试未设置任何新的数值验收阈值。

## 5. 四组完整数值结果

所有 max/mean 均统计整个 2,747,520 元素，`mean` 是绝对差之和除以元素总数；Fixed16 输出先转为 double **仅用于统计**。

| 组别 / 对照 | max absolute error / difference | mean absolute error / difference | 说明 |
|---|---:|---:|---|
| **A. Bilinear 中间 `generated_full_fixed` vs FP32 `parameters_fullres`** | **`6.0498714447e-05`** | **`1.75228651079e-05`** | 与此前 Bilinear Fixed16 buffered 独立 CSim 的两项结果逐位打印一致。中间数组边界值计数 0。 |
| **B. Curve 直接量化 FP32 参数 vs FP32 `enhanced`** | **`0.000706814229488`** | **`7.45493943104e-05`** | 复现已有 Curve Fixed16 baseline（先前报告分别约 `0.000706814229`、`0.0000745493943`）。该路径输出边界值计数 0。 |
| **C. 真实 Bilinear → Curve 联合输出 vs FP32 `enhanced`** | **`0.000711549073458`** | **`7.63478037805e-05`** | 本任务最终整链结果；输出 min/max=`0 / 1`，NaN/Inf=0，Fixed16 上下饱和边界值计数=0。 |
| **D. 联合输出 vs B 的 Curve 输出** | **`0.0008544921875`** | **`1.37127170523e-05`** | 单独观察 Bilinear 实际参数与直接量化参考参数在八轮 Curve 后造成的输出差异。 |

另有 **437,974** 个中间 Fixed16 参数元素不同于“直接量化 FP32 `parameters_fullres`”的对应元素。C 相比 B 的整图 max absolute error 高约 `4.73484397e-06`，mean absolute error 高约 `1.7984094701e-06`；这些是各自相对 FP32 reference 的指标变化。D 的 max/mean 是两条 Curve 输出之间的逐元素差异，**不能等同于**对 reference 的误差增量：最大差异与最大 reference 误差可能出现在不同位置，也可能有符号抵消。上述结果只适用于当前 reference 与既有 Fixed16 算法，未推断其他图像的误差上界。

## 6. Warning、结论与后续

CSim 编译时，AMD/Xilinx 自带 `gmp.h` 与 `floating_point_v7_1_bitacc_cmodel.h` 报 `__GMP_LIBGMP_DLL` macro redefined warning；不涉及本次模块源码，CSim 仍 0 errors。没有观察到输入越界、NaN/Inf 或输出落在 Fixed16 饱和边界。由于本次没有 C Synthesis，不能填写联合 top 的 DSP/LUT/FF/BRAM/URAM、Clock、II、Latency、Trip Count；RTL/板上数值和性能也均未验证。

**结论：**两个现有模块的外部 Fixed16 类型可以直接连接；真实 Bilinear → Curve 非 CNN 数值链在当前 2,747,520 元素上对 FP32 `enhanced` 的 **max absolute error=`0.000711549073458`、mean absolute error=`7.63478037805e-05`**。Bilinear 中间结果与 Curve 独立基线均已在同一 harness 复现，联合链可以保留作为数值接口兼容性验证结果。是否满足项目精度要求须由 Master 根据后续口径判断，本次不自行设门限或继续实施硬件集成。

建议 Commit Message（仅供审核，本次未提交）：`fpga: add Fixed16 bilinear-to-curve chain CSim harness`

工作区状态：`codex/curve-fp32-baseline`，本次仅上述新文件为未跟踪状态，两个已验证模块源码及其原 Testbench 未改；没有 `git add`、commit 或 push。
