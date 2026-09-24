# KV260 Vivado Fixed16 V1 系统集成

## 1. 目标与范围

在现有 Kria KV260 Vision AI Starter Kit SOM 的 Vivado 2025.2 工程和 `system` Block Design 上，接入原版 `bilinear_fixed16_buffered` 与 `curve_image_fixed16` HLS IP，形成由 PS 控制、经 PS HP0 访问 DDR 的 V1 拓扑。完成 Processor System Reset、两条控制接口、五条数据接口、100 MHz 时钟、地址映射和 `Validate Design`。

本次没有修改 Fixed16 算法源码、格式、缓存、公式或性能 pragma；没有 AXI Stream 化、CNN、RGB 并行或性能优化。未做 Vivado synthesis、implementation、bitstream、软件驱动或 KV260 板上测试。DDR 中 A_low / A_full / model_input / enhanced 的缓冲区分配和 PS 启动顺序属于后续软件集成，当前只是硬件地址通路。

## 2. 基线与版本

| 项目 | 实际结果 |
| --- | --- |
| Git 分支 | `codex/curve-fp32-baseline` |
| HEAD | `5b1f54a380e5bd1e2cf0b892c303a94a089a47af` |
| Vivado | 2025.2，SW Build 6299465，IP Build 6300035 |
| 工程 | `fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr` |
| Block Design | `fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd` |
| Board Part | `xilinx.com:kv260_som:part0:1.4`，目标器件 `xck26-sfvc784-2LV-c` |
| HLS 核心基线 | `fpga/hls/bilinear_fixed16_buffered/`、`fpga/hls/curve_image_fixed16/`，均保持原样 |
| HLS 外部数据格式 | `ap_fixed<16,2,AP_RND,AP_SAT>`，每元素 16 bit |
| PS PL 时钟 | `pl_clk0` 配置值 100 MHz |

本次沿用此前各自通过 CSim、C Synthesis、RTL Co-sim 的计算核心。当前 Vivado 工程没有对任何 reference 数组重新做数值测试。软件约定为 NCHW、batch=1、channels=3；实际 DDR 地址和处理时序还未由 PS 程序配置。

开始时，磁盘上的 `system.bd` 只有空设计框架，而 Vivado GUI 中已有未保存的 PS 设置。用户保存工程后，磁盘文件显示 Zynq UltraScale+ MPSoC、`M_AXI_HPM0_FPD`、`S_AXI_HP0_FPD` 和 100 MHz `pl_clk0`；本次集成以该已保存状态为起点。执行集成时 GUI 仍在运行，实际修改由独立的 Vivado batch 会话写入磁盘。**若原 GUI 仍打开旧版设计，审核时应重新打开工程/Block Design，避免旧 GUI 状态再次保存覆盖本次结果。**

## 3. 最终 Block Design 拓扑

```text
                         PS M_AXI_HPM0_FPD
                                  |
                     axi_control (SmartConnect 1->2)
                         /                    \
             Bilinear s_axi_control     Curve s_axi_control

 DDR A_low ----> Bilinear m_axi_gmem_input
                    |
                    +---- Bilinear m_axi_gmem_output ----> DDR A_full

 DDR model_input ----> Curve m_axi_gmem_input
 DDR A_full ---------> Curve m_axi_gmem_parameter
                    +---- Curve m_axi_gmem_output ----> DDR enhanced

 所有五个 m_axi -> axi_ddr (SmartConnect 5->1)
                         -> PS S_AXI_HP0_FPD -> PS DDR 地址空间

 PS pl_clk0 (100 MHz) -> 两个 HLS ap_clk、两个 SmartConnect aclk、
                          两个 PS AXI 端口时钟、Processor System Reset
 PS pl_resetn0 -> Processor System Reset -> HLS ap_rst_n / AXI aresetn
```

这是 PS 调度的**DDR 中转链**：Bilinear 写 A_full 后，由后续 PS 控制 Curve 从同一 DDR 缓冲区读取。两个 IP 之间没有 AXI Stream 或直接片上线缆；当前 Block Design 不负责自动先后调度。

### 实际加入的 HLS IP

两个原始 HLS 工程此前已生成 Vivado IP `component.xml` 和 ZIP，本次直接把下列目录注册为 Vivado IP repository；没有重新 export，也没有使用 RTL Co-sim 的 depth 专用副本：

| IP | 注册目录 | Vivado VLNV | BD 实例 |
| --- | --- | --- | --- |
| Bilinear | `E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip` | `xilinx.com:hls:bilinear_fixed16_buffered:1.0` | `bilinear_fixed16_buffered_0` |
| Curve | `E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip` | `xilinx.com:hls:curve_image_fixed16:1.0` | `curve_image_fixed16_0` |

Vivado `get_ipdefs -all` 对两个 VLNV 各找到一个 IP，`system.bd` 保存后再次打开也正确识别。原核心 CPP 与对应 IP 打包时间相符，且本次 Git 状态无原核心修改。工程的 `.xpr` 保存了两个 `E:/HLS` 仓库路径；迁移工程到其他机器前需提供这些 IP 包并更新路径。

### IP 接口与 SmartConnect

| 实例 | AXI4-Lite | AXI4 Memory-Mapped master | DDR SmartConnect 输入 |
| --- | --- | --- | --- |
| `bilinear_fixed16_buffered_0` | `s_axi_control`：输入/输出指针、`input_height`、`input_width`、启动控制 | `m_axi_gmem_input` | `axi_ddr/S00_AXI` |
| 同上 | 同一 control | `m_axi_gmem_output` | `axi_ddr/S01_AXI` |
| `curve_image_fixed16_0` | `s_axi_control`：三个指针、`count`、启动控制 | `m_axi_gmem_input` | `axi_ddr/S02_AXI` |
| 同上 | 同一 control | `m_axi_gmem_parameter` | `axi_ddr/S03_AXI` |
| 同上 | 同一 control | `m_axi_gmem_output` | `axi_ddr/S04_AXI` |

`axi_control` 是一只 1 SI / 2 MI SmartConnect：`PS M_AXI_HPM0_FPD -> S00_AXI`，其 `M00_AXI -> Bilinear s_axi_control`、`M01_AXI -> Curve s_axi_control`。`axi_ddr` 是另一只 5 SI / 1 MI SmartConnect：上述五个 HLS master 汇聚到 `M00_AXI -> PS S_AXI_HP0_FPD`。共 **2 只 SmartConnect**，没有另建传统 AXI Interconnect。PS `M_AXI_HPM1_FPD` 是 Board Automation 顺带启用的闲置口，本次禁用；PS 其余未使用 AXI 端口保持原工程状态。

## 4. 时钟、复位与地址

### 时钟与 Processor System Reset

- `zynq_ultra_ps_e_0/pl_clk0` 配置为 100 MHz，连至两个 HLS `ap_clk`、两只 SmartConnect `aclk`、PS `maxihpm0_fpd_aclk` 和 `saxihp0_fpd_aclk`，以及 `rst_ps_100m/slowest_sync_clk`。
- PS `pl_resetn0` 接 `rst_ps_100m/ext_reset_in`。Vivado 最终验证的 `CONFIG.POLARITY=ACTIVE_LOW` 且 `CONFIG.C_EXT_RESET_HIGH=0`；低有效 PS reset 语义正确。
- `const_locked/dout=1` 接 `rst_ps_100m/dcm_locked`，因为本次没有外部 MMCM/PLL 的锁定输出；时钟直接来自 PS `pl_clk0`。
- `rst_ps_100m/interconnect_aresetn` 接两只 SmartConnect `aresetn`；`peripheral_aresetn` 接两个 HLS `ap_rst_n`。两者均为 100 MHz 域同步释放的低有效复位。

曾尝试直接设置 `C_EXT_RESET_HIGH` 和 `ext_reset_in` 的 `POLARITY`，Vivado 分别提示 `[BD 41-737]` 为只读。实际连接后在 Validate 阶段自动推导为低有效；最终脚本已移除两处手工设置，保存状态为正确的 `ACTIVE_LOW/0`。相关早期警告及后续修正均保留在日志中。

### AXI Address Editor 映射

| PS / HLS 地址空间 | 实际 segment | Offset | Range | 说明 |
| --- | --- | --- | --- | --- |
| `zynq_ultra_ps_e_0/Data` | `SEG_bilinear_fixed16_buffered_0_Reg` | `0xA0000000` | 64 KiB | Bilinear AXI4-Lite control |
| `zynq_ultra_ps_e_0/Data` | `SEG_curve_image_fixed16_0_Reg` | `0xA0010000` | 64 KiB | Curve AXI4-Lite control |
| 五个 HLS `Data_m_axi_*` 地址空间，各自一份 | `HP0_DDR_LOW` | `0x00000000` | 2 GiB aperture | DDR low window |
| 五个 HLS `Data_m_axi_*` 地址空间，各自一份 | `HP0_DDR_HIGH` | `0x800000000` | 32 GiB aperture | DDR high address window |

五个 HLS master 的 `HP0_QSPI` 与 `HP0_LPS_OCM` segment 都已标记为 `is_excluded=TRUE`；最终 `get_bd_addr_segs -of_objects` 列出的有效 HLS 数据映射只有 DDR_LOW 和 DDR_HIGH。表中的窗口是 Address Editor aperture，**不是** KV260 实际可分配的物理 DDR 容量。实际缓冲区物理地址、可用区间及 cache 一致性仍需后续 PS 软件确认。本次尚未分配 A_low、A_full、model_input、enhanced 的具体地址。

## 5. 实际执行与阶段结果

Vivado batch 会话均在 Windows `cmd` 中先设置 `PROCESSOR_ARCHITECTURE=AMD64`，再调用 `E:\Xilinx\2025.2\data\settings64.bat` 和 `E:\Xilinx\2025.2\Vivado\bin\vivado.bat`。实际运行的集成/核查命令为：

```cmd
cmd /c "set PROCESSOR_ARCHITECTURE=AMD64&& call E:\Xilinx\2025.2\data\settings64.bat && call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_fixed16_stage1.tcl -log E:\HLS\vivado_fixed16_stage1.log -journal E:\HLS\vivado_fixed16_stage1.jou -notrace"
cmd /c "set PROCESSOR_ARCHITECTURE=AMD64&& call E:\Xilinx\2025.2\data\settings64.bat && call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_fixed16_stage2.tcl -log E:\HLS\vivado_fixed16_stage2.log -journal E:\HLS\vivado_fixed16_stage2.jou -notrace"
cmd /c "set PROCESSOR_ARCHITECTURE=AMD64&& call E:\Xilinx\2025.2\data\settings64.bat && call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_fixed16_stage2.tcl -log E:\HLS\vivado_fixed16_stage2_retry.log -journal E:\HLS\vivado_fixed16_stage2_retry.jou -notrace"
cmd /c "set PROCESSOR_ARCHITECTURE=AMD64&& call E:\Xilinx\2025.2\data\settings64.bat && call E:\Xilinx\2025.2\Vivado\bin\vivado.bat -mode batch -source E:\github\-\fpga\scripts\vivado_fixed16_verify.tcl -log E:\HLS\vivado_fixed16_verify_rw.log -journal E:\HLS\vivado_fixed16_verify_rw.jou -notrace"
```

上面第一轮 Stage 2 为失败排查记录，第二轮 Stage 2 完成并保存设计。另曾用 `open_project -read_only` 试图执行核查，Vivado 因 Validate 会写项目状态而报 `[Project 1-228] Project ... is read-only`；因此最终用普通打开方式核查。过程中产生的临时 `dfx_runtime.txt` 已清理，不是工程输入。

| 阶段 | 实际结果 |
| --- | --- |
| 用户保存已有 PS BD | 磁盘 `system.bd` 包含 KV260 PS、HPM0、HP0、100 MHz `pl_clk0` |
| 注册/加入 HLS IP | 两个原版打包 IP 被 Vivado 识别并加入，Stage 1 完成 |
| 复位与时钟 | Processor System Reset、`pl_clk0`、`pl_resetn0`、SmartConnect/HLS reset 连接完成 |
| 控制与 DDR AXI | 2 只 SmartConnect、2 条 AXI4-Lite control、5 条 m_axi、HP0 DDR 汇聚完成 |
| 地址分配 | 两个不重叠的 64 KiB control 区、五组 DDR low/high 数据窗口；QSPI/OCM 排除 |
| Validate Design | **PASS**：Stage 2 `validate_bd_design` 无 error；重开保存后的设计再次调用时 Vivado 提示 `Validate design is not run, since the design is already validated`，说明已保存验证状态 |
| Output products | Vivado 验证期间自动生成了部分 `.gen` 元数据 / IP 展开文件；**未执行 `generate_target all`**，未发现 BD 顶层 HDL wrapper 或完整 output products |
| Vivado synthesis / implementation | **未运行 / 未验证**；未生成 bitstream |
| 数值验证 / 板上 | 本任务未重新运行 CSim/RTL Co-sim，也未进行板上测试 |

## 6. Warning / error 与处理

1. **首次 Stage 2 失败**：Board Automation 同时开启 `M_AXI_HPM1_FPD`，但 V1 没有其外设和时钟。Vivado 报 `[BD 41-2670]` 不完整地址路径，并以 `[BD 41-758]` 指出 `/zynq_ultra_ps_e_0/maxihpm1_fpd_aclk` 没有有效时钟。将 `CONFIG.PSU__USE__M_AXI_GP1=0` 后重跑，HPM0 与 HP0 仍启用，Validate 通过。
2. **复位极性只读警告**：早期手动设置 `C_EXT_RESET_HIGH` / `POLARITY` 报 `[BD 41-737]`。这两个属性在当前 IP Integrator 连接上下文中由传播规则控制；最终脚本不再强制设置，Validate 后查询得到 `ACTIVE_LOW` / `0`，与 `pl_resetn0` 匹配。
3. **仍保留的 AXI sideband 警告**：`[BD 41-237]` 指出 PS `S_AXI_HP0_FPD` 的 `AWUSER_WIDTH=1`、`ARUSER_WIDTH=1`，而 `axi_ddr/M00_AXI` 为 0。Validate 没有因此失败；本次没有进行综合或 PS/DDR 事务测试，所以不能据此断言实际 DDR 访问已被验证。
4. **仍保留的自动配置提示**：`[BD 41-3281]` 指出 PS 与两个 HLS 实例在两侧均经 SmartConnect 连接，Vivado 不能自动按端点替它们选择所有 AXI 参数。当前端口连线和地址映射通过 Validate；需要在后续综合与事务测试中继续确认接口适配。
5. **地址排除提示**：`[BD 41-1051]` 将 OCM 的 register usage 与 HLS memory usage 判为不匹配并排除；显式排除 QSPI 后 `[BD 41-1629]` 提示 QSPI/OCM 没有地址路径。这符合当前仅走 DDR 的设计目的。
6. **工具环境提示**：`[Board 49-26]` 对一些与 KV260 无关的已安装 board definitions 报器件缺失；KV260 board part 和 PS 已正常加载。`xlconstant:1.1` 被提示可换为 inline HDL constant，属于未来版本兼容/工程体积提示，本次常量 1 的功能与 Validate 不受阻。

最后一次从磁盘重新打开工程的核查日志 `E:\HLS\vivado_fixed16_verify_rw.log` 中，所有预期 AXI、时钟和复位 net 均可查询，`HPM0_ENABLED=1`、`HPM1_ENABLED=0`、`HP0_ENABLED=1`、`PL_CLK0_MHZ=100`、`C_EXT_RESET_HIGH=0`，并输出 `SAVED_BD_VALIDATE=PASS`。没有最终 Validate error。该核查因设计已有效而未重复执行内部检查，不替代之前 Stage 2 的实际 Validate PASS。

## 7. 文件、Git 状态与结论

本次新增 `fpga/scripts/vivado_fixed16_stage1.tcl`、`vivado_fixed16_stage2.tcl`、`vivado_fixed16_verify.tcl`，用于可追溯地注册 IP、连线/分配地址及核查保存状态；修改新建中的 Vivado 工程 `.xpr`、`system.bd` 及其 IP/生成目录；新增本报告。两个 HLS 核心和之前 Fixed16 Testbench 均未修改。由于工程目录和三个脚本是未跟踪的新文件，本次无已跟踪文件差异；未执行 `git add`、commit 或 push。

**当前结论**：V1 Block Design 的预期控制、复位、100 MHz 时钟和 DDR 连接已建立，地址已分配，Vivado `Validate Design` 通过，可以提交给 Master 审核。实际 AXI DDR 事务、数值链联动、完整 output products、Vivado synthesis/implementation 和上板均尚未验证。下一步应由 Master 审核现存 AXI USER/自动配置 warning 与工程的外部 IP repository 依赖，再决定是否进入 output products / synthesis；本次停止于 Validate。

建议 Commit Message（仅建议，未提交）：`feat(fpga): integrate Fixed16 Bilinear and Curve IPs in KV260 block design`。
