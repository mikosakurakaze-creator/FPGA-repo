# 联合硬件时序裕量优化记录（2026-11-02）

## 目标与边界

在现有 100 MHz / 200 MHz 时钟下扩大 setup 和 hold 裕量。网络拓扑、训练参数、整数编码、舍入裁剪、接口地址和软件调用顺序保持原合同。本次从已经通过签核的 routed checkpoint 开始做物理优化，不把降低频率或添加时序例外作为优化结果。

最新偏好（17:33 更新）：取消 WHS 0.100 ns、WNS 0.300 ns 的固定采用门槛，在原约束通过的基础上尽量扩大裕量。setup/hold 一并比较，明确一项改善而另一项下降的取舍；保留旧版及独立重开证据。完整布线、原约束时序、DRC/CDC/bus-skew 和独立重开仍须通过。当前仅优化并检查效果，不导出或打包硬件。

基线：`joint_prepare_pipeline01_20261101/joint_routed.dcp`，SHA256：
`6a0b73a19108fc6eb7dc1dd344d95a0c825b791c25826dc6ea8ce2e518b2b949`。

## 问题定位

- 最紧 setup 路径位于 D 的第三个残差块中，从卷积窗口控制寄存器到窗口寄存器的 CE。数据路径 4.711 ns，其中连线 4.226 ns，占 89.704%；窗口更新使能末级驱动 1,152 个负载。因此优先处理控制信号的布局和布线。
- 最紧 hold 路径是 CNN AXI 读地址寄存器到 SmartConnect 缓冲寄存器，数据延迟 0.225 ns、时钟偏斜 0.122 ns，原 hold 裕量仅 0.002 ns。

## 实验与选择

| 版本 | Setup WNS / ns | Hold WHS / ns | 状态 |
| --- | ---: | ---: | --- |
| 原交付基线 | 0.000 | 0.002 | 已通过原签核，保留 |
| opt01 | 0.018 | 0.002 | 原约束通过，但 hold 没改善，不选作新版 |
| opt02 | 0.203 | 0.046 | 原约束、独立重开和约束/哈希审计通过；保留候选 |
| opt03 | 无新结果 | 无新结果 | 工具拒绝在 post-route 使用 DSP/SRL register opt，失败记录保留 |
| rtl01 | 0.404 | 0.070 | 独立重开、834 条约束及 audit03 通过；作为新结构比较基准保留 |

优化阶段临时增加 setup 0.200 ns、hold 0.050 ns 的 user uncertainty，让工具继续处理贴近零的路径。这是加严优化目标，不能直接当作已经取得的裕量。结束后恢复为原来的零 user uncertainty，保留器件抖动和原时钟周期，再按正式 routed 报告验收。

opt01 发现：对已全部布线的设计执行 `route_design -tns_cleanup` 会进入 TNS 专用清理，其他路由选项被忽略（Vivado Route 35-558）。opt02 因此收集加严目标下的 setup/hold 紧路径，选择 1,998 个端点网络，工具报告实际解除 1,789 个网络，再执行正常 `route_design -directive Explore`。选择时排除承载已定义时钟的网络；D 的部分数据/控制网络使用 BUFG 高扇出布线，因此仍触发 Route 35-359 提示。后续正常路由已执行时钟拓扑修复、ILP clock placer 和 Global Clock Net Routing；最终还要以 route status、DRC 和 clock coverage 为准。原 100/200 MHz 时钟定义不变。

opt02 的 100 MHz 域 setup/hold 为 0.407/0.046 ns，200 MHz 域为 0.203/0.060 ns；LUT、FF、BRAM、URAM、DSP 用量均与原基线相同。临时加严条件下 setup 为 0.003 ns、hold 为 -0.004 ns，因此实际已取得的 hold 裕量是 0.046 ns，不能称达到 0.050 ns 目标。

## 继续扩大裕量的依据

opt02 的新 setup 最差路径已经从窗口 CE 连线转移到 D 第二个残差块入口的 `h*w`。冻结 RTL 为 32 位乘法，向 fork 的长度 FIFO 供数；这不是卷积 MAC。该路径 4.493 ns，其中逻辑 3.525 ns，经过 DSP 级联和进位链；单纯继续缩短连线的收益有限。

hold 最差路径在 CNN unpacker 的小位宽地址计算 `(in0+in1)*in2+in3`，其调用处乘数是 53。它由 DSP 内部预加器寄存器路径限制：逻辑延迟 0.114 ns、可编程连线延迟为 0，原约束下 slack 0.046 ns。因此不能宣称普通绕线一定能把它扩到 0.100 ns。

opt03 从原基线另开实验：先给工具更严格的 0.400/0.100 ns 目标，尝试 Vivado 自带 DSP 寄存器移动、SRL 寄存器优化、重定时及 clock-skew 优化，再处理外部紧路径。这一阶段没有修改 RTL；后续 rtl01 的结构调整单独记录，不能把两种实验混为一谈。

该尝试在第一次寄存器优化调用被 Vivado 4-265 明确拒绝：`-dsp_register_opt` 与 `-shift_register_opt` 不支持 post-route。后面的 clock-skew 优化并未执行，不报告它产生过收益。当前 runner 已去掉这一不可用组合；失败脚本快照及原始日志保存在 opt03。

### rtl01：保持算法/拍数的结构调整

仅在新目录 `rtl01` 派生两个生成 RTL 文件，冻结 IP 和 opt02 checkpoint 均不修改：

1. `ip/compact_d/hdl/verilog/compact_d_top.v`：完整 32 位 AXI-Lite 高宽寄存器及其参数检查保持原样。在确认 `1<=h<=720, 1<=w<=1280` 后，`frame` 的参数连接改为高度低 10 位、宽度低 11 位的零扩展。合法输入的每一位数值不变，使综合器能够消去计算域的无用高位、简化 `h*w` 和相关索引运算。未添加流水拍、不改变有效数据位宽；INT16 图像和卷积数值合同不变。
2. `ip/cnn/hdl/verilog/zero_dce_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1.v`：仅为小位宽 unpacker 地址运算加 `use_dsp="no"` 属性。原始表达式、寄存器、CE 和 reset 行为完全相同；通过普通逻辑映射避免该地址模块的 DSP 内部固定短路径。必须在新综合/实现网表核对属性是否真正生效。

`timing_variant.json` 显式记录两文件前后哈希及 `export_allowed=false`；`inputs_before_timing_variant.json` 保留派生前身份，`inputs.json` 绑定新的实验源码，不能冒充未改 RTL 的物理优化结果。

验证 `rtl01_eq06/result.json`：PASS。穷举全部 921,600 组合法高宽，检查传入 frame 的数值和 `h*w` 均相同；CNN 新旧 RTL 对照 1,056,768 周期（含 CE 停顿和 reset 切换）；XSim 对真实 D 顶层控制器执行 1,038 次合法/非法/错误 cookie 请求，返回值、启动时机和启动时的高宽参数一致。该控制器测试用确定性 frame stub 替代卷积内部，并同等移除两边不可综合的层级死锁监测代码，**不是完整 D 或六核数值仿真**。

早期测试失败另保留：eq01 为 Icarus 本机 DLL 缺失；eq02/03 为文件列表及 include 配置；eq04/05 为 Icarus 编译器内部 StringHeap 断言。CNN 对照已运行通过；D 控制器改用 Vivado XSim 后通过。未修改厂商/编译器安装。

rtl01 的 CNN 单核综合已完成：DSP 从 89 降至 87，FF 从 15,528 增至 15,600，表明两个地址计算实例的映射改变已在综合资源中体现。D 单核综合的 FF 从 31,895 降至 30,801；DSP 仍为 758，BRAM 7、URAM 40 不变。这些是 OOC 综合结果，不能当作联合布线资源或裕量。联合流程位于 `rtl01_flow01`，在当前综合结束后使用 opt02 作为增量参考，重新布局、布线、恢复原约束并独立重开检查。

本轮增量读取使用 Vivado 默认 `RuntimeOptimized`；日志明确表明它覆盖部分显式的 Explore 指令，不能把请求过的指令都写成已生效。布局后的物理优化实际执行了 DSP 寄存器移动，其中包含旧 setup 瓶颈的 D `residual_block_1_Block_entry_proc_U0` 尺寸乘法。两条 Vivado 12-8060 Critical Warning 提醒临时 user uncertainty 会影响增量实现运行时间；本轮没有按建议将它忽略。实测本机 2025.2 配置中 `incr.ignore_user_clock_uncertainty=0`。这类优化过程警告与最终 DRC/时序违例分别记录，最终仍按恢复后的原约束和独立重开结果验收。

### 尺寸乘法入口缩窄的独立验证

rtl01 的布局后报告中，第二个残差块入口仍保留 32 位尺寸乘法的 DSP 级联/进位结构，说明只在 D 顶层截断参数并不足以确保经过 FIFO 后的算术结构完全缩窄。为准备后续结构优化，新增 `scripts/probe_dimension_multiplier.py`，在独立目录派生 12 个直接 `h*w` 调用。宽度操作数改为 `{1'b0,w[10:0]}`（12 位），高度改为 `{1'b0,h[9:0]}`（11 位）；前导零保留原有有符号乘法的非负语义，输出仍为 32 位，控制器、握手和寄存器拍数不变。卷积步数和 NCHW 地址乘法不在本探针的修改范围内。

`dimension_probe02/result.json`：PASS。对实际原乘法 RTL 与缩窄参数版本穷举 921,600 组合法高宽，输出逐位一致。局部 OOC 综合中，原乘法使用 3 个 DSP，缩窄后使用 1 个 DSP。该结果只证明这一局部结构的数值等价和资源映射，**尚未纳入 rtl01 联合实现，也不代表完整 D 或系统时序已通过**。`dimension_probe01` 的数值对照已经通过，但其初版统计把一个 DSP 展开的内部子单元重复计数，导致统计门失败；修正为本纯乘法探针中的 `DSP_MULTIPLIER` 计数后重跑得到 probe02，原失败记录保留。

### 安全线与额外目标

rtl01 最终 routed DCP 的 SHA256 为 `8a2a3f454ded05832cc63733f959988bd850dd7ca0610f726645b0772222b94a`。100 MHz 域 setup/hold 为 0.459/0.070 ns，200 MHz 域为 0.404/0.070 ns；192,892 条可布线网络全部完成，布线错误为零。LUT 86,111、FF 96,427、BRAM tile 100、URAM 58、DSP 946；相对 opt02 分别变化 -274、-952、0、0、-2。最终 setup 最差路径已转到 D `read_nchw` 控制器，不能继续将 `h*w` 描述为最终瓶颈。

首版自动审计因未分类的 Route 35-39 停止，失败 `audit.json` 和流程结果保留。该提示发生在临时加严 0.400/0.100 ns 的布线过程中；加严条件下 hold 为 -0.030 ns，恢复原合同后为 +0.070 ns。补充分类后在新文件 `rtl01_flow01/audit02.json` 完成审计：仍强制原约束一致、正式时序通过、独立重开一致及全部 route/DRC/CDC/bus-skew/clock 检查，不将临时目标未达冒充目标通过。

### hold 专项追加轮（执行中）

用户要求再做一轮全力 hold 优化。以已审计的 rtl01 为参考，先量化剩余短路径。当前最差路径位于 SmartConnect XPM FIFO 的 RAMD32 输出到同 SLICE FDRE 的 D 端：数据逻辑 0.118 ns、连接 0.009 ns。Vivado Route 35-426 明确指出站内/专用连线无法用普通绕线继续增加延迟。因此本轮重点是消除这类连接的最短路径下限，随后重布线；保持 100/200 MHz、算法、接口、周期行为，按原约束同时验收 setup。新增 `scripts/inspect_hold_floor.tcl` 生成全部低于 0.150 ns 路径的器件类型、位置和延迟分类。具体候选及结果以下续记录为准，尚不导出硬件包。

`hold_floor01` 抓取最紧的 50,000 条路径，末条 slack 为 0.124 ns；0.150 ns 的查询触及数量上限，不能把它称为所有低于 0.150 ns 路径的完整枚举。在已覆盖的 <0.100 ns 区间，共 6,905 个端点：6,794 条 RAMD32/RAMD64E 到同站 FDRE，另 111 条属于同一个 CNN DW 窗口小地址运算 DSP 的内部路径（最小 0.077 ns）。因此仅改变 FIFO 连接还会被该 DSP 限制。

新派生 `rtl02` 保留 rtl01 两处改动，另对 `zero_dce_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1.v` 的内部运算模块加 `use_dsp="no"`。所有表达式、寄存器、CE 和复位行为保持。`rtl02_eq01` 通过：新增地址模块穷举 8,192 种输入并追加停顿/复位序列，共 16,384 周期；原地址模块 1,056,768 周期、D 顶层 1,038 事务和合法尺寸穷举也重新通过。CNN OOC DSP 87→86；这不是联合 routed 资源结论。

FIFO 方案由 `scripts/fifo_hold_eco.tcl` 在新实验网表中实施：对 setup 尚有足够余量、且 hold 紧张的 RAM→FDRE D 端连接加入真值表 `INIT=2'h2` 的 LUT1（O=I），再进行 ECO 布线。它是组合恒等连接，不新增寄存器或流水拍。记录并逐项核对原驱动、其他负载、目标 D 端，以及目标寄存器的 C/CE/R/Q；插入前后及独立重开还要核对 primitive 集合。新缓冲器需要额外 LUT，最终是否采用必须同时看 hold 收益、setup 和资源。先执行 8 条路径的隔离探针，尚不把方案视为已验收。

`hold_probe01`、`hold_probe02` 均在空闲 LUT 位置选择阶段停止，尚未修改任何网表连接；失败记录保留。独立只读 `bel_query01` 用小型复位核检查点核实：本机 Vivado 2025.2 的 BEL 属性为 `IS_USED`，并无 `IS_OCCUPIED`；原过滤表达式静默返回空集合，不能据此判断资源不足。已改为同时检查 `IS_USED=0`、`IS_RESERVED=0`、`PROHIBIT=0`，并要求同一 LUT 的 5LUT/6LUT 均可用。

`hold_probe03` 使用修正后的选择器，八个恒等 LUT 的逻辑连接检查通过，但 `route_design -eco` 失败，产生 Route 35-583 及原 RAM 站点的物理引脚映射错误；未产生可采用候选。该失败属于本轮 ECO 连接方案，不代表已验收的 rtl01 出现这些错误。完整失败日志保留，不启动此方案的全量插入。

`rtl02/synth_result.json` 已 PASS，联合综合检查点完成，尚未完成新一轮联合布线。

### 更新验收目标：setup 至少 0.300 ns，hold 至少 0.100 ns

2026-11-02 用户明确允许以部分 setup 裕量换取 hold，最终采用门改为原有效约束下 `WNS>=0.300 ns && WHS>=0.100 ns`，时钟仍为 100/200 MHz；不以简单的“两项均较 rtl01 提升”作为采用要求。约束完整性、route、DRC、CDC、bus-skew 和独立重开要求继续执行。

改用现有 FIFO 输出 FDRE 的局部物理移动探针：移出 RAM 的同站专用短连接，选择同一 clock region 内未使用 FF 的 SLICEL；同一目标站仅打包时钟、使能、复位连接完全相同的寄存器。保留全部 primitive 和逐引脚逻辑连接，不加 LUT 或流水拍。检查移动前、移动后、布线后及独立重开的证据。

`hold_relocate01` 在未设置 DONT_TOUCH 属性的空字符串布尔判断处停止；`hold_relocate02` 完成八个寄存器移动，但验证函数把序列化名字当作对象集合传给 `get_pins -of_objects`，工具拒绝后停止，未取得布线结果。两次失败均保留。已修正显式对象查询，并将可用站选择从整站空闲改为 FF 资源空闲，避免无谓占用大量空站；`hold_relocate03` 是当前执行中的八点探针，尚未取得结果。

后续 `hold_relocate03/04` 均因目的位置的共享 LUT 输入资源不兼容而停止。仅检查 5LUT 的 IS_USED 并不足够，LUT6_2 也可能占用共享资源；`hold_relocate05` 最终要求目标 FF 对应 5LUT/6LUT 均未使用。该八点探针已 PASS：逻辑连接、原始 primitive 集合、完整布线和 DRC 均通过；八条原 0.070 ns 路径的 hold 为 0.209/0.283/0.361/0.523/0.269/0.281/0.270/0.294 ns，对应 setup 为 7.455/6.406/6.548/6.338/6.562/7.106/7.164/6.526 ns。这里只是八条局部路径改善，不代表整机 WHS 已达到 0.100 ns。

保守手工筛选在参考网表仅能提供 3,642 个 FF 槽，少于需要处理的 6,794 个 FIFO 端点。因此全量候选不继续硬编码 BEL。新增 `fifo_hold_floorplan.tcl`，在新综合网表为这 6,794 个已定位端点建立临时的 SLICEL-only 硬 Pblock，由 Vivado 原生布局器统一安排合法 FF/LUT/控制集；不排他占用区域，不增加流水拍。布局后、布线后及独立重开逐引脚核对目标 FDRE 的逻辑连接及类型。最终报告前删除临时 Pblock，仍须逐条匹配原有 834 条有效约束，不允许将物理放置手段变为额外时序例外。

`rtl02_flow01` 已启动联合实现，优化目标为 setup 0.300 ns / hold 0.100 ns。输入绑定 `rtl02_eq01`、`rtl02/synth_result.json`、`rtl01_flow01/audit03.json` 以及 `hold_relocate05` 的已通过探针；尚未获得最终联合 routed 结果。审计解析器的十五项正负测试已通过，该测试不代替 Vivado 实现或真板验证。

`rtl02_flow01` 的布局命令完成，但布局后强制检查发现目标仍在 SLICEM，立即停止。日志 Place 46-12 明确表示增量流程因旧位置复用优先级较高，忽略了全部 6,794 个新 Pblock 约束；不能把“place_design 成功”当作本方案生效。该失败连同原始日志保留。

用户明确本轮采用门为 WHS >= 0.100 ns 且 WNS >= 0.300 ns，允许 setup 相对 rtl01 的 0.404 ns 下降；仍保持 100/200 MHz 和原约束。`rtl02_flow02` 因 opt_design 后旧时钟对象句柄失效而停止，修正为重新查询并核对时钟。`rtl02_flow03` 已正确识别两个时钟并完成 opt_design，但新布局失败：Place 30-642 将 RAM32M16 的 RAMD32/RAMS32 与关联输出 FDRE 构成单站 shape，和仅限 SLICEL 的寄存器 Pblock 不相容。没有生成新 routed 候选，不把它记作时序改善。`fifo_shape01` 只读检查确认样本没有用户 macro/LOC/BEL 绑定；下一步检查 routed 设计中可移动寄存器的合法容量，保留本次所有失败证据。

`relocation_capacity01` 只读统计通过。在同时要求 LUT5/LUT6 资源空闲的情况下，SLICEL 空 FF 站有 3,642 槽，SLICEM 空 FF 站有 2,256 槽；只含相同 C/CE/R 的 FDRE 的 SLICEL/SLICEM 站另有 2,254/1,354 槽，共 9,506 个保守可选槽。此总量尚未考虑每组控制信号、clock region、距离和具体放置合法性，不能当作 6,794 个目标一定可全量移动的证明。新增 `fifo_hold_relocate_dense.tcl` 和可显式选择、冻结并核对哈希的 helper 参数，不修改原 `hold_relocate05` 的 helper。`hold_relocate_dense01` 已合法移动来自七个顶层模块的八个代表寄存器，但检查器将 Vivado 返回的 `SLICEL.AFF` 和放置命令的 `AFF` 直接比较而停止，尚未布线；修正为核对站类型加 FF 槽，失败目录保留，重新运行局部试验。

`hold_relocate_dense02` 已完成八条代表路径的移位、ECO 布线、DRC、完整路由检查及 primitive/逐引脚连接核对，result.json 为 PASS。各路径 hold 由 0.070~0.085 ns 增至 0.192~0.590 ns，对应路径 setup 最低 1.561 ns；这是八条局部路径的结果，全局尚未达到 hold 目标。helper SHA256 为 `3e33b871025d0fea5006ea8d2d27f3e335b2bf35459c9d7c5146b8d3b0bd8359`，移位前、移位后和布线后 primitive 清单哈希完全相同。覆盖 bilinear_ddr_sc、cnn_data_sc、cnn_model_sc、Compact D、curve_ddr_sc、Prepare 和 CNN 内部缓冲。

`rtl02_flow04` 采用已通过的 rtl02 综合、等价证据及 dense02 helper 启动全量增量实现。此处不采用失败的 SLICEL Pblock；由真实新实现的低于目标路径动态选取 RAM→同站 FDRE 候选，排除 setup 紧路径的起点/终点，再移动现有寄存器。独立重开及最终审计须同时确认 WNS >= 0.300 ns、WHS >= 0.100 ns，不能用局部试验或临时加严报告代替。

重现命令：

```powershell
& 'C:/Users/wzh16/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -X utf8 -B `
  'D:/github clone/feat-software/fpga/joint_lowlight_compact_d/scripts/run_timing_variant_flow.py' `
  --build 'D:/weather_builds/timing_margin_20261102/rtl02' `
  --equivalence 'D:/weather_builds/timing_margin_20261102/rtl02_eq01' `
  --reference-audit 'D:/weather_builds/timing_margin_20261102/rtl01_flow01/audit03.json' `
  --out 'D:/weather_builds/timing_margin_20261102/rtl02_flow04' `
  --strategy preplace_relocate `
  --hold-probe 'D:/weather_builds/timing_margin_20261102/hold_relocate_dense02' `
  --relocation-helper 'D:/github clone/feat-software/fpga/joint_lowlight_compact_d/scripts/fifo_hold_relocate_dense.tcl' `
  --setup-margin 0.300 --hold-margin 0.100
```

该命令的输出目录必须尚不存在，复现实验须使用新的目录名，不覆盖本次收据。

`rtl02_flow04` 的初始联合布线成功，在加严 setup 0.300 ns 条件下 WNS 为 0.040 ns（恢复原约束对应 0.340 ns，但还不是最终采用结果）。动态查询得到 6,811 个 hold 紧端点，6,732 个进入原移位候选、79 个因 setup 敏感被旧策略排除。原位网表有 9,256 个保守可选 FF 槽；实际移位时仍遇到 Vivado 12-1409（目标 HFF 的 OUTMUXG 路由资源争用），所以整个实现阶段为失败，没有最终 routed 候选，不能将初始布线值当作完成验收。

新增 `fifo_hold_relocate_dense_v3.tcl`：保留每个候选试放的开始/结束标记、原始工具消息、返回码及表格，只允许明确拒绝的 12-1409 候选恢复原位置后改试其他槽；成功放置的寄存器仍须检查位置和逐引脚逻辑连接。`relocation_before_moves.dcp` 在移位前保存，容量不足时另存失败快照。`fifo_hold_relocation_collect_v2.tcl` 记录并优先处理 setup 敏感端点，不再将它们直接排除，最终仍以真实全局 setup >= 0.300 ns 为采用门。`hold_relocate_dense03` 在负对照前因当前 Vivado 不提供通用 redirect 命令而停止；保留失败并改用原始控制台内的显式 trial 标记，不屏蔽或降低任何工具消息等级。`hold_relocate_dense04` 正在重新验证包含占用 BEL 负对照的八路径试验。

增加从已保存 `tightened_physopt.dcp` 继续的参数，绑定原失败实现的综合来源、日志、脚本、原退出状态和新输入哈希，不把失败重标为成功；独立审计还须比较继承的加严约束和最终恢复的原始约束。诊断解析器扩为 25 项正负测试并通过，覆盖正式错误、非预期试放错误、错误的成功标记、缺失 trial 结束和未恢复的最终 uncertainty 等拒绝条件；这仍不是 FPGA 签核。

第二轮运行库去重收据为 `runtime_dedup_second_20261102.jsonl`：仅七个已结束的实验目录中 2,037 个相同 exe/dll 副本，逐文件核对 SHA256 后共享硬链接，释放重复内容 11,440,609,362 字节。所有实验路径、日志和失败记录均保留。

`hold_relocate_dense04` 的占用 BEL 负对照确实被拒绝、原位置/连接恢复，但 Tcl catch 返回的完整错误没有自动写入控制台 trial 区间；已明确停止该次尚未完成的探针并保留非零退出收据，不补写旧日志。`hold_relocate_dense05` 使用显式 `puts $reason` 后完成并 PASS：原始 console 内一个预期 12-1409 负对照、八个成功移位 trial，完整路由、DRC、primitive/逐引脚连接及八路径时序检查通过，数值仍为 hold 0.192~0.590 ns、对应 setup 最低 1.561 ns。实际采用的 helper SHA256 为 `9597613d77334575037c757d72729e69caaefa72c0bf3d00299e28ecbfddc99c`。

`rtl02_flow05` 从 flow04 已保存的 `tightened_physopt.dcp` 继续，跳过综合、逻辑优化和布局；绑定原失败收据及新输入哈希，保留原 0.300/0.100 ns 临时加严目标。使用上述已通过 helper 与 collect_v2，不再直接跳过 setup 敏感端点，并在初始布线完成后立即保存完整路由检查点，避免后续位置拒绝导致重复初始布线。尚无新的最终联合时序结果。

flow05 恢复后已额外执行约束预检查：除继承的两条临时加严 uncertainty 外，其余 834 条有效约束与原 routed 合同逐条相同。此检查不替代最终恢复/独立重开的约束及裕量审核。

`rtl02_flow05` 随后完成初始布线并保存 `implement01/initial_routed_candidate.dcp`，动态识别 6,811 个目标，其中 79 个 setup 敏感目标优先处理、没有直接跳过。v3 正确记录并恢复了不合法位置，但在成功移动 92 个寄存器后因局部兼容位置不足停止；保留原失败状态和部分移动快照。9,256 个保守槽只是总量，按控制组、clock region 和距离分布后不能保证全量可用。后续实验从未移动的初始 routed checkpoint 恢复，避免重复综合、布局和初始布线，不采用部分失败快照。

新增 `scripts/fifo_hold_relocate_native_v4.tcl`：枚举同 clock region 内未占用的 FF 槽，距离上限为 80 个 SLICE 的 Manhattan 距离，由原生 `place_cell` 校验完整站内资源，而非要求整个站的 C/CE/R 都一致或 LUT5/LUT6 都空闲。候选被拒绝时保留原始消息并恢复位置与连接；没有增加 primitive、改变逻辑连接或增加流水拍。`hold_relocate_native01` 已通过占用 BEL 负对照，完成八个代表寄存器的合法移动（121 次位置拒绝均保留），正在 ECO 布线；尚无最终时序结果，不能视为局部或全局目标通过。

2026-11-02 本次接续时重新执行 `test_hold_eco_audit.py` 的 25 项正负解析测试，全部通过。当前已独立重开审计的完整候选仍为 rtl01：原约束下全局 WNS 0.404 ns、WHS 0.070 ns；setup 满足 0.300 ns，hold 尚未达到 0.100 ns。当前没有 setup/hold 负 slack，不把额外余量目标未达成表述为已经发生功能故障。

用户随后询问 rtl01 是否已有交付包，并要求如无则继续当前优化。只读检查确认该版本没有 bit、bit.bin、XSA 或完整 ZIP，仅有 routed checkpoint、报告和独立审计。现有 `D:/weather_builds/kv260_joint_prepare_pipeline_delivery_20261101.zip` 是更早的版本，其独立验证记录为 WNS 0.000 ns、WHS 0.002 ns，不能标为 rtl01 的交付物；本次继续优化，不新导出或打包。

`hold_relocate_native01` 于 13:27 完成并 PASS：8 个目标的 hold 为 0.450/0.179/0.395/0.171/0.465/0.133/0.197/0.499 ns，对应 setup 最低 1.943 ns。完整路由、DRC、移动后/布线后逐引脚连接和 primitive 集合检查通过；122 次拒绝包括占用 BEL 负对照，原始消息保留。该探针只证明 8 条被移动路径，不能将其最小 hold 当作全局 WHS。helper SHA256 为 `07e4bca44eb9b5fd394faf6b9a32845e074cbc2558d189c21302a9fddca2df66`。

`rtl02_flow06` 已从 flow05 的初始 routed checkpoint 恢复，采用上述已通过 v4 helper 和 collect_v2。除同源综合/等价/原基准审计外，继续核对恢复祖先的原始失败记录和新输入 SHA256，跳过综合、opt、place、physopt 及初始 route，直接执行全量寄存器移位及后续布线。只有最终恢复原约束、独立重开、全局 WNS >= 0.300 ns 且 WHS >= 0.100 ns 才满足采用目标；尚未获得结果。

flow06 动态选择仍为 6,811 个目标、79 个 setup 敏感目标优先处理、其他短路径 0、直接跳过目标 0。恢复约束与 rtl01 的 834 条有效命令比较通过：仅归一化已审核的 CDC waiver 创建时间，所有约束参数、例外和作用域保持逐条相同；继承的临时加严仍为 setup 0.300 ns / hold 0.100 ns。当前位置枚举正在执行，最终还须恢复 user uncertainty 并独立重开检查。

flow06 于 13:44 自行失败退出，仍在第 93 个目标（curve_ddr_sc/s05 AW FIFO 的输出位 172）因原生 RAM32M16/FDRE shape 限制耗尽合法位置；13:43 的中间记录已包含 12,062 次拒绝、92 次成功。保留原始失败收据及 `relocation_partial_failed.dcp`，未采用此部分候选。定位表明该目标的问题不是空闲 FF 总量不足，继续枚举不能解除原生固定组合关系。

`shape_tools01` 为公开工具能力只读查询：没有可用的 shape/unpack 命令，`delete_macros` 只处理用户 macro，不把它当作解除原生 RAM packing 的办法。新增 `fifo_hold_recreate_v5.tcl` 和 `fifo_hold_recreate_probe.tcl`：针对 FDRE 重建同名、同类型实例，逐引脚保持 C/CE/D/R/Q 连接，规范化并保持 INIT、时钟/数据/复位反相参数，尝试解除旧内部对象的 packing 关系；不增加寄存器或拍数。位置枚举改为按 clock region 批量获取站点，并核验覆盖；遇到重建后仍有 shape 限制立即停止，避免万次无效重试。`hold_recreate01` 在原始未移动的 flow05 初始 routed 检查点上试验，八点包含上述确切失败目标，尚未得到布线/时序结论。

用户授权仅在后续存储空间不足时清理 weather_builds 中不影响最近三个版本的冗余旧构建；同时保留 rtl01 已验证基准及采用候选的依赖证据。当前尚有约 17 GB 空间，没有执行删除。

`hold_recreate01` 于 14:03 失败，未开始布线；完成 137,294 个空 FF 的位置表后，在首次重建时遇到 Common 17-55（空对象的 get_property）。保留日志，不将其归因为时序或重建方法本身已失败。新增带步骤诊断的 `fifo_hold_recreate_debug_v6.tcl` 与 `fifo_hold_recreate_single_probe.tcl`，在 `hold_recreate_single01` 只检查确切失败的 curve FIFO 位 172，省略全器件位置扫描，并将待重建实例名物化为普通字符串，避免删除旧对象后仍引用其内部句柄。该最小试验先核对逐引脚连接和四个功能参数，再测试一个旧记录中空闲的位置；尚无最终结果。

用户随后要求不再检查内存，集中完成项目；后续停止例行内存/磁盘检查，继续时序工作。

`hold_recreate_single01` 于 14:08 PASS：确切失败的 curve FIFO 位 172 在同类型重建后可放入旧试验被 shape 拒绝的 `SLICE_X48Y208/DFF2`；重建前后逐引脚连接及 INIT/反相参数文件的 SHA256 完全相同。该单点试验只证明功能参数与放置，不含布线或时序通过。

新增 `fifo_hold_recreate_lazy_v7.tcl`，修正删除旧实例后的对象名引用，按访问过的相邻站点缓存 FF 空闲与 clock region，省略全器件位置池。`hold_recreate_lazy01` 已完成八点重建/移位，包含确切 shape 失败目标，进入真实 ECO 布线。验证表独立记录原始参数和重建后参数，D 的样本 `IS_R_INVERTED=1` 被明确保留。`run_timing_variant_flow.py` 与 `audit_timing_variant.py` 要求重建方案的参数覆盖完整、前后及独立重开一致；新增重复、未知值、缺失和参数变化负对照后，30 项解析测试 PASS。该解析测试仍不代表硬件时序通过。

`hold_recreate_lazy01` 于 14:18 PASS，八条目标 hold 0.446/0.179/0.395/0.171/0.363/0.133/0.392/0.216 ns，对应 setup 最低 1.943 ns。确切 shape 失败位 172 的 hold 为 0.216 ns、setup 为 6.929 ns。primitive 集合、逐引脚连接、四个功能参数、完整布线和 DRC 检查通过；不把这八点的最小 hold 当成全局 WHS。helper SHA256 为 `a14b8d281fef3ea9b6cf902e69446338e543576f6a20d8be8cf3e2a0e5db5bfd`。`rtl02_flow07` 已使用此已通过 helper、collect_v2、rtl02 综合/等价和 flow05 未移位的初始 routed 检查点启动全量优化，尚无全局最终结果。

flow07 于 14:25 失败，成功完成 93 个寄存器，已越过原 curve 位 172 的 shape 卡点；第 94 个目标在搜索无空闲 FF 的站点时触发 Common 17-55。根因是 `get_bels` 返回空列表后仍传给 `get_property NAME`；新 `fifo_hold_recreate_lazy_v8.tcl` 仅加空列表返回保护，旧 v7 和失败证据不覆盖。`hold_recreate_lazy02` 使用 `fifo_hold_recreate_probe_v2.tcl`，包含原 shape 目标、该第 94 个 CNN Model FIFO 目标，并显式找到无空闲 FF 的站点验证查询应跳过；其余连线、功能参数、布线、DRC 和局部时序采用门不变。

`hold_recreate_lazy02` 于 14:36 PASS：显式空 FF 负对照为 `SLICE_X10Y53`，八点全部完成布线/DRC/primitive/连线/功能参数检查。目标 hold 为 0.446/0.179/0.395/0.171/0.363/0.133/0.161/0.216 ns，对应 setup 最低 1.943 ns；第 94 个 CNN Model FIFO 目标 hold 为 0.161 ns、setup 8.084 ns。helper SHA256 为 `aeb085f329b8418ef393e27d73ad6d2e962a70f6d875a79cc26182813094cc0d`。`rtl02_flow08` 采用此 passing probe 和同 helper，从原 flow05 初始 routed 检查点继续全量优化；尚无全局最终结果。

flow08 于 14:48 在完成 499 个目标后失败：第 500 个 CNN Data s02 R FIFO 位 50 已重建，但 512 次原生试放均因 CE/复位或共享线路不兼容，触发有界重试保护；不是旧 shape 或空列表问题复发。失败快照与 14,691 次拒绝、499 次接受的完整诊断保留。新增 `fifo_hold_recreate_control_v9.tcl`：缓存半 SLICE 内的 FDRE 时钟/复位及各 FF 组使能连接与反相参数，预先过滤明确不兼容的候选，剩余仍由原生放置器检验；不把筛选器视为合法放置证明。原生重试上限改为 4,096，shape 错误仍立即失败。`hold_recreate_control01` 的八点包括该第 500 个目标及前两个失败目标，并用人为不匹配的复位签名验证筛选器拒绝条件；尚在验证中。

### 本轮文件与验证范围

- `scripts/fifo_hold_relocate_dense.tcl`、`fifo_hold_relocate_dense_v3.tcl`、`fifo_hold_dense_probe.tcl`、`fifo_hold_dense_probe_v3.tcl`：新增保守共享站点的现有寄存器移位、原始候选诊断、占用 BEL 负对照及八路径布线验证；原已通过 helper 和原安全候选不覆盖。
- `scripts/fifo_hold_relocate_native_v4.tcl`：扩大候选位置，由原生放置器判定完整合法性，保留拒绝、恢复、连接和 primitive 核验；当前八点探针仍须完成真实布线和时序检查。
- `scripts/fifo_hold_relocation_collect_v2.tcl`：新增 setup 敏感端点记录和优先选择，取消旧策略对这些端点的直接排除；最终全局 setup 门不变。
- `scripts/inspect_fifo_shapes.tcl`、`inspect_fifo_relocation_capacity.tcl`、`inspect_placement_trials.tcl`：只读定位 RAM/FF shape、物理位置容量及当前工具接口。
- `scripts/optimize_timing_margin.py`、`run_timing_variant_flow.py`、`timing_margin.tcl`：新增显式版本 helper/collector、绑定检查点来源的物理恢复及初始布线后的保存，避免重复已完成阶段。
- `scripts/audit_timing_variant.py`、`verify_timing_margin.py`、`test_hold_eco_audit.py`：区分临时加严与最终恢复状态、核对完整候选诊断和独立重开，25 项解析正负测试已通过，禁止将正式错误或未恢复约束当作通过。
- `scripts/deduplicate_probe_runtimes_second.ps1`：只对已结束实验中哈希一致的运行库副本共享硬链接，保存逐文件收据；不修改工具安装或删减证据。

本轮实际执行了原始工程只读检查、器件位置检查、上述 25 项解析测试，以及 dense02/dense05 的八路径真实移位、布线、DRC 和连接检查。rtl02 的源码等价及联合综合沿用先前已经完成并被本轮绑定的证据，不称作本轮重跑。尚未执行新的完整六核端到端仿真、板端数值/性能测量或 30 FPS 验证；未导出 bit/XSA 或打包。

建议 Commit Message：`Improve joint FPGA hold margin with verified FIFO placement`。当前分支为 `feat/software`，联合工程目录在 Git 中仍为未跟踪；本轮没有 add、commit、push、切分支或 PR 操作。最终结果应在下方继续补记，当前运行状态不代表目标已达成。

运行输出空间维护记录：`runtime_dedup_20261102.jsonl` 对已结束的十个失败/只读实验中 2,910 个 exe/dll 副本先比较 SHA256，再用硬链接共享完全相同的内容，释放重复占用 16,343,727,660 字节。所有路径、原始日志和失败收据保留，未修改工具安装或当前实现源码。

独立小设计工具查询保留在 `incremental_config01` 和 `place_options01`：当前公开实现配置没有逐目标取消复用的入口；工具自己在旧错误中的 `place_design -cells` 建议也已被 2025.2 废弃，查询调用被拒绝，不视为通过。`rtl02_flow02` 因此直接使用已通过的新综合网表和原生 Explore 布局，参考 DCP 仅用于身份、约束、时序和资源比较，不再加载其增量位置。布局完成立即保存 `placed_candidate.dcp`，随后强制核对 6,794 个目标确实位于 SLICEL 且连接不变，再继续布线。

首次 `hold_floor01` 的旧 runner 尚未把 TSV 加入报告哈希清单；当前实验将其路径分类表作为新的放置输入绑定 SHA256，核对旧诊断的来源 checkpoint 和已有报告哈希，并明确记录这一证据边界。不能声称分类 TSV 的哈希已由旧收据继承。最终是否采用仍由新实现完整签核及独立重开决定。

本项目暂以 setup 0.3~0.5 ns、hold 尽量 0.05~0.1 ns 作为工程余量目标，这不是厂商通用安全阈值。原约束下所有有效路径通过、多角时序分析及 clock/reset/CDC/route 检查完整，是结论的前提。内部固定 DSP 路径的正 slack 不能仅因数字小就判定不安全；较大的 slack 同样不能替代正确约束或真板验证。降低频率通常有助于 setup，却不能普遍修复同边沿的 hold 问题。

setup 的改善需要降低一个周期内的最长路径延迟或减少不利时钟偏斜；hold 的改善需要使最短路径满足同一时钟边沿的保持要求。两者必须同时验收，不能简单地把所有连线缩短，也不能把增加 uncertainty 的数值当成真实收益。

用户要求先看优化效果：本轮暂停 bit、bit.bin、XSA 和 ZIP 的导出/打包，不更新旧交付物，不推送远端。

## 约束与验证

- 对原 XDC 与恢复后的 XDC 逐条比较。Vivado 会保留 uncertainty 的设置历史，因此只允许已知的“加严 setup、加严 hold、恢复 setup=0、恢复 hold=0”四条顺序；最终 `report_clocks` 也必须证实两时钟均恢复为零 user uncertainty。
- 原有 834 条有效约束命令保持一致；忽略注释和重复的空 `current_instance -quiet`，不忽略时钟、例外或最大延迟约束。
- rtl01 必须在相同阶段比较约束。综合检查点还包含随后被 `opt_design` 清除的 SmartConnect 复位/FIFO 结构，其 `write_xdc` 为 1,149 条命令，不能直接与原 routed 的 834 条按行比较。已从原、新 `joint_synth.dcp` 提取全部三份编译 XDC：board 52 行、early 133 行、late 7,289 行一致。只归一化 waiver 创建时间，以及验证绝对路径、相对路径、工程变量路径指向同一文件后得到的来源元数据；时钟、例外、数值、查询和作用域逐字保留。最终 routed 仍须与原 routed 合同比较，不允许因阶段差异而跳过最终约束审核。
- 优化后的 checkpoint 单独保存。必须重新通过 setup/hold、完整布线、DRC、CDC、bus-skew、未使用 PS 时钟输出分类和导出时复核，才允许生成新版交付包。
- `verify_timing_margin.py` 要求 setup 与 hold 均优于原基线，避免仅更换文件却没有获得两项改善。
- 原 prepare/fusion 的 Golden、RTL 仿真及主机测试证据仅作为相同源码的历史证据继承，不记作本轮重新执行。物理实现变换由 Vivado 完成；本轮没有新增全六核联合 RTL 仿真或真板测试，不能据此宣称整机达到 30 FPS。

## 文件与重现

- `scripts/optimize_timing_margin.py` / `scripts/timing_margin.tcl`：隔离诊断、加严目标、物理优化、重布线、恢复原约束和生成报告。
- `scripts/verify_timing_margin.py`：比较原约束、实际裕量、布线和 DRC/CDC/bus-skew，绑定 checkpoint 与日志哈希。
- `scripts/prepare_timing_variant.py`：在独立构建中派生两处 RTL 改动并绑定前后源码身份。
- `scripts/verify_timing_variant.py`：限定变更检查、尺寸穷举、CNN 周期对照和 D 控制器 XSim 对照。
- `scripts/run_timing_variant_flow.py`：衔接已经启动的综合、独立实现、重开和审核，没有 bitstream、XSA、打包、Git 或板卡阶段。
- `scripts/audit_timing_variant.py`：绑定派生 RTL、等价检查、新综合和独立重开证据，比较原时钟/约束及两项裕量，并从真实报告提取逐时钟域时序和资源变化；原约束通过与是否达到额外裕量目标分开报告。
- `scripts/inherit_timing_build.py`：在新目录继承原始源码和真实历史构建证据；新实现阶段明确标识为 post-route 物理优化。
- `scripts/finish_timing_delivery.py`：串接独立审核、coverage、acceptance、导出、收集和 ZIP 独立验证。
- `scripts/collect_delivery.py`：支持上述构建继承关系，将优化和基线证据一并放入交付包。

所有实验位于 `D:/weather_builds/timing_margin_20261102/`。失败记录与未采用候选保留，旧 ZIP 不覆盖。

### 15:10 后的布线修正

用户明确取消内存巡检，后续只推进工程优化，不执行例行内存/磁盘检查。

`hold_recreate_control01` 完成 8 个寄存器放置（29 次原生拒绝、320 次控制签名预筛选），但 ECO router 的资源重叠从 69 扩大到 211,907，setup 中间值恶化至 -4.238 ns。为避免继续全局扩散，于 15:10 核对进程命令属于本实验后停止该 router。原始失败 result/log 与移动前后 checkpoint 保留，未将八点放置或中间时序视为通过。

`recreate_route_diagnosis01` 只读重开已移动 checkpoint，确认移动后有 37 条路由错误网络，包含 12 条资源冲突；部分目标 SLICE 的新 FF 输入占用了已有 LUTRAM 地址的站点引脚。该诊断通过只表示报告生成完成，不表示候选可采用。新增 `fifo_hold_recreate_logic_v10.tcl` 将目标限定为 SLICEL，避免新 FF 进入已有 LUTRAM 所在的 SLICEM；重建仍保持同名 FDRE、五个引脚、四个功能参数和原有流水拍数。`hold_recreate_logic01` 使用包含第 500 个失败端点的八点探针，并以 `route_design -preserve` 保留其他完整路由；结果待实际布线与报告。另在 `recreate_preserve01` 独立尝试对 v9 已移动快照保留完整路由进行修复，原 v9 失败状态不变。

`recreate_preserve01` 独立修复 PASS：193,385 条可布线网络全部连通、零路由错误，DRC 无 Error/Critical Warning，八点 hold 最低 0.179 ns、对应 setup 最低 1.857 ns。全局 WNS 0.277 ns、WHS 0.070 ns，**未达到全局验收目标**。该结果说明保留其他完整路线能消除本次 v9 router 的扩散现象；之前的资源冲突是移动后待修复状态，不能据此认定 SLICEM 永远不可路由。正式全量采用探针验证过的放置策略与 `-preserve`，恢复原始约束后仍须逐项独立验收。

`hold_recreate_logic01` 于 15:22 PASS：八点 hold 0.626/0.209/0.542/0.206/0.574/0.346/0.499/0.588 ns，对应 setup 最低 1.857 ns，193,385 条可布线网络全部连通，DRC、primitive 集合、连线和功能参数通过。helper SHA256 `dba200fdb35a86fe577c061995e003aab300025c4dc987c814b8ac0b5f8e12fb`。`rtl02_flow09` 已采用该 helper、collect_v2 和同样的 preserve 路由，继续 flow05 初始 routed checkpoint 的全量优化；不重复综合/等价，不导出或打包。全局目标尚待该轮最终报告及独立重开审计。

全量 flow09 超过 750 个成功移位，速度约每秒一个，继续运行。核查发现 v9/v10 的控制签名直接比较层级局部 net 名称，同一 100 MHz 电气网络实际包含 4,344 个层级别名，可能错误排除合法近邻。新增 v11/v12 试验把 `get_nets -segments` 的连通等价类缓存后比较。`hold_recreate_canonical01` 因将 net 对象传给仅接受 pin 等对象的 `-of_objects` 失败；`canonical02` helper 已改成从 pin 查询，但探针误把 PS 的未缓冲时钟源网与 BUFG 输出网比较而失败；两次均在移动前停止，保留失败，不采用。只读 `control_net_alias_diagnosis01` 明确记录源网与缓冲后网的区别。`canonical03` 改用实际叶引脚上的 `get_clocks` 核验：同一时钟的别名归一且 100/200 MHz 两域绝不合并，再进行八点真实 route/DRC/参数检查。未证明通过前不替换当前全量 helper。

`hold_recreate_canonical03` 于 15:52 PASS：16 个局部时钟别名归一且两个时钟域分离，八点 hold 最低 0.188 ns、对应 setup 最低 1.857 ns，primitive、引脚、参数、路由与 DRC 检查通过。v12 helper SHA256 `d9090db8ee87ebf43a1804dd15c626be3d170c0adde6ce94bcd21deda896ee6f`。`canonical04` 的 v13 在相同规范化控制签名和 preserve route 下重新允许 SLICEM 近邻，减少远距离放置；该项通过前不采用。flow09 原试验持续推进，15:53 达 1,166 个成功移位，正式基准仍为 rtl01 的 WNS 0.404 ns / WHS 0.070 ns。

`hold_recreate_canonical04` 于 15:59 PASS：八点 hold 0.446/0.179/0.256/0.206/0.744/0.346/0.198/0.380 ns，对应 setup 最低 1.857 ns，完整布线、DRC、primitive/连线/参数均通过。v13 helper SHA256 `f498f044bf052b3cd4e82ec5cbd8ea89fa62f7f5c189186b66dbf2e292fcd353`。`rtl02_flow10` 已采用该已通过的近邻方案启动全量实现；成功启动后核对 process identity，停止仅 SLICEL 的较慢 flow09（至少 1,335 接受、2,404 拒绝），将其保留为人工停止的未完成试验，不视为时序失败或通过。后续集中计算到 flow10。

16:11 全量 v13 的早期搜索速度反而低于之前的 SLICEL 方案（移位 117 个、拒绝 439 次），不能从小规模近邻结果推断全量加速。启动 `rtl02_flow11`，采用已通过 canonical03 的 v12 SLICEL 方案和相同 preserve 路由，不再引入未经验证的 helper。flow10 保留原始过程记录，待 flow11 正常推进后只保留主运行。全局验收目标未变化。

建议 Commit Message：`Improve joint FPGA setup and hold margins with audited physical optimization`。
本次仅修改本地文件，未执行提交、推送、切分支或上板操作。

### 16:30 后的 FIFO 结构调整

用户要求直接调整 FIFO 存储映射和输出结构，停止逐个寄存器位置搜索。核对进程身份后停止 `rtl02_flow11`（当时完成 562/6,811 个）和批量移位探针，保留未完成/失败记录，不将其视为时序通过。

新候选 `fifo_storage02` 从通过综合的 rtl02 派生，保持 100/200 MHz、算法、权重、定点规则、寄存器地址、AXI burst 和模型流水结构。自有 FIFO/RAM 的七个模板采用地址最低位异或编码存储，读出通过显式保留的 LUT2 解码后进入原输出寄存器；仍使用 LUTRAM，容量、读延迟、CE、reset 和握手保持。该变换旨在打断 RAM 到输出 FF 的直接短连接，尚不能据此宣称 hold 达标。

SmartConnect 采用生成 wrapper 已有的 `C_FIFO_OUTPUT_REG` 参数：仅将 `C_FIFO_TYPE=0`、`C_FIFO_SIZE=5` 的 32 深节点从 1 调为 0，同步更新元数据。共 66 个节点、132 个 sim/synth 源文件，原版备份和前后 SHA256 保存于新构建中；不修改厂商安装文件。此项可能改变事务延迟，不能将局部 RAM 的逐拍等价结论推广到 AXI 互连。

本轮实际验证：

- 七模板原版/派生版逐拍比较共 280,000 拍通过，含满空、回绕、同时读写、CE、复位及同地址读写；错误解码 LUT 的负对照按预期失败。
- `sc_fifo_output_eq04` 使用真实 vendor 仿真库验证 128 位单 SI/MI 互连，覆盖 1～256 拍 burst、背压、读写重叠、ID/LAST 和三轮复位；原版与改版各 3,090 读拍、3,090 写拍通过。未覆盖全部六核、所有多端口仲裁与跨时钟组合。
- 独立三模板映射探针于北京时间 17:07:25 完成综合，272 个读出 XOR LUT2 保留。此结果不代表联合资源、布局布线或全局时序通过。

`fifo_storage02_flow01` 已完成输入派生、逐拍验证和工程生成，真实检查 132 个 wrapper 改动。联合综合阶段于北京时间 17:19:49 启动（Vivado 于 17:20:14 启动子 runs）；截至本条记录仍在运行。用户要求联合综合完成时立即报告北京时间，后续继续独立重开检查实际映射，再执行联合物理实现。验收仍为恢复原约束后 WNS ≥ 0.300 ns、WHS ≥ 0.100 ns，允许 setup 较 rtl01 降低；不再使用“两项均须优于 rtl01”的旧比较规则作为采用门槛。

新脚本为 `prepare_fifo_storage_variant.py`、`verify_fifo_storage_variant.py`、`verify_smartconnect_fifo_output.py`、`fifo_output_policy.tcl`、`run_fifo_storage_flow.py` 和 `audit_fifo_storage_synth.tcl`；`system_build.tcl` 仅对含新 policy 的独立构建应用/核对参数。最终还需新结构的 route、DRC、CDC、bus-skew、约束比较及独立重开证据。本阶段不生成 bit/XSA 或 ZIP。

17:33 左右用户更新验收偏好：取消 setup 0.300 ns / hold 0.100 ns 的硬门槛，裕量尽量扩大。后续以原 100/200 MHz 约束下时序、完整布线和 DRC/CDC 等签核通过为基础，报告 setup/hold 两项实际值及与 rtl01 的取舍，择优保留；临时 uncertainty 只用于引导优化，不作为恢复后裕量的固定验收门槛。新增 `audit_fifo_storage_timing.py` 已据此使用原约束签核和双指标比较，不再要求固定数值或两项同时增加。

顶层 `synth_1` 于北京时间 2026-11-02 17:37:04 完成，已立即向用户报时。之后构建脚本继续合并全部 OOC IP、解析 XDC 和生成完整联合检查点；17:40 已确认 132 个 wrapper 改动仍保持，合并设计不存在黑盒。顶层 synth run 的完成时刻与联合报告/收据落盘时刻分开记录，不能把此时状态当作物理时序结论。

完整联合综合流程于北京时间 17:41:05 PASS，已再次报时，DCP SHA256 为 `931dc54eaed26ad3dd1426597ea14ba7f8f3d6f79d97f2179a768ef2cbd5d786`。综合资源为 LUT 96,151、FF 94,732、BRAM 100 tiles、URAM 58、DSP 945；综合资源不能与旧 routed 资源混作同阶段增量。

`fifo_storage02_mapping01` 独立重开确认三个核的 3,616 个解码 LUT2 均保留，但“所有原 SmartConnect 输出寄存器均消失”的预期失败：还剩 520 个。此原始失败收据保留。`fifo_storage02_remaining01` 逐项读出寄存器、实际驱动 primitive 和生成模块，定位到 cnn_data_sc/s03 的 AR/R、curve_ddr_sc/s03 的 AW/B/W 五个 32/128 位宽转换节点；五个 wrapper 均实际设为 TYPE=0、SIZE=5、OUTPUT_REG=0，但仍保留相应内部寄存器。其中 519 个由 RAMD32 直接驱动，1 个是请求 FIFO 的 LUT4 驱动，不能声称全部短连接已移除。

`classify_fifo_output_mapping.py` 将上述事实与 DCP、原失败日志、只读诊断和五个 wrapper 哈希绑定，`mapping_classification03.json` 通过的范围仅为“部分映射变化的身份及分类”，明确 `full_output_register_removal=false`。前两次分类分别因 Verilog 十六进制解析、请求 FIFO 驱动类型假设过窄而失败，原记录保留，不是 RTL 功能失败。新的 `fifo_storage02_flow01/implement01` 在此已知部分改善的结构上运行物理实现，以实际全局结果判断收益，不将映射分类 PASS 当作时序通过。

综合约束比较发现，Vivado 对独立 XPM reset block 重新枚举来源编号并交换生成顺序。`audit_fifo_storage_timing.py` 保留所有非此类命令的值、作用域和顺序，对精确匹配的 `src_arst` additive false path 按作用域及重数核对，并验证完整来源元数据及行号，仅归一化枚举编号。三份 compiled XDC 的合同核对通过；八项正负测试通过，包含时钟改值、漏/重 reset cut、作用域变化、非 reset 命令换序及来源行号变化的拒绝。最终 routed 与原 routed 的约束核对仍待完成。

为覆盖本次残留寄存器所在的位宽转换类型，新增 disposable `sc_width_conversion01`（32-bit SI、128-bit MI、单 SI/MI 同步时钟），使用同一 vendor 生成器建立原版/改版。`sc_width_conversion_eq01` 于 17:53:03 完成仿真并 PASS：1/2/16/17/32/64/127/256 拍上游 burst 的数据、ID、LAST、背压、读写重叠和三轮复位均核对；原版/改版分别在下游接收 786 个写拍、786 个读拍，重叠计数 18。32 位数据被实际聚合为 128 位下游事务，模型按 WSTRB 写入字节并根据 AWSIZE/ARSIZE 推进地址。此项补足同步位宽转换验证，仍不代表所有多端口/跨时钟组合或六核端到端仿真。

`implement01` 于 17:59:34 在增量布局阶段失败，报 Place 46-13 / 30-99：超过 5% movable instances 无法在增量布局中找到合法位置。该轮尚未进入布线，不作为 FIFO 功能或最终裕量结论；失败日志及收据保留。未增加忽略时序的配置或例外。新增 `preplace_fresh` 物理策略：不读入旧版增量位置，旧 routed DCP 只作比较与身份参考，其他原时钟、临时优化引导、opt/place/physopt/route/恢复约束/报告流程保持。`implement02` 已在同一个通过综合及仿真的 checkpoint 上启动重新布局，不重复综合，也不再逐 FF 位置搜索。

### 18:37 新候选布线结果与后续范围

`fifo_storage02_flow01/implement02` 于北京时间 18:37:51 正常结束。原 100/200 MHz 约束下 WNS **0.391 ns**、WHS **0.070 ns**，setup/hold 违规端点均为 0；100 MHz 域为 0.484/0.070 ns，200 MHz 域为 0.391/0.101 ns。197,527 条可布线网络全部布通且无路由错误。新 routed DCP SHA256 为 `e39904f0a7f2066ce23e9c9d74213321aa976221331557dea779e1b833e0746e`。全局 hold 未增加，不能把 200 MHz 局部改善称为全局改善。

`reopen02` 于 18:41:28 独立重开通过。`audit01.json` 因 routed XPM reset block 的枚举顺序不同而失败，原收据与差异保留。逐项核对确认 834 条命令、全部非 reset 命令的作用域与次序均保持；差异仅为原已核对的独立 additive `src_arst` cut 重排和 waiver 时间戳。审计改用与 compiled XDC 相同的限定规则，不放宽时钟、例外目标、作用域或命令重数；新增两个 routed 正负测试后共 10 项通过，`audit02.json` PASS。DRC、CDC、bus-skew 和有效端点覆盖均通过。新 routed 资源为 LUT 90,560、FF 90,639、BRAM 100、URAM 58、DSP 945。

用户在 18:48 左右明确：后续以**刚完成布线的 implement02**作为继承起点，只处理该版剩余紧路径，不返回 rtl01，也不按更早的 54 个节点名单批量修改。rtl01 的 0.404/0.070 ns 仅作历史比较。新增 `inspect_current_fifo_hold.tcl` 从当前 routed DCP 独立提取 100 MHz hold <0.100 ns 的端点和节点；0.100 ns 是诊断筛选界限，不是恢复后的硬验收门槛。下一候选应绑定该 DCP、当前源文件与新目标清单，并优先尝试保留该版物理实现。

用户已授权定向 BRAM 和保留输出寄存器方向。只在 disposable 设计先探测实际厂商映射及 AXI 行为，不修改当前通过候选。厂商公开常量给出 FIFO_BRAM=1、最低 BRAM 指针宽度 9（512 项）；`sc_bram_mapping01` 尝试保留 32 项时在 encrypted envelope 内综合失败，不能采用或视为通过。`sc_bram_mapping02` 采用公开最小深度，仍待实际综合映射与资源报告。增大 FIFO 容量不等于算法或吞吐改变，但容量、事务延迟和复位/背压须单独验证，不能沿用此前 OUTPUT_REG=0 的仿真结论。

### 当前 6 节点的定向调整

`fifo_storage02_flow01/current_hold01` 只读重开当前 DCP，提取到 100 MHz 域 511 个紧端点：bilinear R 104、bilinear AR 81、CNN data R 104、CNN model R 106、curve R 114、curve B 1，合计 510 个 FIFO 端点；另 1 个普通 FF→FF 路径打印值为 0.100 ns，位于筛选界限附近。端点按接收寄存器的每一位统计，不代表 510 个 FIFO 或串行操作。原约束下均非负裕量。

厂商真实仿真给出 SmartConnect 500-5/500-6：AR/AW/B 通道的深度指针不能大于 5，FIFO_TYPE 必须为 LUTRAM。因此 `sc_bram_mapping01/02/03` 失败记录全部保留；BRAM 不适用于这两条命令/响应路径，不能把 6 个节点全部强改成 BRAM。`sc_bram_mapping04` 仅对 R/W 使用公开 XPM FIFO backend（FIFO_IP=2）、BRAM（TYPE=1）、512 项（SIZE=9）和注册输出，通过实际综合并产生 RAMB36E2/RAMB18E2。

采用的定向方案为：4 个 R FIFO 改为上述 BRAM/注册输出；bilinear AR 与 curve B 继续继承当前 OUTPUT_REG=0 的 LUTRAM，在 payload 输出增加两级 `DONT_TOUCH` identity LUT1（INIT=2'h2）。两级缓冲不改变 payload、握手或流水拍数，其组合延迟须由新布线验收。此方案没有把 vendor payload 异或编码或修改 encrypted RTL。

`verify_smartconnect_fifo_output.py` 原先只改名一个 Verilog 文件中的首个 module，生成 BD 文件包含的其他 module 可能被后编译的副本覆盖。历史记录保留，但不能继续把它当作严格独立的原/改版比较。现已改为隔离所有 module，并拒绝任何 module 重定义告警；校验脚本和转换 helper 也随仿真收据冻结。`sc_width_conversion_eq02`、`sc_fifo_output_eq05` 重新验证当前 OUTPUT_REG=0 方案；`sc_targeted_axi32_eq02`、`sc_targeted_axi128_eq01` 验证定向 BRAM+buffer 方案，均通过数据、响应、ID/LAST、burst、背压、重叠与复位检查。`fifo_storage02_flow01/audit03.json` 绑定修正后的独立证据通过，当前 routed 基础继续有效。未覆盖所有多端口/CDC 组合或六核端到端 RTL。

`sc_targeted_mapping01` 的组合方案小设计综合通过，确认 BRAM 和两级缓冲均真实保留。`fifo_targeted03_nodes` 将当前 source、DCP、目标表、6 个生成 wrapper 的前后 SHA256 冻结；只读选择来自当前 implement02，未沿用旧版 54 节点名单。`fifo_targeted03_synth01` 因裸 encrypted 库 compilation unit 配置失败，`synth02` 因复制 probe 工程的 IP 源仍被限定在旧 BD 作用域而失败；原记录保留。`synth03` 将独立节点与官方依赖放入同一 standalone 编译，于北京时间 **19:16:48** 全部 6 节点综合 PASS，已向用户报时。4 个 R 节点各 2 RAMB36+2 RAMB18，共 12 BRAM tiles；AR/B 为 344/24 个 identity LUT1，共 368 个。预计联合 BRAM 为 112/144，最终用量仍以合并设计为准。

`physical_inputs01.json` 绑定当前 routed DCP、6 个替换 DCP、wrapper 源、厂商依赖及两类独立仿真。`implement_targeted_fifo_nodes.tcl` 尝试在当前 routed 设计中仅将 6 个模块 black-box 后读入其替换 DCP，逐项核对边界引脚/连线和替换范围外的 primitive/位置，再复用原 checkpoint 布局与路由。`fifo_targeted03_implement01` 在任何替换前因 REF_NAME 缺少联合综合加上的 `system_<sc>_0_` 前缀而停止；实际前缀已从当前 hierarchical report 确认，`implement02` 据此运行。尚未将模块综合 PASS 视为新全局裕量通过，未导出 bit/XSA、打包或执行 Git。

`fifo_targeted03_implement02` 于 19:23:58 在任何替换前停止：边界检查对生成 wrapper 的未连接引脚调用 `get_property NAME`，空对象导致 Common 17-55。修正为将未连接引脚明确记录为空连接并继续前后严格比较，未放宽边界合同。`implement03` 使用新目录重新读取同一个当前 routed DCP，原失败记录保留。

`sc_targeted_axi32_saturation02` 与 `sc_targeted_axi128_saturation02` 均于 19:24:18 完成 PASS。真实 vendor RTL 在一笔 256 拍读 burst 中，预热 16 拍后，reference 和 variant 各连续 240 拍达到每拍一个有效读数据拍；32/128 位两种互连仍通过已有数据、ID、LAST、响应、背压和复位测试。128 位场景原/改版读写重叠计数不同（198/180），因此只声明事务与饱和吞吐验证，不能声明逐拍延迟相同或端到端 30 FPS 已验证。saturation01 的 testbench 编译失败记录保留。

`fifo_targeted03_implement03` 于 19:32:37 在首个节点导入时失败，Netlist 29-77：联合综合对 wrapper 边界做了重命名、常量传播与未用位裁除，单独 OOC DCP 的通用端口不能直接匹配现有物理接口。只读 `fifo_targeted03_ports01` 于 19:38:21 PASS，保留六节点逐位端口、方向及连线，并确认差异并非仅大小写：例如 bilinear R 的输出剩 140 个有效 payload 边界位、输入仍为 150 位，公共时钟与复位也已合并。未绕开接口检查或猜接缺失端口，原通过 routed DCP 保持。

后继 `fifo_targeted04` 从 **fifo_storage02 当前源码及 audit03** 派生，继续仅修改当前六节点。新增 `prepare_targeted_fifo_build.py` 验证当前父版输入哈希和目标来源后复制源码；`targeted_fifo_policy.tcl` 调用冻结的 `targeted_fifo_mapping.py`，对新生成 132 份 wrapper 与父版逐份比较，只允许 6 个节点的 sim/synth 共 12 份产生定向结构差异。其余继承 OUTPUT_REG=0 及当前七模板解码结构，不返回 rtl01、rtl02 原始源码，不采用旧 54 节点名单。`run_targeted_fifo_source_flow.py` 的 create 于 19:44:28 PASS，真实输出 TARGETED_FIFO_POLICY_APPLIED=6、VERIFIED=132；联合 synth_1 于 **19:44:57** 启动，尚未结束，不能报为综合完成时刻。

`fifo_targeted04_continue01` 的 `continue_targeted_fifo_flow.py` 已启动，等待上述唯一命名综合收据通过后顺序执行：实际六节点/3,616 解码 LUT 映射检查、以当前 implement02 的 routed DCP 为增量参考实现、原约束独立重开、完整审核。实现使用临时 .300/.100 ns uncertainty 引导并恢复为零，不把它们当固定采用门槛。不启动失败后的自动候选、不逐 FF 搜位置、不巡检内存/磁盘、不导出 bit/XSA、不打包或执行 Git/板卡操作。任一阶段失败即保留原始记录并停止自动链。

新增 `audit_targeted_fifo_mapping.tcl` 用于核对六节点真实 BRAM/identity LUT 映射和继承解码；`audit_targeted_fifo_timing.py` 区分直接导入与上下文重建，绑定当前父版、只改六节点的生成源码、两项饱和仿真、原有约束、独立重开、时序/资源/route/DRC/CDC/bus-skew。这些审核当前仅已通过 Python 语法检查，尚未对新 routed 候选执行；不得把“脚本已准备”写成新实现签核通过。已有约束比较的 10 项正负回归通过。

当前 Git 状态仍为 `feat/software...origin/feat/software`，`?? fpga/joint_lowlight_compact_d/`，未暂存、提交、推送或切分支。建议 Commit Message：`Target six remaining SmartConnect FIFO hold bottlenecks with source-bound validation`。本轮最终时序、综合完成时刻与资源变化须由运行结果补充。

`fifo_targeted04` 的 14 个 IP 子运行于北京时间 20:00:15 全部结束；顶层 `synth_1` 于 **20:01:12** 成功结束，已向用户报告。随后仍需 `open_run` 合并各 OOC DCP、解析 XDC、生成联合报告和 `joint_synth.dcp`；顶层 run 完成与完整联合综合收据完成分开记录。已完成互连 OOC 报告确认 4 个 R FIFO 所在的各互连新增 3 BRAM tiles，URAM/DSP 均无增量；最终资源仍以同阶段联合报告为准。

完整联合综合于北京时间 **20:04:42** PASS，已向用户报告，`joint_synth.dcp` SHA256 为 `e95ea9b059a415e5605abd20aab7406066fc7d4f12d140efb4dc1b885efde538`。同综合阶段比较：LUT 96,428（+277）、FF 95,000（+268）、BRAM 112 tiles（+12）、URAM 58（不变）、DSP 945（不变）。未以旧 routed 用量计算综合增量。

`fifo_targeted04_continue01/mapping01` 于 **20:06:03** 输出检查通过，runner 于 20:06:04 完成收据。四个 R FIFO 各有 2 RAMB36E2、2 RAMB18E2；AR/B 分别保留 344/24 个 identity LUT1；继承的 3,616 个 XOR 解码 LUT2 及其 INIT/DONT_TOUCH 均确认保留，无黑盒，100/200 MHz 时钟保持。`implement01` 随后以当前父版 routed DCP 为增量参考继续物理实现。

综合 XDC 核对发现四个读节点各两条来源记录由 `xpm_memory_xdc.tcl` 变为 `xpm_fifo_rst.tcl`，共八条来源和 392 条行来源记录。新增 `targeted_fifo_constraint_contract.py` 仅接受这四个精确节点、两条精确内部支路和两个固定厂商路径的对应变换；实际时序命令、次序、作用域及 additive reset cut 重数仍严格一致。保留原始差异文件，不修改父版已绑定的通用约束审核。`compiled_constraints02.json` 对真实父/新联合 DCP 的三份 XDC 核对 PASS：board/early 全同，late 仅上述来源变换。新增八个正负测试及原十项约束回归共 18 项 PASS。

更新的最终审核额外绑定 `mapping01` 的 runner、Tcl、目标表、日志和报告，并核对精确六节点映射及继承解码。当前续跑链使用启动时冻结的旧审核脚本；若它因上述已定位的来源差异失败，应保留原 `audit01`，使用更新审核独立生成 `audit02`，不修改原失败结果、不重复实现。新的物理裕量和独立重开尚未完成，不能将上述映射/约束检查视为 routed 签核。

### 20:35 接受候选并开始交付

`fifo_targeted04_continue01/implement01` 于 **20:32:34** 完成 PASS，当前父版增量布线复用率为 98.18%。恢复原约束后 WNS **0.391 ns**、WHS **0.100 ns**，setup/hold 违规端点均为 0；100 MHz 域为 0.484/0.100 ns，200 MHz 域为 0.391/0.101 ns。相比当前 implement02，setup 不变，hold 增加 0.030 ns。198,851 条可布线网络全部布通，路由错误为 0；17 条 bus-skew 约束通过，最差 slack 3.488 ns。

最终资源为 LUT 90,753、FF 90,929、BRAM 112/144、URAM 58/64、DSP 945/1248；与当前父版 routed 同阶段相比为 +193 LUT、+290 FF、+12 BRAM，URAM/DSP 不变。新 DCP SHA256 为 `d582ed0005dbc85563fb2eb0713e74a95f8efafdafe91af1a5a3ecf3ae028f66`。独立 `reopen01` 于 **20:35:08** 通过。冻结的旧 `audit01` 因已定位的 XPM 来源记录差异失败，保留原结果；更新后的独立 `audit02.json` PASS，绑定六节点映射、实际来源替换、饱和仿真、原约束、完整时序/覆盖/路由/DRC/CDC/bus-skew，未放宽实际时序合同。

用户随后明确接受此结果，要求停止优化并生成压缩包。新增 `package_accepted_fifo.py` 只执行固定 DCP 的 coverage、数值/物理证据验收、bit/XSA 导出、BIN 转换和 ZIP 校验，不重新综合或布局布线。交付写入新的 `accepted_fifo04_delivery01`，新增 checkpoint-bound `release_approval.json`，原实验的 no-export 记录及失败记录保持原样。新的清单允许该次已审核导出，不将授权扩展到 Git 或板端。

`collect_delivery.py` 支持这类源码重建的独立物理报告，纳入实际实现输入及 132 份生成 wrapper；原低照度/D 的模型来源包放入 `reference_ip/`，明确不能替代实际修改后的 RTL。`verify_delivery.py` 增加 ZIP 内审核、原始输入、导出检查点与全部实现源的身份对应核对。交付将包含 bit、Bootgen bit.bin、XSA、HWH、实际寄存器表、时钟复位及调用说明、Golden/报告、逐文件 SHA256 和 ZIP 旁侧哈希；生成和最终 ZIP 验证仍在进行，未上板、未验证真板 FPS。
