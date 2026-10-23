# 2026-10-23 数值故障修正与代码自审变更清单

## 结论

原布线后功能网表精确复现真板171/192错值；定位到opt_design改变一个DSP的22-bit截断/符号扩展加数。单点恢复对照全部恢复Golden后，关闭本机Vivado 2025.2的相应DSP级联改写，从原已链接综合DCP重新布局布线。新实际routed网表四帧task=0、0、1、0全部通过。

主要自审问题是发布前没有验证实现网表数值等价，以及诊断初期对总线宽度、子模块边界、读响应节奏的假设。另发现弱符号位断言和standalone输入缓存检查不足，均已修正；它们与原硬件根因分开记录。完整审查见同目录 `implementation_assumptions_audit_20261023.md`。

## 修改的已有文件及原因

| 文件 | 修改及原因 |
|---|---|
| `.gitignore` | 仅为独立命名的修正硬件候选及其四份小图数值证据放行；不暂存或上传 |
| `.gitattributes` | 修正候选文件逐字节保存，防止Git换行转换使已核验SHA清单失效 |
| `README.md` | 标明旧版真板失败，指向独立修正候选和自审报告，区分离线通过与板端验收 |
| `docs/weather_frame_v2_contract.md` | 增加旧发布故障状态，防止继续把旧bit作为已验收版本 |
| `deployment/standalone/main.c` | 输入不变性比较前显式失效活动输入缓存，避免只验证CPU旧缓存 |
| `system/impl.tcl` | 连接OPT_DESIGN前后保护/严格检查，另导出完整routed功能网表用于数值回归 |
| `tools/build_system.py` | 复制并记录执行hook身份，记录DCP及routed网表输出哈希 |
| `tools/package_release.py` | 要求同一routed网表的四帧双任务数值门禁，收集实际输出及执行源 |
| `tools/board_artifacts.py` | collect加入同样数值门禁，verify继续兼容旧版本字节核验；检查新XSA内唯一bit与外部bit相同，不强制工具内部成员文件名 |

## 新增文件及原因

### 调查与可审查证据

- `docs/board_mismatch_20261023.md`：输入身份、逐级偏离、精确原因、单点对照、新实现和真板复测范围。
- `docs/implementation_assumptions_audit_20261023.md`：缺失信息、早期诊断错误、已补检查和未完成项目。
- 本文件：供本轮人工审核使用的修改、验证和Git状态说明。
- `evidence/board_mismatch_20261023_signature.json`、`physical_stage_comparison_20261023.json`、`dsp_cascade_causality_20261023.json`：分别记录故障特征、实际逐级比较及单点恢复因果对照。
- `evidence/routed_dsp_opmode_20261023.json`、`signedfix_routed_dsp_opmode_20261023.json`：原版和修正版18项DPREG-7的有限稳定二值检查，不宣称物理瞬态安全。
- `evidence/source_integer_contract_20261023.json`：两套冻结模型24层的源码位宽、移位、形状和保守INT32界限。
- `evidence/signedfix_release_gate_20261023.json`：真实新routed回归及六项发布门禁负对照。

### 诊断工具

- `tools/run_board_repro.py`：包内同组8×8输入的导出RTL、综合网表和实际物理父层复现；严格输出解析与执行源冻结。
- `tools/diagnostic_boundary.py`、`tools/physical_system_repro.py`：按实际端口/总线宽度保留物理父层连接，以独立PS刺激替代硬核，不伪装完整PS/DDR仿真。
- `tools/analyze_board_signature.py`、`tools/analyze_physical_stages.py`：数值特征和实际阶段比较；假设注入不作为根因证明。
- `tools/restore_diagnostic_dsp.py`：只恢复一个接收DSP的诊断Verilog副本，用于因果对照；其输出没有作为实际bit来源。
- `tools/audit_routed_dsp.py`、`tools/audit_integer_contract.py`：分别核对有限OPMODE条件和冻结源码整数界限。
- `system/export_diagnostic_netlist.tcl`、`export_diagnostic_system.tcl`、`export_linked_synthesis.tcl`：保留原实现，另导出诊断和已链接综合证据。
- `system/inspect_diagnostic_boundary.tcl`、`inspect_diagnostic_constants.tcl`：检查优化后的真实端口、驱动和常量，不靠原始RTL猜测。
- `system/trace_physical_stages.tcl`、`trace_physical_saturation.tcl`、`trace_physical_quantization.tcl`、`trace_physical_dsp_cascade.tcl`：观察已有网表信号，不force、不deposit、不补造删除位。

### 构建及发布修正

- `system/protect_weather_signed_dsp.tcl`、`check_weather_signed_dsp.tcl`：关闭经实测的DSP级联改写，逐位核对48位C来源和有效OPMODE；层次或工具条件变化时直接失败。
- `system/validate_signed_checkpoint.tcl`：旧错误检查点负对照、新检查点正对照。
- `system/optimize_protected_checkpoint.tcl`、`implement_protected_checkpoint.tcl`：从指定DCP新做opt和implementation，不覆盖旧工程或旧发布。
- `system/export_corrected_checkpoint.tcl`、`export_checkpoint_platform.tcl`：只从新routed DCP生成bit和原生XSA；保留首次路径解析失败，另在无空格工作目录成功导出。
- `tools/implementation_gate.py`：共享数值发布门禁，重新核验实际字节、任务序列、哈希、执行源及日志。
- `tools/stage_native_board.py`：原生XSA不改内容，提取其唯一bit；核对HWH/PS/驱动不变，核对与独立bit的配置payload一致。
- `tools/collect_signedfix_release.py`：收集新候选，记录原DCP、新DCP、当前未提交源码和执行快照，生成manifest/SHA清单并核验。
- `board/releases/k26_weather_v2_signedfix_20261023/`：新bit、BIN、原生XSA、HWH、PS初始化、驱动、报告、四帧实际输出、构建脚本和清单。没有另做ZIP，也不覆盖原故障目录。

## 关键差异

硬件保持原网络、权重、冻结整数规则、BD、PS配置和CSR接口，修正的是后端DSP优化选择。该选项对当前Vivado进程生效，范围包括组合系统；实际目标DSP另做严格检查。不能把选项设置成功、DONT_TOUCH设置成功或timing clean单独当作数值通过。

旧工程的impl run仍是原版本；新文件来自 `D:/weather_builds/weather_signedfix_system01/system_routed.dcp`。原故障bit/XSA/BIN、用户输入包只读保留。大体积仿真数据库和检查点留在本地D盘，不自动加入Git。

## 实际执行与未执行

已执行：

- 同一包输入的源码、导出RTL、OOC综合网表数值对照；原完整布线父层两次逐字节复现真板。
- 实际FIFO端口逐级检查、首个偏离点定位、只恢复一个DSP的因果对照。
- 关闭级联改写后的opt四帧和新routed四帧回归，4/4均192/192正确。
- 新place、phys_opt、route；100 MHz setup +0.638 ns、hold +0.010 ns，166,311条可布线net全部完成。
- 旧错误结构拒绝、新结构通过；原版及新版18个DPREG-7稳定模式检查；两任务源码24层整数界限检查。
- 实际新routed数据通过发布门禁；六项篡改/缺失负对照全部拒绝。
- 新bit和原生XSA生成；HWH/PS/驱动身份、外部/内部bit、独立bit配置payload、Bootgen BIN逐字节比较。
- Python语法编译和Git空白差异检查；最终文件清单核验结果保存于新候选manifest及本地verify命令输出。

未执行：

- 修正版真板数值复测、SDF时序仿真、物理DDR吞吐、持续720p和真实视频采集显示。
- 其他低照度master并发及其整网数值回归；诊断中它们为空闲。
- 新挂钩的全新project从create重新跑完整流程；本轮实际复用了原始已链接综合DCP。
- 修改后的standalone源代码A53 ELF编译及上板；没有新ELF、BOOT.BIN、Linux设备树或ILA/LTX。

普通DRC Warning仍存在，详见新候选README；不表述为零告警。只有离线数值和时序通过，不能标记 `board_tested=true`。

## Git 审核信息

- 当前分支：`weather_fpga_integration`，跟踪 `origin/weather_fpga_integration`。
- 当前HEAD：`c2a90a2b1f2f15d390fb32d72eae0b59842a394e`。
- 有本轮已跟踪文件修改和新增未跟踪文件；未暂存、未提交、未推送，未切换分支。与远端的关系只据当前本地origin引用，没有声称重新fetch后的远端状态。
- 建议Commit Message：`fix(fpga): preserve signed DSP boundaries and verify routed outputs`。
- 本文件及实际 `git status --short --branch`、`git diff` 供用户审核。本轮没有取得新的提交/推送授权，审核后再执行用户明确批准的Git操作。
