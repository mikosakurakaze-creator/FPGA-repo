# KV260 三模块 Fixed16/Q14 V1.1 Vivado 集成与 Validate Design

日期：2026-09-29。**结论：在全新隔离工程中，CNN、Bilinear、Curve 三个 HLS IP 已接入同一 KV260 Block Design；PS AXI-Lite 控制、四组 HP DDR 通路、11 路 m_axi、100 MHz 单时钟和复位均已连接；`validate_bd_design` 实际通过，设计已保存。** 本阶段没有生成 output products/HDL wrapper，没有运行 full synthesis、implementation、bitstream、XSA、PS 软件或板测。AXI 宽度适配与 DDR 带宽尚无 RTL/系统性能证据。

## 1. 任务边界与工程版本

| 项目 | 实际值 |
|---|---|
| Master 分支 | `codex/curve-fp32-baseline`；本次未切换分支、未 commit、未 push |
| 新工程 | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.xpr` |
| 新 Block Design 源文件 | `E:/github/-/fpga/vivado/three_module_integration_v1_1/three_module_integration_v1_1.srcs/sources_1/bd/system/system.bd` |
| 稳定 V1 | `E:/github/-/fpga/vivado/fixed16_integration_v1/`；`git status --short -- fpga/vivado/fixed16_integration_v1` 无变化，未打开保存或重跑旧工程 |
| Board / part | `xilinx.com:kv260_som:part0:1.4` / `xck26-sfvc784-2LV-c` |
| Vivado | 2025.2 Build 6299465 |
| CNN 固定源码 commit | `72b21138ce87a16eb3d3d6163675936b82ceadbc`；没有使用浮动 branch HEAD，也没有修改 core |
| CLK | PS `pl_clk0` = 100 MHz，同一 PL 时钟网 |

新工程目录在本次任务开始时不存在，先实际检查后创建。第一次自动创建在时钟网 Tcl 集合传参处停止，尚未地址分配/Validate；该**本次新建的失败尝试**被移到 `E:/HLS/kv260_v1_1_failed_create_20260929` 保留，修正脚本后从空目标目录重建并通过后续步骤。没有移动或覆盖稳定 V1。工程目录中的 `.xpr/.cache/.gen/.runs` 等由 Vivado 生成，未加入 Git；本次新增的 `system.bd` 和 Tcl 是可审核的设计输入。

## 2. 三个固定 HLS IP 与来源

| IP | VLNV | 本次实际 IP repository |
|---|---|---|
| WZH CNN | `xilinx.com:hls:zero_dce_cnn_top:1.0` | `E:/HLS/kv260_three_module_v1_1_ip_repo/cnn_72b2113_k26_10ns` |
| Bilinear Fixed16 Buffered | `xilinx.com:hls:bilinear_fixed16_buffered:1.0` | `E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip` |
| Curve Image Fixed16 | `xilinx.com:hls:curve_image_fixed16:1.0` | `E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip` |

CNN IP 不是临时 `cnn_synth_k26` 目录的悬空引用：本次从前一轮实际 K26/10 ns 综合结果 `E:/HLS/wzh_cnn_100mhz_audit_72b2113/cnn_synth_k26/hls/impl/ip` **原样复制**到上表固定目录。两处 `component.xml`、ZIP 的 SHA-256 各自完全相同：

| 包文件 | 固定目录路径与 SHA-256 | 包时间（本地 +08:00） |
|---|---|---|
| `component.xml` | `E:/HLS/kv260_three_module_v1_1_ip_repo/cnn_72b2113_k26_10ns/component.xml`；`55aec1707feab74795f6d20c4b3f5e4de4f2faa81b92baa4a15f135b86e834de` | 2026-09-28 23:59:45 |
| `xilinx_com_hls_zero_dce_cnn_top_1_0.zip` | 同目录；`730a0afa24654acb0b1d4f3da80663ece2b0c3f5ba5b29355e1b91238d71c46c` | 2026-09-28 23:59:46 |

其 `component.xml` 的 VLNV、接口与源码提交对应前次审计：K26 `xck26-sfvc784-2LV-c`、HLS target 10.000 ns、estimated 7.300 ns；原始 `night_01` CSim 19,080/19,080 Q14 raw bit-exact。**本次只是复用该验证过的 IP，不重新修改/运行 CNN HLS core。** Bilinear/Curve 继续使用稳定 V1 原版 repository，未使用 RTL Co-sim depth 临时副本。Vivado IP Catalog 对三个 VLNV 各返回唯一 IP definition；`report_ip_status` 列出 178 个主/内部 IP 实例均 `Up-to-date`、`No changes required`，包含三颗 HLS IP，未列 missing/locked。CNN IP 的 `zynquplus` metadata 为 Pre-Production；这是 HLS 打包生命周期标记，不是本次 Validate failure。

## 3. 实际 Block Design 拓扑与 DDR-buffered 数据流

实例：`zynq_ultra_ps_e_0`、`zero_dce_cnn_top_0`、`bilinear_fixed16_buffered_0`、`curve_image_fixed16_0`、`axi_control`、`cnn_data_sc`、`cnn_model_sc`、`bilinear_ddr_sc`、`curve_ddr_sc`、`rst_ps_100m`，另有 `const_locked` 提供 reset IP 的 `dcm_locked=1`。所有三个 HLS IP 的相同底层 AXI pointer/数值 core 均保持原样。没有 AXI Stream、CNN→Bilinear 点对点链路或 Clock Converter。

```text
PS M_AXI_HPM0_FPD ── axi_control (1 SI / 3 MI) ── CNN/Bilinear/Curve s_axi_control

CNN input/output/workspace ── cnn_data_sc (3 SI / 1 MI) ── PS S_AXI_HP0_FPD ── DDR
CNN weights/frac/bias/LUT ── cnn_model_sc (3 SI / 1 MI) ── PS S_AXI_HP1_FPD ── DDR
Bilinear input/output ─────── bilinear_ddr_sc (2 SI / 1 MI) ── PS S_AXI_HP2_FPD ── DDR
Curve input/parameter/output ─ curve_ddr_sc (3 SI / 1 MI) ── PS S_AXI_HP3_FPD ── DDR
```

控制：PS `M_AXI_HPM0_FPD` 启用、`M_AXI_HPM1_FPD` 关闭。`axi_control/S00_AXI` 接 HPM0；M00/M01/M02 分别接 CNN/Bilinear/Curve `s_axi_control`，每颗 HLS IP 用 `ap_ctrl_hs`。`axi_control` 入口实际 128-bit AXI4、三个出口 32-bit AXI4-Lite；SmartConnect 负责协议/宽度适配。三个 AXI-Lite 地址由 Vivado 自动分配并在脚本中断言：

| HLS control | PS 地址 | Range |
|---|---:|---:|
| Bilinear | `0xA0000000` | 64 KiB |
| Curve | `0xA0010000` | 64 KiB |
| CNN | `0xA0020000` | 64 KiB |

逻辑数据流：PS/未来预处理 producer 将已缩小的 `input_q14` 等写 DDR → CNN `a_low_q14` 写 DDR A_low → Bilinear 从**同一 DDR A_low** 读并写 DDR A_full → Curve 从 DDR 读取 `model_input` 和 A_full 并写 DDR enhanced。两段 PL→DDR→PL 交接不要求 PS 把中间参数重新读成 float；现阶段也没有给实际 DDR buffer 硬编码物理地址。

### 11 路 master、实际总线宽度和地址窗口

Vivado saved BD 的真实 `CONFIG.DATA_WIDTH`：**11 路 HLS m_axi pin 均为 32-bit AXI4**，四个 `S_AXI_HP*_FPD` pin 均为 **128-bit AXI4**，各 DDR SmartConnect 为 **32-bit SI → 128-bit MI**。这与 HLS C 类型元素宽度不同：CNN `gmem8` 中权重/frac 元素为 8 bit，`gmem32` bias 为 32 bit，其他 CNN 数组及 Bilinear/Curve Fixed16 元素为 16 bit；IP 包装后的物理 m_axi 总线均为 32 bit。`component.xml` 的例如 `m_axi_gmem_input_RDATA` 和 `m_axi_gmem8_RDATA` 向量均为 `[31:0]`，与 Vivado BD 一致。不能把元素宽度当成 HP 总线宽度。

| master（SI） | SmartConnect/SI | MI→PS HP | SI→MI bus | DDR aperture |
|---|---|---|---|---|
| CNN `m_axi_gmem_input` | `cnn_data_sc/S00_AXI` | HP0 | 32→128 bit | HP0 LOW/HIGH |
| CNN `m_axi_gmem_output` | `cnn_data_sc/S01_AXI` | HP0 | 32→128 bit | HP0 LOW/HIGH |
| CNN `m_axi_gmem_workspace` | `cnn_data_sc/S02_AXI` | HP0 | 32→128 bit | HP0 LOW/HIGH |
| CNN `m_axi_gmem8`（weight+frac） | `cnn_model_sc/S00_AXI` | HP1 | 32→128 bit | HP1 LOW/HIGH |
| CNN `m_axi_gmem32`（bias） | `cnn_model_sc/S01_AXI` | HP1 | 32→128 bit | HP1 LOW/HIGH |
| CNN `m_axi_gmem_lut` | `cnn_model_sc/S02_AXI` | HP1 | 32→128 bit | HP1 LOW/HIGH |
| Bilinear `m_axi_gmem_input` | `bilinear_ddr_sc/S00_AXI` | HP2 | 32→128 bit | HP2 LOW/HIGH |
| Bilinear `m_axi_gmem_output` | `bilinear_ddr_sc/S01_AXI` | HP2 | 32→128 bit | HP2 LOW/HIGH |
| Curve `m_axi_gmem_input` | `curve_ddr_sc/S00_AXI` | HP3 | 32→128 bit | HP3 LOW/HIGH |
| Curve `m_axi_gmem_parameter` | `curve_ddr_sc/S01_AXI` | HP3 | 32→128 bit | HP3 LOW/HIGH |
| Curve `m_axi_gmem_output` | `curve_ddr_sc/S02_AXI` | HP3 | 32→128 bit | HP3 LOW/HIGH |

四个 HP group 均实际可启用、连接并 Validate，不必退化为 11→1。每路 master 的 Address Editor 都保留相应 HP 的 **DDR_LOW `0x0000000000000000` / 2 GiB** 与 **DDR_HIGH `0x0000000800000000` / 32 GiB** 两个窗口，合计 22 个 DDR aperture；每路的 QSPI 映射已显式排除，OCM 被 Vivado 依 memory/register usage 自动排除并在验证时确认无非 DDR 映射。Vivado 对四组 SmartConnect 报 High-performance Mode，对 control 报 Low-Area Mode；`report_ip_status` 可见 SmartConnect 内部 `SC SI_CONVERTER` 实例，BD 宽度不一致而 Validate PASS，说明互连配置接受该适配。**尚未生成 output products/netlist，因此本阶段不能量化最终插入的宽度/协议转换单元资源、DDR 吞吐或 burst 效果。**

## 4. 时钟与复位

PS `PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ=100`。同一个实际 BD net `/zynq_ultra_ps_e_0_pl_clk0` 接三颗 HLS `ap_clk`、五颗 SmartConnect `aclk`、PS HPM0 及 HP0～HP3 的 AXI ACLK、Processor System Reset `slowest_sync_clk`。脚本逐 pin 核对同一 net；HPM1 禁用。没有另建 PL 时钟、时钟变换器或 CDC。

`PS pl_resetn0 → rst_ps_100m/ext_reset_in`；`const_locked/dout=1 → dcm_locked`；`peripheral_aresetn → 三颗 HLS ap_rst_n`；`interconnect_aresetn → 五颗 SmartConnect aresetn`。在首轮 validation 前，`C_EXT_RESET_HIGH` 暂显示 1；Vivado propagation/Validate 后 `ext_reset_in` 实测 `POLARITY=ACTIVE_LOW` 且 `C_EXT_RESET_HIGH=0`，已保存。复核脚本还逐一核对三颗 HLS 和五颗 SmartConnect 的实际 reset net。未手写只读 polarity 属性。

## 5. 后续 PS 软件边界及最低 payload 容量

**前处理尚不存在于本 BD**：CNN top 要求 `[1,3,60,106]` RGB/NCHW signed INT16 Q14，不能直接输入 720×1280 原图。未来 PS/software producer 负责原图 crop 至 720×1272、按既定规则 12× downsample、Q14 量化并写入 DDR `input_q14`；本次未写软件，也没有增加 preprocessing IP。CNN 输出 A_low 与 Bilinear Fixed16 输入在 16-bit raw Q14 上一致，不做 requant、layout reorder 或 AXIS adapter。

下表按元素数×字节数逐项重新计算，只是**payload 最低容量**；缓存对齐、页对齐和实际 buffer 物理地址属后续 PS 软件设计：

| DDR buffer | 算式 | 最低字节数 |
|---|---:|---:|
| CNN `input_q14` | 19,080×2 | 38,160 |
| CNN `weights_int8` | 10,075×1 | 10,075 |
| CNN `bias_int32` | 486×4 | 1,944 |
| CNN `weight_frac` | 486×1 | 486 |
| CNN `tanh_lut_q15` | 4,097×2 | 8,194 |
| CNN `workspace_int16` | 1,221,120×2 | 2,442,240 |
| DDR A_low / CNN `a_low_q14` / Bilinear input | 19,080×2 | 38,160 |
| DDR A_full / Bilinear output / Curve `parameter` | 2,747,520×2 | 5,495,040 |
| Curve `model_input` | 2,747,520×2 | 5,495,040 |
| DDR enhanced / Curve output | 2,747,520×2 | 5,495,040 |
| **不同用途 buffer payload 合计** | 逐项求和，共用 A_low/A_full 只各计一次 | **19,024,379 B** |

未来调度合同：PS 准备并 flush CNN input、weights、bias、frac、LUT，分配有效 workspace/output buffer；设七个 CNN 指针（含 workspace 与 A_low），start→wait `ap_done`；Bilinear 的 `input` 指向同一 A_low、`output` 指向 A_full，`H=60`,`W=106`，start→wait；Curve 的 `input=model_input`,`parameter=A_full`,`output=enhanced`,`count=2,747,520`，start→wait。PS cache/coherency 细节及真实 DDR 读写尚未实现/验证。两个参数图中间缓冲区由相邻 IP 共享 DDR 地址，但不同工作缓冲区不得意外重叠。

## 6. Validate、warning 与当前风险

`validate_bd_design` **PASS**；保存后的复核再次 PASS。三颗 HLS IP 及 SmartConnect/PS/Reset 在 IP 状态报告中 Up-to-date，未见 missing/locked；没有 AXI address path failure、unsupported width/burst error、clock/reset blocker 或需插入额外时钟域的要求。详细可复核日志 `E:/HLS/vivado_three_module_v1_1_verify.log` 和 IP 状态 `E:/HLS/vivado_three_module_v1_1_ip_status.rpt`。

重要日志分类如下，均未升级为 error：

| 消息 | 实际含义与处置 |
|---|---|
| `BD 41-237` ×8 | 四路 PS HP 端口各有 AWUSER/ARUSER width **1**，对应 SmartConnect MI 为 **0**；与旧 V1 的 HP0 提示同类。Validate PASS，不代表 post-synth/post-route 已证明无问题；下阶段 output products/synthesis 再查 AXI 参数和 DRC。未观察到 AWLOCK/ARLOCK 错配 warning。 |
| `BD 41-3281` ×4 | PS 与三颗 HLS IP 都被 SmartConnect 接在两侧，Vivado 不能自动替端点推断所有 AXI 参数；本工程已显式设置 SmartConnect SI/MI 数量，实际宽度/协议均可读且 Validate PASS。下阶段需检查生成互连的参数/资源。 |
| `BD 41-1629` ×8 | HP0～HP3 的 QSPI 和 LPS_OCM 段被排除于所有 HLS memory address paths，正是 DDR-only 设计意图。 |
| `BD 41-1051`（初始自动 assign） | OCM `register` 段与 HLS `memory` address-space usage 不符，Vivado 自动排除；随后复核没有 OCM mapping。 |
| `Board 49-26` | 本机加载板卡 catalog 时若干**其他型号** board part 不可用；KV260 board part 仍已设置，四 HP 和 PS preset 可用。 |
| `BD 41-1753` | Bilinear 实例名在 Windows 较长，后续 output products 可能面临路径长度限制；当前 Validate 未受影响。 |
| `BD 5-1043` | `xlconstant` 提示未来改用 inline HDL；沿用 V1 reset glue，本阶段可 Validate。 |

第一次 `verify` 脚本在 **Validate 之前**检查 `C_EXT_RESET_HIGH` 得到 1，因 PS 极性尚未传播而提前停止；只把检查移到实际 `validate_bd_design` 之后，重新执行后得到 0 且 PASS。没有手动篡改 reset polarity，也没有改变算法/位宽/时钟。Vivado `validate_bd_design` Tcl 返回空字符串，但日志无 ERROR，打印 `V1_1_VALIDATE=PASS` 且已保存；不能单看空返回值误判失败。

## 7. 与旧 V1 的区别及下一步

旧 V1 仅 Bilinear+Curve：PS HPM0→1:2 AXI control，五路 HLS m_axi→单 SmartConnect→HP0；已经完成独立的 synthesis/implementation/bitstream/XSA。新 V1.1 是**独立工程**：增加固定 `72b2113` CNN、控制 1:3、DDR master 总数 11、四组 SmartConnect 分别到 HP0～HP3；CNN 的 workspace 2,442,240 B 和六个物理 AXI master 都纳入系统。新增阶段只有 BD Validate，不继承旧 V1 的 post-route timing 或 bitstream 成功结论。

**建议 Master 审核拓扑后，在新 V1.1 工程进入 output products/HDL wrapper 和 full synthesis。** 届时重点核对三个 HLS IP 的生成/lock、SmartConnect 32→128 宽度适配及 128-bit HPM0→AXI4-Lite 转换、AXI USER width warning、系统资源与 100 MHz 时序；再另行决定 Implementation。当前不能宣称 DDR 带宽足够、CNN 全帧吞吐达标或 KV260 三模块板上链已工作。

## 8. 可复现脚本、实际执行与 Git 状态

本次新增三个顺序执行的 Tcl：

1. `fpga/scripts/vivado_three_module_v1_1_create.tcl`：拒绝覆盖已有 V1.1 目录；注册三个固定 IP，创建全新 board/PS/BD/核心/SmartConnect/100 MHz/reset 并保存。
2. `fpga/scripts/vivado_three_module_v1_1_stage2.tcl`：接 1:3 AXI-Lite 与 3+3+2+3 master 到 HP0～HP3，自动 assign 地址并保存。
3. `fpga/scripts/vivado_three_module_v1_1_verify.tcl`：排除 QSPI/OCM、核对 3 个 control 和 22 个 DDR aperture、逐 pin 核对 clock/reset/AXI/宽度、Validate、保存并出 IP 状态报告。

实际在 PowerShell 顺序运行的入口命令：

```powershell
& E:\HLS\vivado_three_module_v1_1_create.cmd
& E:\HLS\vivado_three_module_v1_1_stage2.cmd
& E:\HLS\vivado_three_module_v1_1_verify.cmd
```

各 `.cmd` 均先 `call E:\Xilinx\2025.2\data\settings64.bat`，再 `call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source <对应 Tcl> -log <E:\HLS\vivado_three_module_v1_1_*.log> -journal <...> -notrace`。`create.cmd` 首次失败后修正、重建 PASS；`stage2.cmd` PASS；`verify.cmd` 首次在 reset pre-validation 检查处停止，修正后 PASS，再从保存工程复核 PASS。主项目 Tcl 从自身路径推得 repo root；重建前须确保三个精确 IP repository 存在，尤其 CNN 固定目录及上述 SHA。没有复制旧 V1 的 `.runs/.gen/.cache`。

本次任务文件：新增上述三个 Tcl、上述 V1.1 `system.bd`、本报告；`.gitignore` 只新增 `dfx_runtime.txt` 忽略规则，防止 Vivado 生成的运行文件进入 Git 状态。生成的 `.xpr` 与缓存未加入 Git。原有未跟踪文件保持原样，稳定 V1 没有修改。**没有 `git add`、commit 或 push。**

明确未运行/未验证：V1.1 output products、HDL wrapper、full Vivado Synthesis、Implementation/post-route timing/DRC、Bitstream、XSA、PS 软件、DDR 实机读写、KV260 板测、CNN RTL Co-sim、DDR 带宽/FPS、CNN→Bilinear→Curve 三模块硬件数值链。
