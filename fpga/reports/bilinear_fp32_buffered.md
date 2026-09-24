# Bilinear FP32 两行缓存实验报告

## 1. 目标与范围

在已验证的 `bilinear_fp32` AXI baseline 之外，新建 `bilinear_fp32_buffered`，用两条片上 source row 缓存减少输出像素循环对同一 `gmem_input` 的四邻居 DDR 读取，尝试将该循环的 Achieved II 从 4 降到 1。保持 batch=1、三通道 NCHW、FP32、`scale_factor=12`、`align_corners=True` 的插值公式和现有 AXI 接口。

本次没有修改原始 Bilinear 或 Curve 代码，没有定点化、RGB 并行或数学改写，没有运行 RTL Co-simulation、Vivado Implementation、KV260 板上测试或 DDR 带宽实测，也没有 commit 或 push。

## 2. 基线、工具和数据

- 分支：`codex/curve-fp32-baseline`；本次开始及报告时 HEAD：`dce4bafb78683626aa368c16eaa8f66e03e423dd`。本次文件均未提交。
- 原始 baseline 与记录：`fpga/hls/bilinear_fp32/`、`fpga/reports/bilinear_fp32_baseline.md`。
- Vitis HLS 2025.2，Build 6295257；环境脚本 `E:\Xilinx\2025.2\data\settings64.bat`；Vivado IP flow；目标器件 `xck26-sfvc784-2LV-c`；100 MHz 目标时钟。
- 软件 reference：`outputs/zero_dce_pp/reference/parameters_lowres.npy`，FP32、NCHW `[1,3,60,106]`、19,080 元素；`parameters_fullres.npy`，FP32、NCHW `[1,3,720,1272]`、2,747,520 元素。Testbench 实际读取先前由 reference 转换出的 `outputs/zero_dce_pp/bilinear_fp32_raw/parameters_lowres.f32` 和 `parameters_fullres.f32`，分别为 76,320 和 10,990,080 字节。`.npy` 不由 HLS 解析；本次没有重新生成 reference。

## 3. 新增文件与设计

| 新增文件 | 作用 |
|---|---|
| `fpga/hls/bilinear_fp32_buffered/bilinear_fp32_buffered.hpp` | 独立顶层声明。 |
| `fpga/hls/bilinear_fp32_buffered/bilinear_fp32_buffered.cpp` | 两行缓存、通道/行/像素循环、FP32 插值、AXI 接口。 |
| `fpga/hls/bilinear_fp32_buffered/tb_bilinear_fp32_buffered.cpp` | 复制 baseline Testbench 的数据与误差检查口径，仅更换顶层调用。 |
| `fpga/hls/bilinear_fp32_buffered/hls_config.cfg` | 独立 HLS Component，top 为 `bilinear_fp32_buffered`。 |
| `fpga/scripts/bilinear_fp32_buffered_csim.cmd`、`bilinear_fp32_buffered_synth.cmd` | 独立 Vitis 2025.2 CSim / C Synthesis 入口。 |
| `fpga/reports/bilinear_fp32_buffered.md` | 本报告。 |

顶层签名为 `bilinear_fp32_buffered(const float* parameters_lowres, float* parameters_fullres, unsigned int input_height, unsigned int input_width)`。输入与输出分别使用 `gmem_input`、`gmem_output` 的 32 bit `m_axi`；两个基地址、H/W 和控制使用 `control` AXI4-Lite。输出 H/W 为输入 H/W 的 12 倍。

坐标映射与 baseline 相同：`sy=oy*(Hi-1)/(Ho-1)`、`sx=ox*(Wi-1)/(Wo-1)`，分母对应输出尺寸减一；`y0/x0=floor`，`y1/x1` 限制到输入边界。浮点运算仍按原有次序计算 `top=(1-wx)*v00+wx*v01`、`bottom=(1-wx)*v10+wx*v11`、`out=(1-wy)*top+wy*bottom`。没有使用 `oy/12` 或 `ox/12`。

`row_a[128]`、`row_b[128]` 是当前通道的两条 source row，使用 `BIND_STORAGE type=ram_2p impl=bram`。最初装入 `y0/y1`；`y0` 前进到旧 `y1` 时，交换两条缓存的逻辑角色，只把新的 `y1` 装入空出的缓存；若下一行不在缓存中，则重新装入两条。相同 `y0/y1` 的连续输出行不再读 DDR。最下边界 `y0=y1` 时复用同一行。输出像素从片上缓存取四邻居。源码没有 PIPELINE、UNROLL、ARRAY_PARTITION pragma；3 个内层循环由 HLS 自动 pipeline。

缓存最大支持 `input_width <= 128`，当前 V1 的 106 符合。零尺寸或宽度超过 128 时顶层直接返回且不写输出；这是本实验的容量边界，超过此宽度的行为不等同于原始 baseline，尚未作为通用尺寸版本验证。两个缓存逻辑容量合计 `2×128×32=8192 bit`，综合实际使用 4 个 BRAM_18K。

## 4. 实际执行及数值正确性

在 `E:\github\-` 实际执行：

```powershell
cmd /c fpga\scripts\bilinear_fp32_buffered_csim.cmd
cmd /c fpga\scripts\bilinear_fp32_buffered_synth.cmd
& 'E:\HLS\bilinear_oracle_venv\Scripts\python.exe' -c 'import numpy as np; r=np.float32(np.float32(59)/np.float32(719)); y=np.minimum(np.arange(720,dtype=np.float32)*r,np.float32(59)).astype(np.int32); print("unique_y0",len(np.unique(y)),"transitions",np.count_nonzero(y[1:]!=y[:-1]),"first_last",int(y[0]),int(y[-1]),"row_loads_per_channel",2+max(0,np.count_nonzero(y[1:]!=y[:-1])-1))'
```

两个 `.cmd` 分别加载上述 Vitis 环境，再在 `E:\HLS\fpga_bilinear_buffered` 运行：

```text
E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat --mode hls --csim --config E:\github\-\fpga\hls\bilinear_fp32_buffered\hls_config.cfg --work_dir fpga_bilinear_buffered
E:\Xilinx\2025.2\Vitis\bin\v++.bat -c --mode hls --config E:\github\-\fpga\hls\bilinear_fp32_buffered\hls_config.cfg --work_dir fpga_bilinear_buffered
```

CSim 和 C Synthesis 命令均退出 0。CSim 日志：`E:\HLS\fpga_bilinear_buffered\fpga_bilinear_buffered\hls\csim\report\bilinear_fp32_buffered_csim.log`，显示 **`CSim done with 0 errors`**。

| 指标 | 结果 |
|---|---:|
| 输出 shape / 元素 | `[1,3,720,1272]` / 2,747,520 |
| max absolute error vs `parameters_fullres` | **0** |
| mean absolute error vs `parameters_fullres` | **0** |
| Testbench tolerance | `1e-6` |
| 输入 / reference / 输出 NaN、Inf | `0 / 0 / 0` |
| 三通道四角点与原输入精确相等 | **12/12** |
| 四角最大绝对误差 vs 输入 / reference | `0 / 0` |

Testbench 判定 PASS；本次 CSim 中全部输出与 reference 完全一致。该结果仅证明 C Simulation 数值行为。

## 5. C Synthesis 与性能

C Synthesis 和 Vivado IP 导出成功。原始顶层报告：`E:\HLS\fpga_bilinear_buffered\fpga_bilinear_buffered\hls\syn\report\bilinear_fp32_buffered_csynth.rpt`；循环子模块报告位于同一目录，日志位于 `E:\HLS\fpga_bilinear_buffered\fpga_bilinear_buffered\logs\hls_compile.log`。以下均为 HLS 估计，取顶层详细 `Utilization Estimates / Total` 行。

| 资源 / 时钟 | Buffered |
|---|---:|
| DSP | **42** |
| LUT | **8,328** |
| FF | **6,497** |
| BRAM_18K | **6** |
| URAM | **0** |
| Target Clock | **10.00 ns** |
| Estimated Clock | **7.300 ns** |

`csynth.rpt` 的模块汇总 LUT 为 8,332，比顶层详细 Total 多 4；本报告和 baseline 对比均采用顶层详细 Total 口径。BRAM 中两条缓存各 2 个，另 2 个归入 `gmem_input_m_axi` 实例。

源码/综合层级为顶层 → `channel` (`VITIS_LOOP_38_1`) → 输出行 `oy` (`VITIS_LOOP_45_2`) → 条件性的初次两行装载 (`VITIS_LOOP_54_3`) 或增量单行装载 (`VITIS_LOOP_62_4`) → 输出像素 `ox` (`VITIS_LOOP_75_5`)。HLS 将后三个内层循环各生成为 pipeline 子模块；未见 loop flatten 或 unroll 的记录。

| 顶层 / loop | Pipelined | Target II | Achieved II | Iteration Latency | Trip Count | min/max Latency (cycles) |
|---|---|---:|---:|---:|---|---|
| `bilinear_fp32_buffered` | no | unknown | unknown | unknown | unknown | `? / ?` |
| `VITIS_LOOP_38_1` channel | no | - | - | `?` | `3` | `? / ?` |
| `VITIS_LOOP_45_2` output row | no | - | - | `?` | `0 ~ 4294967292`（报告原值；运行时 H/W） | `? / ?` |
| `VITIS_LOOP_54_3` initial two-row load | yes, auto | 1 | **2** | 12 | `1 ~ ?` | `11 / ?` |
| `VITIS_LOOP_62_4` incremental one-row load | yes, auto | 1 | **1** | 3 | `1 ~ ?` | `2 / ?` |
| `VITIS_LOOP_75_5` output pixel | yes, auto | 1 | **1** | 36 | `?` | `? / ?` |

HLS 报告中的 `0 ~ 4294967292` 是运行时参数所允许的静态范围，不能当作当前图像实际 720 次输出行；两个 loader 的 `?` 和 pixel loop 的 `?` 也不能用 Testbench 尺寸替换。顶层整图 Latency/Interval 因运行时 H/W 和条件装载无法静态确定，原样保留 `?`。**核心输出像素循环 Achieved II=1**，实现本次目标；初次两行装载循环 Achieved II=2，不等于输出像素循环的 II。

## 6. AXI burst、warning 与 DDR 访问量

综合的 M_AXI Burst Information 显示：增量装载循环 `VITIS_LOOP_62_4` 推断 variable-length、32 bit input read burst；输出像素循环 `VITIS_LOOP_75_5` 推断 variable-length、32 bit output write burst。初次两行装载在源码第 55–56 行的两处 input read 未推断 burst，报告为 `214-231 Access is clobbered by load`。第 66 行单行装载在外层条件分支报告 `214-232 Access call is in the conditional branch`，其内层循环仍显示 burst `Inferred`。输出写在外层行循环报告 `214-230 Stride is incompatible`，其内层像素循环仍显示 burst `Inferred`。输入和输出均报告 `214-353` 未拓宽 AXI 位宽，维持 32 bit。

`hls_compile.log` 的主要调度 warning 为 `HLS 200-448`：初次装载循环同周期从 `gmem_input` 读取 `y0` 和 `y1` 两行，单一 AXI read 端口将该 loader 的 II 下界限制为 2。这项 warning 不发生在输出像素循环。没有看到缓存 RAM port conflict warning；`row_a/row_b` 均绑定为片上 BRAM，输出像素循环实际 II=1。IP 打包阶段另有 dangling AXI 子模块端口的 RTGEN warning 和 Windows 路径长度提示，导出仍成功。本次没有为 loader 的 II=2 额外改动，因为像素 II=1 已达成。

对当前 `60×106×3` V1 图像，源码四邻居读取表达式意味着 baseline 理论上每个输出 scalar 直接请求 4 个 input scalar，共 `4×2,747,520=10,990,080` 次表达式级 input read；编译器或总线可能合并/缓存，不能将其等同于实际 DDR 事务。Buffered 初始每通道装 2 行，`y0` 在 720 条输出行上覆盖 0–59、发生 59 次变化；最后一次前进至 59 时 `y1=y0`，不再装载，所以每通道共装 60 行，全三通道 **180 次 source-row 装载**、**19,080 次 scalar input read**。相对上述表达式级 baseline 为 576 倍的读取次数缩减。输出 scalar write 仍为 **2,747,520**。这些是代码与坐标序列推导值，不是板上 DDR 事务数或实测带宽。

## 7. 与原始 FP32 AXI baseline 比较

| 指标 | Baseline | Buffered | 变化 |
|---|---:|---:|---:|
| CSim max / mean absolute error | `0 / 0` | **`0 / 0`** | 无 |
| 输出像素 loop Achieved II | 4 | **1** | 减少 3 cycle；每次迭代启动间隔为原来的 1/4 |
| 输出像素 loop Iteration Latency | 48 | 36 | -12 cycle |
| DSP | 25 | 42 | +17 |
| LUT | 7,060 | 8,328 | +1,268 |
| FF | 5,396 | 6,497 | +1,101 |
| BRAM_18K | 2 | 6 | +4 |
| URAM | 0 | 0 | 无 |
| Target / Estimated Clock | `10.00 / 7.300 ns` | `10.00 / 7.300 ns` | 相同 |
| 对外接口 | input/output `m_axi`，控制 `s_axilite` | 相同 | 无 |

本地缓存及其控制增加 BRAM、算术/地址与选择逻辑资源；输出像素不再每次从同一 input AXI 端口请求四邻居，消除了 baseline 像素循环因 multiple bus read 造成的 II=4 限制。**不能据输出 loop II=1 直接宣称整图吞吐提升 4 倍**：初始两行 loader II=2、增量装载、AXI burst/DDR 等仍影响总执行时间，顶层总延迟未知且尚未在 RTL 或板上测量。

## 8. 结论与后续

独立 buffered 版本在当前 V1 reference 上通过 Vitis HLS CSim（0 errors、全 2,747,520 输出 `max_abs=mean_abs=0`）；C Synthesis 成功，输出像素 loop Achieved II=1。值得保留为 FP32 数据访问优化实验。资源代价为 DSP +17、LUT +1,268、FF +1,101、BRAM +4；初次双行装载仍有单 input AXI 端口 II=2 warning。当前证据没有 RTL 级、板上总吞吐或 DDR 带宽结论。

如 Master 后续需要，应先用 RTL Co-simulation 或板上测量确认整图周期与 DDR 行为，并在决定通用宽度支持前明确最大输入宽度；本次不继续实施下一阶段。

建议 Commit Message（仅供审核，本次未提交）：`fpga: add buffered FP32 bilinear HLS experiment`

工作区状态：`codex/curve-fp32-baseline` 分支，原始 baseline 文件未改；本次新增的 buffered 源码、配置、脚本及报告均为未跟踪文件。没有 `git add`、commit 或 push。
