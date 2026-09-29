# KV260 三模块 V1.1：Bitstream、XSA 与 PS 寄存器交接

日期：2026-09-29。**结论：现有 routed V1.1 从 `impl_1` 成功完成 `write_bitstream`，并导出包含同一份 bitstream 的 XSA。前后 100 MHz setup/hold/pulse width 均满足，三颗 HLS IP 的 AXI-Lite 地址和寄存器已从最终 XSA 与打包驱动核实。可以进入 PS software skeleton；实际 DDR/cache/板上功能仍未验证。**

## 1. 目标、固定基线与范围

| 项目 | 实际值 |
|---|---|
| Git branch / 执行时 HEAD | `codex/curve-fp32-baseline` / `9c3ff825ed1e6bc4c5f7176aa0b1ec19f797e0f3` |
| Vivado | 2025.2，SW Build 6299465，IP Build 6300035 |
| Board / part | `xilinx.com:kv260_som:part0:1.4` / `xck26-sfvc784-2LV-c` |
| V1.1 工程 / top | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.xpr` / `system_wrapper` |
| 固定 CNN 源码 | WZH `72b21138ce87a16eb3d3d6163675936b82ceadbc`；使用原已注册的 K26 10 ns IP repository，未重新 HLS |
| 旧 V1 | `fpga/vivado/fixed16_integration_v1/` 未修改；旧 `E:/HLS/vivado_fixed16_bitstream_xsa_v1/kv260_fixed16_v1.xsa` 未覆盖 |

本次新增 `fpga/scripts/vivado_three_module_v1_1_bitstream_xsa.tcl`、`fpga/docs/v1_1_hw_register_map.json` 和本报告。没有修改 CNN/Bilinear/Curve、BD、AXI、100 MHz 时钟、reset、HLS pragma 或 implementation strategy；未运行 PS 软件、板测、RTL Co-sim；未 `git add`、commit、push。Bitstream/XSA 位于忽略的工程输出与 `E:/HLS`，没有加入 Git。

## 2. 前置复核、实际命令与时间

脚本从磁盘打开原 V1.1 工程，检查 board/part/top、`synth_1=synth_design Complete!` / 100%、`impl_1=route_design Complete!` / 100% 和 `system_wrapper_routed.dcp` 存在。**先独立执行 preflight-only**，重新打开 routed design 并实际生成 timing、route、DRC、`check_timing` 报告，未运行 bitstream。通过后使用同一 Tcl 的正式模式再次执行同样关口，再 `launch_runs impl_1 -to_step write_bitstream -jobs 4`、`wait_on_run impl_1`，重新打开 design 做 post-bitstream 审计，最后 `write_hw_platform -fixed -include_bit -force -file ...`。没有 `reset_run` 或重新执行 opt/place/phys_opt/route；routed DCP mtime 在 bitstream 前后相同。

实际 PowerShell 命令：

```powershell
& 'E:\HLS\vivado_three_module_v1_1_bitstream_xsa_preflight.cmd'
& 'E:\HLS\vivado_three_module_v1_1_bitstream_xsa.cmd'
python 'E:\HLS\vivado_three_module_v1_1_bitstream_xsa\build_register_map.py'
python -m json.tool 'fpga/docs/v1_1_hw_register_map.json'
```

两个外部 `.cmd` 均加载 `E:\Xilinx\2025.2\data\settings64.bat`，调用 `E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_three_module_v1_1_bitstream_xsa.tcl -notrace`；preflight 额外传 `-tclargs preflight`。原始日志：`E:/HLS/vivado_three_module_v1_1_bitstream_xsa_preflight.log`、`E:/HLS/vivado_three_module_v1_1_bitstream_xsa_driver.log`、V1.1 `impl_1/runme.log`。审计报告在 `E:/HLS/vivado_three_module_v1_1_bitstream_xsa/`。生成 JSON 的一次性解析脚本留在 `E:/HLS`，没有加入仓库；它从最终 XSA 的 `system.hwh`、`sysdef.xml` 和 XSA 内三份驱动头文件读取并相互校验地址、寄存器宽度、offset 和访问属性。

| 操作 | 本地时间（UTC+08） | 结果 |
|---|---|---|
| 独立 preflight | 21:20:41～21:23:39 | PASS，未生成 bitstream |
| `write_bitstream` 调度 | 21:26:17～21:28:55，158 s | `write_bitstream Complete!` / 100% |
| XSA 导出 | 21:30:28～21:30:52，24 s | `Successfully created Hardware Platform` |

| 复核项 | 生成前 | 生成后 |
|---|---:|---:|
| Setup WNS / TNS / failing endpoints | +1.720 ns / 0 / 0 | +1.720 ns / 0 / 0 |
| Hold WHS / THS / failing endpoints | +0.010 ns / 0 / 0 | +0.010 ns / 0 / 0 |
| Pulse WPWS / TPWS / failing endpoints | +3.500 ns / 0 / 0 | +3.500 ns / 0 / 0 |
| Routable / fully routed | 57,441 / 57,441 | 57,441 / 57,441 |
| Routing errors | 0 | 0 |
| DRC Error / Critical Warning | 0 / 0 | 0 / 0 |
| `check_timing` no-clock / unconstrained internal endpoints | 0 / 0 | 0 / 0 |

生成前、后 DRC 都是 136 条 **Warning**：`DPIP-2` 40、`DPOP-3` 43、`DPOP-4` 52（135 条 DSP 流水线建议），`RTSTAT-10` 1（`axi_control` 内部复位管道相关 net 无可路由负载）。它们没有变成 Error；`RTSTAT-10` 不等于 unrouted net。生成阶段 bitstream 前置 DRC `0 Errors`；worker 明确报告 `Bitgen Completed Successfully`、`write_bitstream completed successfully`、`75 Infos, 0 Warnings, 0 Critical Warnings and 0 Errors`。同时，worker 原始文本仍有 3 次非标准格式 `WARNING::74 - Unsupported FPGA device name 'xck26-sfvc784-2LV-c'`，出现在 `open_checkpoint` 后的内存数据/updatemem 检查附近；其后 bitgen 成功、产物 device/board 正确，故不是 bitstream blocker，但不能从正式 0 Warning 汇总中抹去。外层 Vivado 打开 Board Catalog 时另有 73 条与其他未安装器件有关的 `[Board 49-26]`，另有 1 条 Windows IP cache 路径长度 `[IP_Flow 19-4995]`。无 Error 或 Critical Warning。没有发现 unconstrained pin、clock、AXI、routing 或 bitstream rule 阻断。

## 3. Bitstream 与 XSA 文件验收

| 项目 | Bitstream | XSA |
|---|---|---|
| 完整路径 | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.runs/impl_1/system_wrapper.bit` | `E:/HLS/vivado_three_module_v1_1_bitstream_xsa/kv260_three_module_v1_1.xsa` |
| 大小 | **7,797,826 B** | **2,610,226 B**（ZIP 压缩容器） |
| SHA-256 | `20eb18fdf01d9ec3ee50489054c7e937d8aab964200d2e6b1715818927701b0b` | `00aa1fbb240b348ea01dbaf5ddd72921ba6e2e12d57009c6c5434e54d59c5fb1` |
| 修改时间（UTC+08） | 2026-09-29 21:28:53 | 2026-09-29 21:30:46 |
| 工具状态 | `write_bitstream Complete!` / 100% | `Successfully created Hardware Platform` |

无 `system_wrapper.ltx`，设计无 ILA，未把缺失 `.ltx` 判为错误。用 Python `zipfile.testzip()` 校验 XSA ZIP 全部条目，结果无坏文件。XSA 内 `kv260_three_module_v1_1.bit` 解压后也为 **7,797,826 B**，SHA-256 与外部 `system_wrapper.bit` 完全相同，进一步逐字节比较为 `True`。XSA `sysdef.xml` 明列 `Type="BIT"`，并含 `system.hwh`、PS 初始化文件、三个 HLS driver 目录、`system_axi_control_0.hwh`、`system_cnn_data_sc_0.hwh`、`system_cnn_model_sc_0.hwh`、`system_bilinear_ddr_sc_0.hwh`、`system_curve_ddr_sc_0.hwh`。`sysdef.xml` 的 USEDRESOURCES 为 LUT 27,045、FF 39,451、BRAM tile 29、DSP 76，与 routed 里程碑一致。

XSA `system.hwh` 实际存在 `zynq_ultra_ps_e_0`、`rst_ps_100m`、`axi_control`、四个 DDR SmartConnect，以及 `zero_dce_cnn_top_0`、`bilinear_fixed16_buffered_0`、`curve_image_fixed16_0`。三颗 IP 的 `ap_clk` 均连接 PS `pl_clk0`；`ap_rst_n` 均连接 `rst_ps_100m/peripheral_aresetn`，极性 `ACTIVE_LOW`。PS HPM0 经 `axi_control` 到三个 `s_axi_control`；CNN 数据/工作区通过 HP0、模型数据通过 HP1，Bilinear 通过 HP2，Curve 通过 HP3 访问 DDR。XSA 内三份 HLS `*_hw.h` 与本工程 `.gen` 驱动及原 IP repository 对应文件的 SHA-256 分别完全一致：Bilinear `8eee5035...ebf065a3`、Curve `8c145a90...a409660c`、CNN `3a5b88ee...716362`。这些验证覆盖 handoff 文件与映射存在性，不代表 AXI runtime 已测试。

## 4. 最终 AXI-Lite 控制地址与公共寄存器

地址由本次重新打开的 BD `get_bd_addr_segs` 与最终 XSA `system.hwh` **双重核对**：

| IP instance | Base | High | Range |
|---|---|---|---:|
| `bilinear_fixed16_buffered_0` | `0xA0000000` | `0xA000FFFF` | 64 KiB |
| `curve_image_fixed16_0` | `0xA0010000` | `0xA001FFFF` | 64 KiB |
| `zero_dce_cnn_top_0` | `0xA0020000` | `0xA002FFFF` | 64 KiB |

三个 `s_axi_control` 的公共 **32-bit 寄存器**：

| Offset | Register | 访问与位定义（打包 driver `*_hw.h`） |
|---|---|---|
| `0x00` | `AP_CTRL` | bit0 `ap_start` R/W、**COH (clear-on-handshake)**；bit1 `ap_done` R/**COR (clear-on-read)**；bit2 `ap_idle` R；bit3 `ap_ready` R/COR；bit7 `auto_restart` R/W；bit9 `interrupt` R |
| `0x04` | `GIE` | bit0 全局中断使能，R/W |
| `0x08` | `IER` | bit0 ap_done、bit1 ap_ready 中断使能，R/W |
| `0x0C` | `ISR` | bit0 ap_done、bit1 ap_ready 中断状态，**R/TOW (toggle-on-write)** |

`ap_start` 的实际注释是 **COH**，不是 SC/self-clear；启动后由核心握手清除。`ap_done` 读取 `AP_CTRL` 时清除，因此轮询时每次读取都应保存当次返回值，避免先读一次用于调试却消费完成事件。当前伪代码不用中断；`GIE/IER/ISR` 的精确定义仍提供给后续软件。HWH 把 32-bit 参数寄存器标为 `write-only`，但 HLS `*_hw.h` 注释写 `Read/Write` 且生成 RTL `rdata` case 确实给出读回；这属于 handoff metadata 与 RTL/driver 注释不一致。PS 软件应按**只需写入**的合同使用参数寄存器，不依赖参数读回或以其作为硬件验证。三颗 IP 的控制寄存器在 HWH 中标为 `read-write`。

## 5. 三颗 IP 的完整参数寄存器表

下列 offset 全部相对各自 base。指针都是 **64 bit**，由连续两个 **32-bit AXI-Lite word** 写入：low 为 bits `[31:0]`，high 为 bits `[63:32]`。`H/W/count` 为 32 bit。表中每个参数 word 的 HWH 声明访问为 `write-only`；HLS driver/RTL 的读回差异见上节。

### Bilinear：`base=0xA0000000`

| 参数（驱动名） | Low / scalar offset | High offset | 宽度 | PS 语义 |
|---|---:|---:|---:|---|
| `parameters_lowres` | `0x10` | `0x14` | 64 | DDR A_low 输入指针 |
| `parameters_fullres` | `0x1C` | `0x20` | 64 | DDR A_full 输出指针 |
| `input_height` | `0x28` | — | 32 | `60` |
| `input_width` | `0x30` | — | 32 | `106` |

### Curve：`base=0xA0010000`

| 参数（驱动名） | Low / scalar offset | High offset | 宽度 | PS 语义 |
|---|---:|---:|---:|---|
| `input_r` | `0x10` | `0x14` | 64 | DDR `model_input` 输入指针 |
| `parameter_r` | `0x1C` | `0x20` | 64 | DDR A_full 输入指针 |
| `output_r` | `0x28` | `0x2C` | 64 | DDR `enhanced` 输出指针 |
| `count` | `0x34` | — | 32 | `2,747,520` 个 scalar |

### CNN：`base=0xA0020000`

| 参数（驱动名） | Low offset | High offset | 宽度 | PS 语义 |
|---|---:|---:|---:|---|
| `input_q14` | `0x10` | `0x14` | 64 | DDR CNN 输入 |
| `weights_int8` | `0x1C` | `0x20` | 64 | DDR INT8 weights |
| `bias_int32` | `0x28` | `0x2C` | 64 | DDR INT32 bias |
| `weight_frac` | `0x34` | `0x38` | 64 | DDR fractional-bit 表 |
| `tanh_lut_q15` | `0x40` | `0x44` | 64 | DDR Q15 LUT |
| `a_low_q14` | `0x4C` | `0x50` | 64 | DDR A_low 输出 |
| `workspace_int16` | `0x58` | `0x5C` | 64 | DDR CNN scratch |

这些名称/offset/宽度直接从**最终 XSA 自带**三个 `drivers/*/src/x*_hw.h` 提取，并用 XSA `system.hwh` 的 32-bit low/high registers 复核；不是从旧 V1 猜测。对应机器可读文件 `fpga/docs/v1_1_hw_register_map.json` 包含 board、part、Vivado、CNN commit、XSA hash、base/range、三颗 IP 的公共控制寄存器、全部 pointer/scalar offsets/位宽/HWH 访问属性、常量和 buffer 大小。CNN commit 是固定 IP repository 的已审计来源信息，**并非 XSA 自身嵌入的 Git commit 字段**。

## 6. DDR payload、数据流和 PS 软件准备

大小依据当前 CNN header 的 weight/bias/frac/LUT/workspace 常量、三通道 `[1,3,60,106]` / `[1,3,720,1272]` 和 16-bit scalar 计算；`weight_frac` 为 8-bit，bias 为 32-bit。此表是**不同用途 payload 的逻辑总量**，不是 DDR allocator 的实际申请大小。

| Buffer | 计算 | Payload bytes |
|---|---:|---:|
| CNN `input_q14` | `3×60×106×2` | 38,160 |
| `weights_int8` | `10,075×1` | 10,075 |
| `bias_int32` | `486×4` | 1,944 |
| `weight_frac` | `486×1` | 486 |
| `tanh_lut_q15` | `4,097×2` | 8,194 |
| `workspace_int16` | `1,221,120×2` | 2,442,240 |
| A_low | `3×60×106×2` | 38,160 |
| A_full | `3×720×1272×2` | 5,495,040 |
| `model_input` | `3×720×1272×2` | 5,495,040 |
| `enhanced` | `3×720×1272×2` | 5,495,040 |
| **合计** | 重新计算 | **19,024,379** |

后续 PS 软件仍需按物理地址范围、alignment、cache line、page、allocator 要求决定实际 DDR 分配；不得直接把 payload 合计当成内存预留值。64-bit 指针寄存器也不意味着任意 DDR 物理地址都已板上验证。

冻结的 V1.1 软件/硬件交接顺序：

```text
Original image
  -> PS/software crop 720×1272
  -> downsample 12× -> RGB/NCHW Q14 -> DDR input_q14 [1,3,60,106]
  -> CNN(input_q14, model data, workspace) -> DDR A_low Q14 [1,3,60,106]
  -> Bilinear(A_low, H=60, W=106) -> DDR A_full Fixed16 [1,3,720,1272]
  -> Curve(model_input Fixed16 [1,3,720,1272], A_full, count=2747520)
  -> DDR enhanced Fixed16 [1,3,720,1272]
```

原图裁剪、降采样、RGB/NCHW 转换、定点量化和 `model_input` 准备是下一阶段 PS/software 责任；本次 XSA 仅证明硬件接口，不证明这些预处理已有软件实现或板上数值正确。A_low 的 signed 16-bit Q14 raw 与 Bilinear `ap_fixed<16,2,AP_RND,AP_SAT>` 的外部 16-bit/Q14 存储格式对应，当前 V1.1 通过 DDR 交接原始 16-bit words。三模块中间为 **PL → DDR → PL**，没有 AXI Stream、PL 直接链式连接或预处理 IP。

下面只是以本次实际寄存器 map 为依据的**PS software 调度伪代码，未编译/运行**；`write_ptr64` 按表分别向 low/high offset 写 32-bit word。

```text
prepare_and_flush(cnn_input_q14, weights_int8, bias_int32, weight_frac, tanh_lut_q15,
                  model_input_fixed16, scratch/output buffers as required)

write_ptr64(0xA0020000, 0x10, 0x14, phys_cnn_input_q14)
write_ptr64(0xA0020000, 0x1C, 0x20, phys_weights_int8)
write_ptr64(0xA0020000, 0x28, 0x2C, phys_bias_int32)
write_ptr64(0xA0020000, 0x34, 0x38, phys_weight_frac)
write_ptr64(0xA0020000, 0x40, 0x44, phys_tanh_lut_q15)
write_ptr64(0xA0020000, 0x4C, 0x50, phys_a_low_q14)
write_ptr64(0xA0020000, 0x58, 0x5C, phys_workspace_int16)
write32(0xA0020000 + 0x00, 1)  // ap_start bit0; clear-on-handshake
poll_until(read32(0xA0020000 + 0x00) & 0x02)  // ap_done, clear-on-read

write_ptr64(0xA0000000, 0x10, 0x14, phys_a_low_q14)
write_ptr64(0xA0000000, 0x1C, 0x20, phys_a_full_fixed16)
write32(0xA0000000 + 0x28, 60)
write32(0xA0000000 + 0x30, 106)
write32(0xA0000000 + 0x00, 1)
poll_until(read32(0xA0000000 + 0x00) & 0x02)

write_ptr64(0xA0010000, 0x10, 0x14, phys_model_input_fixed16)
write_ptr64(0xA0010000, 0x1C, 0x20, phys_a_full_fixed16)
write_ptr64(0xA0010000, 0x28, 0x2C, phys_enhanced_fixed16)
write32(0xA0010000 + 0x34, 2747520)
write32(0xA0010000 + 0x00, 1)
poll_until(read32(0xA0010000 + 0x00) & 0x02)

invalidate_enhanced_cache_as_required()
read_or_save_enhanced()
```

实际 buffer 物理地址、非一致性 HP 访问的 flush/invalidate、处理器内存屏障、数据交接顺序和 DMA/allocator 行为均**未板测**。PS skeleton 可以据此定义寄存器常量、buffer 尺寸和调用顺序，但每个 cache/coherency 假设需要运行时验证。

## 7. 当前结论与未验证边界

- **已验证**：Bitstream 完成、前后 routed timing/route/DRC clean、XSA 导出完成、ZIP CRC 正常、XSA 内外 bitstream 逐字节一致、PS/三颗 IP/五 SmartConnect/reset/地址 map/打包驱动存在，寄存器布局已冻结。
- **需保留关注**：三次 `WARNING::74` 的内存数据/updatemem 设备名提示；136 条非阻断 post-route DRC Warning；HWH 参数 `write-only` 与 driver/RTL 读回描述不一致，软件只依赖写入。
- **未运行/未验证**：board boot、实际 DDR transaction、PS cache/coherency、AXI runtime、DDR throughput、FPS、CNN RTL Co-sim、三模块板上最终图像数值链，以及 PS 软件编译/执行。

因此**具备开始 PS software skeleton 的硬件交接资料**，但还不能声称板级功能或吞吐达标。下一步只建议 Master 审核本报告与 JSON 后建立 PS 软件骨架，再在 KV260 上逐项验证地址写入、cache、DDR 和输出；本次未擅自开始。
