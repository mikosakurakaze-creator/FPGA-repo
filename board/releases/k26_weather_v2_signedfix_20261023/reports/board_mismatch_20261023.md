# 2026-10-23 真板数值不匹配调查

## 当前状态

已确认本组数据在实现功能模型中的因果链：DSP 级联改写没有保留 22-bit 截断后符号扩展的语义。只恢复一个接收 DSP 的原始加数/模式，两次调用均由 171 处错误变为 Golden 192/192 一致。正式修正已重新布局布线，其真实导出的布线功能网表在四帧 task=0、0、1、0 中全部逐值等于 Golden。新 bit 已生成；配套文件核验状态见 [修正版目录](../board/releases/k26_weather_v2_signedfix_20261023/README.md)。保留 2026-10-22 发布文件原始字节，不替换故障 bit/XSA。

## 输入证据

只读输入目录：`C:/Users/wzh16/Desktop/github clone/weather_board_mismatch_20261023/`。目录内 `manifest.json` 所列文件的大小和 SHA-256 全部一致。没有将包内说明作为自动运行板卡或修改硬件的指令。

同一组输入/输出均为 RGB NCHW、小端 INT16 Q14，8×8、task=0，每份 192 个标量、384 字节：

| 数据 | SHA-256 |
|---|---|
| 原始输入 | `3bf4260d11a4d9d8ec7c00167a323d9793a7f74fb8e7a11c8dfc7f7822bc62f6` |
| Golden | `bbb5e6f343e1a4b6f0b05c8f18fbce48655e30ed532194e1a4e32fcf250b8697` |
| 真板第一帧 | `ca1af1cfe6eb7f46ac43abb94327ba59702dc97f911c365a05f7daa539686597` |

板端第一帧 171/192 不匹配；21 个匹配点位于三个通道的 `y=1..7,x=2`。首次与暖态输出哈希相同；暖态证据仅有终端摘要，没有原始暖态日志。后两帧未执行，不把占位零输出列为去雾或连续帧结果。

## 已执行的离线验证

- C++ 流水源码直接运行包内输入：192/192 等于包内 Golden，实际输出 SHA-256 与 Golden 一致。
- 与发布 bit 对应的导出 RTL，通过 AXI-Lite 配置、独立 AXI DDR 模型、实际板端地址和反压，连续运行同一 task=0 输入两次：两次均 192/192 等于 Golden，与板端各有 171 处差异。
- 已核对天气 IP 的 254 份导出 RTL/ROM 与当次 Vivado 编译输入身份一致，天气 OOC 综合检查点哈希与发布审计记录一致。
- 综合后功能网表已完成相同输入、地址、反压及连续两次 task=0：两次均 192/192 等于 Golden，与真板各有 171 处差异。第一次连接了已被 IP wrapper 移除的 USER 端口而未完成 elaboration，仅是测试平台失败；有效结果来自修正后的 `board_diag_20261023_synth02`。
- 导出 RTL 的六个空间阶段输出逐像素检查 RGB 旁路：每阶段、每帧 64 个 RGB 均与输入一致，两个连续调用均通过。这仅证明所测 RTL 的旁路，不等于已排除真板时序问题。
- 原独立 DDR 模型强制读 beat 之间至少空一拍，即使关闭人为反压也未覆盖连续回数。新补充每拍可连续回数的同组输入回归：两帧均 192/192 等于 Golden，各 1,427 拍。输出仍与板端各有 171 处差异。
- 已从原 `system_routed.dcp` 导出完整系统功能网表。早期孤立子模块拼接因全局优化后的端口/常量边界而无有效数值结果，不能记为功能失败。第 3 次完整父层尝试也因诊断边界中悬空控制响应及未完整处理 PS HPM 窄访问而中止，没有产生帧输出；这些是测试平台缺陷。修正后的第 4 次完整路径运行已完成：两次调用均与真板 192/192 完全相同，SHA-256 一致；均与 Golden 有 171/192 差异。保留了真实天气核、复位、控制和两路数据 SmartConnect 父层连线，PS 用独立内存/控制刺激替代，其他低照度 master 空闲，未加 SDF。

## 原布线后网表中的首个偏离点

`board_diag_20261023_physical_trace01` 复用第 4 次路径的已编译快照，每个上升沿前 1ns 采样，以实际 FIFO 的 168-bit 输入端口比较，不猜测被优化删除的位：

- stage0～stage4：每级 64/64 个完整数据包与导出 RTL 相同。
- stage5：57/64 个数据包不同，仅特征通道 2 被置为 32767；其余 7 个特征通道和全部 RGB 都正确。
- 残差相加、下溢比较符合实际操作数；点卷积输出在相加前已经错误，故残差饱和不是首个错误计算。
- 首像素量化幅值寄存器取得 65976，正常为 440；单点卷积量化前后的固定偏移与实现中的符号扩展差异相符。

原综合接收 DSP 的 C 为 22-bit 前级输出的符号扩展；实现网表把它改接到前级完整 PCOUT 并修改 OPMODE。实际 PCOUT[21]=1、[22]=0 时，`sign_extend(low22)` 与完整 PCOUT 不同。`open_run synth_1` 后导出的已链接检查点仍保留原始 C 连接；`system_wrapper_opt.dcp` 已经改变，可将引入阶段缩小到 `opt_design`。

### 单点恢复因果验证（已完成）

`tools/restore_diagnostic_dsp.py` 对原布线后完整网表的新副本只改一个 DSP 接收端的 C、PCIN、OPMODE：恢复 `M + sign_extend(low22)`，其他网表内容和测试平台均保留。

`board_diag_20261023_c_restore_repro01` 两次输出 SHA-256 均为 Golden 的 `bbb5e6f...250b8697`，每次 192/192 一致；周期仍为 2401/2376。原始导出网表则两次精确重现真板 SHA 和 171 处错误。该对照没有改行缓存、RGB、URAM、DDR 连接、权重或量化规则。

错误时，原本应有的负数符号扩展被完整 PCOUT 的第 22 位 0 替代，接收加数相差 `2^22`；本通道右移 6 位后相差 65536，使正常 440 变为 65976，再钳为 32767。该特征与实际逐级 trace 及最终 171=57×3 个错值一致。证据见 `evidence/dsp_cascade_causality_20261023.json`。

这是实现模型中的因果验证，不能等同于真板复测。首次尝试仅给接收 DSP 加 `DONT_TOUCH`，实际检查证明没有阻止重接，已拒绝该候选；正式方案关闭当前 Vivado 2025.2 进程中的 `logicopt.enableDSPCascadeFixing`。随后 opt和新routed网表均通过四帧回归，严格结构检查也核对全部48根C输入及实际OPMODE，不再只比较两根符号线。

## 正式修正的实际结果

| 项目 | 结果 |
|---|---|
| 原始已链接综合 DCP | `D:/weather_builds/board_diag_20261023_linked_export01/system_linked_synth.dcp` |
| 修正 opt DCP | `D:/weather_builds/board_diag_20261023_protected_opt02/system_protected_opt.dcp` |
| 新 implementation | `D:/weather_builds/weather_signedfix_system01/` |
| 最终 routed 功能网表 SHA-256 | `a17d8a86a49d9639485f139fe85373adc4ef2fe42805d30b8c45e5288ae9baf5` |
| 最终 routed 四帧回归 | `D:/weather_builds/board_diag_20261023_signedfix_route_repro01/run.json`，4/4通过 |
| 帧顺序及周期 | task=0、0、1、0；2401、2376、2376、2376拍；四帧之间不复位 |
| 原包task=0 | 冷态、暖态、切回后均192/192与原Golden一致 |
| task=1 | 192/192与既有独立RTL验证向量一致；没有该向量的真板capture |
| 100 MHz时序 | setup WNS +0.638 ns，hold WHS +0.010 ns，pulse width +3.500 ns |
| 布线 | 166,311/166,311个可布线net完成，0 routing errors |
| 组合系统资源 | LUT 74,047（63.22%）、FF 79,552（33.96%）、BRAM 72（50%）、URAM 47（73.44%）、DSP 961（77.00%） |

新 DRC 没有 Error/Critical Warning，但存在533项DPIP-2、211项DPOP-3、250项DPOP-4、18项DPREG-7及1项RTSTAT-10 Warning，不能描述为“零告警”。18项DPREG-7稳定二值OPMODE检查通过；这项有限检查不覆盖物理瞬态、SDF或其他警告类别。见 `evidence/signedfix_routed_dsp_opmode_20261023.json`。

修正版XSA已从新routed DCP原生导出。第一次被工作目录空格触发的工具内部命令解析错误阻断；换到无空格目录重试成功。没有手工修改XSA：HWH、PS初始化、驱动均与原版逐字节一致，工具更新平台包装元数据并加入`.nts`。外部bit取自该XSA内唯一bit成员，与独立bit导出的配置payload一致，Bootgen BIN也已逐字节核验。新文件身份见修正版README及manifest。

回归保留实际天气核、复位、控制和HP0/HP3 SmartConnect父层连线；PS硬核由独立刺激/内存替代，其他PL master空闲，未加SDF。它是离线实现功能验证，不是真板DDR、并发或视频性能验收。

原始诊断输出留在 `D:/weather_builds/board_diag_20261023_*`，不自动提交生成缓存或仿真数据库。复现入口为 `tools/run_board_repro.py`。

## PS/DDR 静态检查

XSA/HWH 指定 HP0（SAXIGP2）、HP3（SAXIGP5）接口均为 128 位，天气核本身两路 AXI data 为 32 位，SmartConnect 承担位宽转换。输入/输出分别接 HP0/HP3，天气 master 只开放 `[0,2 GiB)` 地址窗口。板端提供的两组 DMA 地址均在该窗口，互不重叠，且 64 字节对齐。

发布 XSA 的 `psu_init.c` 要求 AFIFM2/AFIFM5 的 `RDCTRL` 和 `WRCTRL` 位 `[1:0]` 为 0：

| 接口 | 读配置地址/实测 | 写配置地址/实测 | 按 XSA 应满足 |
|---|---|---|---|
| HP0 / AFIFM2 | `0xFD380000 = 0x000003B0` | `0xFD380014 = 0x000003B0` | `(value & 3) == 0`，实测满足 |
| HP3 / AFIFM5 | `0xFD3B0000 = 0x000003B0` | `0xFD3B0014 = 0x000003B0` | `(value & 3) == 0`，实测满足 |

包内 Linux 驱动使用 `dma_alloc_coherent`、`dma_wmb/dma_rmb`、有序 MMIO 和寄存器回读，检查 PL0 时钟/复位、SMMU bypass、buffer guard 及输入不变性。用户另行补充上述四个只读实测值，均为 `0x000003B0`。当前仅排除这四个位宽字段 `[1:0]` 不匹配，不能据此排除完整 PS 配置、实际 AXI 事务、DDR 数据一致性或加载状态问题。

## 后续真板验收

- 使用修正版目录的同一套bit/XSA/BIN，重跑原包输入的冷态和暖态，检查192个标量及Golden哈希，再检查任务切换与尺寸变化。
- 正式修正已经过独立新implementation；本次用于生成bit的是新routed DCP，不是单点修改的仿真Verilog，也不是旧工程的impl run。
- 真板内逐级波形仍未取得；目前已在实现功能模型确定偏差，不再优先要求修改 HP 配置试错。
- 功能仿真不含 SDF，不覆盖器件物理行为或板端 PS 硬核/DDR；不得将其表述为真板验证。
- 新版本保持独立目录；原故障证据不覆盖。文件清单和平台导出方式见该目录README及manifest。

## 精确的假设注入特征

用有效导出 RTL 两帧的 `stage_5.txt`（176-bit 完整包）和原始去雨尾层权重重新计算，原值输出仍与 Golden 192/192 一致，RGB 旁路也与原输入逐值一致。

在最终输出存在差异的 57 个像素位置，分别将 8 个特征通道之一改成 32767；其中仅零基通道 2 能把全部 192 个输出逐值变为真板值，预测输出 SHA-256 为 `ca1af1cfe6eb7f46ac43abb94327ba59702dc97f911c365a05f7daa539686597`。正常该通道在这些位置应为 0～1679。另 7 个像素（`y=1..7,x=2`）保持原值。

这一数学特征支持优先检查末级通道 2 的生成、饱和比较、选择和到尾层的传输。错误位置掩码来自已知最终输出，且没有板内逐层读回，因此它不是根因证明，不能排除其他等价故障。

复现脚本：`tools/analyze_board_signature.py`；可审核结果：`evidence/board_mismatch_20261023_signature.json`。原始 trace 仍留在本地 `D:/weather_builds/board_diag_20261023_rtl_trace01/`。

## 本轮代码自审

见 [实现与验证假设审查](implementation_assumptions_audit_20261023.md)。发布前缺少实现网表数值回归是实际验证缺口；本次 DSP 符号边界变化已通过原错误复现与单点恢复完成因果对照。诊断脚本自身的问题另列，没有把它们冒充板端电路根因。
