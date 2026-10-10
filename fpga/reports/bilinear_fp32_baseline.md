# Bilinear FP32 HLS baseline 报告

## 1. 任务目标与范围

依据 `fpga/reports/bilinear_coordinate_oracle.md`，新增独立 Bilinear FP32 HLS 顶层 `bilinear_fp32`：batch=1、channels=3、NCHW、`scale_factor=12`，从低分辨率参数图生成全分辨率参数图。用当前 reference 完整测试 2,747,520 个输出元素，先运行 Vitis HLS C Simulation，正确后运行 C Synthesis，记录首版数值和资源/时序估计。

本次没有修改 Curve 代码；没有定点化，也没有添加 PIPELINE、UNROLL、ARRAY_PARTITION 等性能 pragma。没有运行 RTL Co-simulation、Vivado Implementation、KV260 板上测试或实际 DDR 带宽测试；没有 commit 或 push。

## 2. 基线、版本与输入数据

- Git 分支：`codex/curve-fp32-baseline`。任务开始时 HEAD 为 `6bdceba`；报告整理时 HEAD 为 `629bb1b`，期间已有其他工作区提交发生，本次没有执行任何 Git 提交、切换或推送。
- 工具：Vitis HLS 2025.2（Build 6295257），环境入口 `E:\Xilinx\2025.2\data\settings64.bat`。目标器件 `xck26-sfvc784-2LV-c`，Vivado IP flow；综合报告 Target Clock 为 10.00 ns，即 100 MHz。
- 软件语义来源：`fpga/reports/bilinear_coordinate_oracle.md`；对应 reference 元数据 `outputs/zero_dce_pp/reference/metadata.json` 记录 PyTorch `2.14.0+cpu`、CPU、FP32、NCHW、倍率 12。
- 真值：`outputs/zero_dce_pp/reference/parameters_lowres.npy`：`[1,3,60,106]`、19,080 个 FP32 元素；`parameters_fullres.npy`：`[1,3,720,1272]`、2,747,520 个 FP32 元素。两者布局均为 NCHW。
- HLS Testbench 实际读取从上述 `.npy` 校验并转换出的 `outputs/zero_dce_pp/bilinear_fp32_raw/parameters_lowres.f32`（76,320 字节）与 `parameters_fullres.f32`（10,990,080 字节）。转换工具同时保存忽略 Git 的 `manifest.json`，记录 source、shape、layout、dtype 与元素数；HLS 顶层不解析 `.npy`。

## 3. 修改内容与设计

| 新增文件 | 用途 |
|---|---|
| `fpga/hls/bilinear_fp32/bilinear_fp32.hpp` | 独立顶层签名：`const float* parameters_lowres`、`float* parameters_fullres`、输入 H/W。 |
| `fpga/hls/bilinear_fp32/bilinear_fp32.cpp` | 三通道 NCHW FP32 双线性加权计算；两路 m_axi、H/W 与控制 AXI4-Lite。 |
| `fpga/hls/bilinear_fp32/tb_bilinear_fp32.cpp` | 一次调用处理完整参数图，计算误差、非有限值和四角点。 |
| `fpga/hls/bilinear_fp32/export_raw.py` | 校验 `.npy` 和 metadata，转换为小端、连续 NCHW float32 raw。 |
| `fpga/hls/bilinear_fp32/hls_config.cfg` | 独立 Vitis HLS component 配置，top 为 `bilinear_fp32`。 |
| `fpga/scripts/bilinear_fp32_csim.cmd`、`bilinear_fp32_synth.cmd` | 使用 Vitis 2025.2 CLI 的独立 CSim / C Synthesis 入口。 |
| `fpga/reports/bilinear_fp32_baseline.md` | 本报告。 |

输入 H/W 为运行时 `unsigned int`，输出 `Ho=Hi×12`、`Wo=Wi×12`，一次调用逐通道、逐输出行、逐输出列写满 NCHW 输出。当前 V1 输入为 `Hi=60`、`Wi=106`，输出为 `Ho=720`、`Wo=1272`。零尺寸输入直接返回；未为超出 V1 范围的大尺寸整数溢出或缓冲区容量作独立验证。

```text
sy = 0 if Ho == 1 else oy * (Hi-1) / (Ho-1)
sx = 0 if Wo == 1 else ox * (Wi-1) / (Wo-1)
y0 = floor(sy),  y1 = min(y0+1, Hi-1),  wy = sy-y0
x0 = floor(sx),  x1 = min(x0+1, Wi-1),  wx = sx-x0
out = (1-wy) * ((1-wx)*I[y0,x0] + wx*I[y0,x1])
    + wy * ((1-wx)*I[y1,x0] + wx*I[y1,x1])
```

源码预先按 FP32 计算 `(Hi−1)/(Ho−1)` 与 `(Wi−1)/(Wo−1)`，每个输出索引再乘此比例；与 `align_corners=True` 的端点映射一致。源坐标非负，因此转换为无符号整数等同于 `floor`；右/下边界将第二邻居限制在最后一个有效输入点。代码未使用 `oy/12` 或 `ox/12` 替代。输入和输出分别位于 `gmem_input`、`gmem_output` AXI4 Memory-Mapped bundle（报告均为 32 bit 数据）；两个基地址、`input_height`、`input_width` 和控制在 `control` AXI4-Lite。

## 4. 实际执行与 C Simulation

在 `E:\github\-` 实际运行：

```powershell
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' fpga\hls\bilinear_fp32\export_raw.py outputs\zero_dce_pp\reference outputs\zero_dce_pp\bilinear_fp32_raw
cmd /c fpga\scripts\bilinear_fp32_csim.cmd
cmd /c fpga\scripts\bilinear_fp32_synth.cmd
```

两个 `.cmd` 先调用 `settings64.bat`，随后分别调用 `E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat --mode hls --csim --config E:\github\-\fpga\hls\bilinear_fp32\hls_config.cfg --work_dir fpga_bilinear_fp32` 与 `E:\Xilinx\2025.2\Vitis\bin\v++.bat -c --mode hls --config E:\github\-\fpga\hls\bilinear_fp32\hls_config.cfg --work_dir fpga_bilinear_fp32`，工作目录 `E:\HLS\fpga_bilinear_fp32`。三项命令退出码均为 0。

Vitis HLS CSim 日志 `E:\HLS\fpga_bilinear_fp32\fpga_bilinear_fp32\hls\csim\report\bilinear_fp32_csim.log` 显示 **`CSim done with 0 errors`**，Testbench 数值检查 **PASS**：

| 指标 | 实际结果 |
|---|---:|
| 输出 shape | `[1,3,720,1272]` |
| 输出元素数量 | 2,747,520 |
| max absolute error vs `parameters_fullres` | **0** |
| mean absolute error vs `parameters_fullres` | **0** |
| Testbench FP32 容差 | `1e-6`（沿用既有 FP32 Curve Testbench 口径） |
| 输入 NaN/Inf | 0 |
| reference NaN/Inf | 0 |
| HLS 输出 NaN/Inf | 0 |
| 三通道四角输出等于低分辨率输入 | **12/12，逐值精确相等** |
| 四角最大绝对误差 vs 输入 / reference | `0 / 0` |

本次单独模块的 CSim 与已保存的 `parameters_fullres` reference 在全部元素上完全一致。该结论是 C++/HLS C Simulation 数值结果，不是 RTL 或板卡结果。

## 5. C Synthesis 结果

Vitis HLS C Synthesis 成功，Vivado IP 导出成功。原始报告：`E:\HLS\fpga_bilinear_fp32\fpga_bilinear_fp32\hls\syn\report\bilinear_fp32_csynth.rpt`、对应 pipeline 子模块报告和 `csynth.rpt`。资源取顶层详细 `Utilization Estimates / Total` 行，是 HLS 估计值，非实现后实占。

| 指标 | 结果 |
|---|---:|
| DSP | **25** |
| LUT | **7060** |
| FF | **5396** |
| BRAM_18K | **2** |
| URAM | **0** |
| Target Clock | **10.00 ns** |
| Estimated Clock | **7.300 ns** |

`csynth.rpt` 的模块汇总 LUT 为 7062，比顶层详细 Total 的 7060 多 2；上表统一采用详细 Total 口径。报告列出一个由综合器生成的 `bilinear_fp32_Pipeline_VITIS_LOOP_26_1_VITIS_LOOP_27_2_VITIS_LOOP_35_3` 子模块（该子模块估计 DSP 18、LUT 4741、FF 3149、BRAM 0），其余资源在顶层控制、地址和 AXI 接口等部分。

| 层级 / 循环 | Pipelined | Iteration Latency | Target II | Achieved II | Trip Count | min/max Latency |
|---|---|---:|---:|---:|---|---|
| 顶层 `bilinear_fp32` | no | unknown | unknown | unknown | unknown | `? / ?` |
| 自动生成的 pipeline 子模块 | yes | unknown | unknown | unknown | unknown | `? / ?` |
| 合并循环 `VITIS_LOOP_26_1_VITIS_LOOP_27_2_VITIS_LOOP_35_3` | yes | **48 cycles** | **1** | **4** | `?` | `? / ?` |

源码循环层级为 `channel (3)` → `oy (Ho)` → `ox (Wo)`；综合日志显示先自动 pipeline 最内层 `ox`，随后自动 flatten `oy` 与 `channel` 两层，形成上表的合并循环。未见循环自动 unroll 的日志或独立 unroll 结果，源码也没有性能 pragma。`Hi/W` 为运行时参数，综合报告未给出静态 Trip Count 或顶层/合并循环总 Latency，因此保持 `?`；不能把 CSim 的固定测试尺寸当作综合时固定 tripcount。pipeline 日志记录 Depth 49，详细子模块报告的 Iteration Latency 为 48 cycles；上表采用 Iteration Latency 字段。

## 6. Warning、接口访问与限制

- **II 资源限制：** `WARNING: [HLS 200-448] Lower bound of II is 4 due to multiple bus read operation ... on port 'gmem_input'`。四个邻居从同一 input m_axi master 分别读取，使自动 pipeline 的 Target II=1、Achieved II=4；这是当前 baseline 的真实综合结果，没有为改善 II 改动算法或接口。
- **输入突发访问未推断：** `csynth.rpt` 将四路 `parameters_lowres` 读取均列为 `Fail` / `214-229 Could not analyze pattern`；它们是依坐标变化的邻居读取。输出连续写入在最内层 loop 成功推断 variable length burst；外层尝试提示 `214-230 Stride is incompatible`，整体仍有输出 burst。报告中的 `Widen Fail` / `214-353` 源于 `max_widen_bitwidth` threshold 为 0，未进行接口自动加宽。C Synthesis 没有报数组索引地址被忽略。
- **AXI 复位：** `WARNING: [RTGEN 206-101] Design contains AXI ports. Reset is fixed to synchronous and active low.`。
- **Windows IP 名称：** IP 导出时五条 `IP_Flow 19-4832` 提示生成的子 IP 名较长，Windows 路径长度可能构成问题；本次 IP 已成功导出。
- 未做 RTL Co-simulation、Vivado Implementation、KV260 板上验证或 DDR 带宽测量。II=4 和 7.300 ns 都是 HLS 综合估计，不等于已验证的系统吞吐或上板时钟。

## 7. 对照、结论与审核状态

本次是第一版 Bilinear HLS baseline，没有既有 Bilinear HLS 资源可作同类版本对比。软件 oracle 已确认的 `align_corners=True` 端点映射在本次 HLS CSim 中得到全图 **max/mean absolute error 均为 0**，比此前软件重建 oracle 对保存 reference 的约 `10^-7` 量级差异更小；具体运行路径差别本次未另作归因。当前 baseline 值得保留作后续接口和性能实验的对照，但 II=4、输入突发未推断与整图延迟 unknown 都需要在后续阶段单独评估，当前不做优化。

本次新增 `fpga/hls/bilinear_fp32/`、两个 Bilinear `.cmd` 与本报告；此前工作区中 Fixed14/Fixed12 sweep 与 Bilinear 软件规范的未跟踪文件保持原样。建议供审核的 Commit Message：`feat(fpga): add bilinear fp32 axi baseline`，仅为建议。本次没有 `git add`、commit 或 push；停止等待 Master 审核。
