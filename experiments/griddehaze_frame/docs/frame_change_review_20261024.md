# 整网 PL 调度及系统构建变更记录

日期：2026-10-24。本记录为此前算子评审之后的增量；历史失败和旧评审证据不覆盖。

最新集成纠正：`grid_system01` 误选旧 tile seed，signed-DSP 保护已停止其实现。已新增冻结旧核身份门禁并以正确 `stream_system01` 在 `grid_system02` 重建，原因及实际证据见 `system_seed_correction_20261024.md`。本页早先的“整机综合正在执行”属于发现问题之前的阶段记录。

## 修改、新增及原因

| 文件 | 变更原因和关键差异 |
|---|---|
| `hls/frame_top.cpp/.hpp` | 新增 PL 320 节点调度、tile 遍历、DDR 地址计划检查、模型身份与长度检查；调用两类现有算子；使用可移植 INT64 bias 解码 |
| `hls/generated_model.hpp` | 根据冻结 A 图生成节点 ROM、通道/尺度/权重偏移和 shift；不是手工预设参数 |
| `hls/tb_frame.cpp` | 全节点、独立最终输出、冷暖运行、11 项错误描述符和 guard 检查；每次将输出毒化，避免上次结果造成假通过 |
| `tools/emit_model.py` | 从冻结包生成硬件 ROM 和每个 H/W 的 1,344 字节 layout |
| `tools/frame_trial.py` | 构建不可覆盖的源快照；区分元数据审查、主机执行、Vitis C 仿真、HLS 综合及 RTL scope；默认只审查 |
| `tools/audit_frame_contract.py` | 独立核对 ROM、2,563 项 shift、bias 解码、23 组尺寸/生存期、tile halo 几何和全部 Golden 元数据 |
| `system/axi_bounded_memory.sv`、`frame_axi_test.sv` | 独立 AXI 内存、背压、延迟 B、WSTRB/4 KiB 检查、每节点或网表最终结果比较；不用庞大的 HLS co-sim 指针深度装载小数组 |
| `tools/frame_rtl_trial.py` | 对实际导出 RTL/功能网表进行 AXI-Lite 操作和原始输出哈希检查；错误 Golden 必须检出；分开记录全节点和仅最终输出两种证据 |
| `tools/grid_physical_path.py` | 为全系统功能网表保留真实新核、SmartConnect、控制和复位连接；以仿真代替 PS，旧核保持空闲；尚待实际系统网表回放验证 |
| `system/create.tcl`、`synth.tcl`、`impl.tcl`、`export.tcl` | 在独立目录创建保留四个旧核、增加去雾核的系统；保留旧 signed-DSP 防护钩子，严格经过时序门禁再导出 |
| `tools/build_grid_system.py` | 核对 C 仿真/综合源码一致，逐文件冻结 IP 输入，分阶段构建；修复只创建式 JSON 写入不适合更新状态的问题 |
| `tools/audit_grid_sources.py` | 检查五核实际生成的 Verilog/ROM、综合完成标记和 ROM 加载记录，避免只校验输入 IP 名称 |
| `tools/continue_grid_system.py`、`collect_board_artifacts.py` | 串接实现、新旧核同版布线后回归及本地 bit/XSA 收集；缺门禁即停止，不自动上传 |
| `tools/audit_grid_system.py` | 对实际新 BD 检查所有 PS 参数、旧控制地址/连线保留，新核 HP0/HP3/控制地址正确 |
| `tools/record_frame_recovery.py` | 单独记录安全拦截之后实际成功的原生执行，保留原失败结果，不虚构安全软件放行原因 |
| `docs/frame_interface.md`、README 与实施/安全记录 | 记录实际生成的 CSR/DDR/数据合同、运行状态和当前硬件限制；将早期接口提案明确标为历史 |

## 当前实际执行证据

- 原生恢复执行：8 组每组 320 节点、最终输出一致；首组冷暖运行、11 项错误描述符通过。另重新核验 2,560 个实际节点文件和 8 个最终输出的 SHA/长度。
- Vitis 实际 48 位 C 仿真：8 组所有节点与最终输出一致、11 项错误描述符通过。
- HLS 综合：LUT 23,908、FF 12,806、BRAM18K 99、DSP 44、URAM 0；时钟估计 7.300 ns，延迟/II 未确定，不是布线或帧率结果。
- 导出 RTL，4×4：冷、暖两次均 320 节点逐元素一致；延迟写响应在核心 DONE 前排空；错误 model 被提前拒绝；错误 Golden 被检出。6,529,321/6,530,839 周期含仿真内存背压和 MMIO，不是板端性能。
- 导出 RTL，新增 5×7 随机图：使用同冻结包、A 未改动整数程序独立生成 Golden；冷暖均 320 节点一致，错误 Golden 被检出。该用例明确属于 B 新增边界测试，不冒充 A 附件原有向量。
- 实际新 BD 审查通过：四个旧核、全部 PS 参数、旧连线和旧地址保持；新控制为 0xA0040000，feature→HP3、parameter→HP0，两个 PS 端口配置 128 位、时钟配置 100 MHz。
- 新去雾核 Vivado OOC 综合完成，实际 LUT=10,971、FF=11,071。该值属于单核 OOC，不是整机 routed 资源。
- 正确来源的五核系统整机综合通过，实际生成 524 份 Verilog/ROM 与输入完全一致；正在 implementation。综合资源、加强后的奇数尺寸回归和 A 比较器复核结果见 `execution_followup_20261024.md`。尚未得到新版 routed 时序、最终 bit/XSA 或板测结果。

## 已发现并修正的检查问题

1. 记录脚本尝试用只创建文件的 JSON helper 更新状态，导致 BD 已创建但状态未保存。改为临时记录后原子替换，按已存在的 PASS 日志和 XSA 恢复 create 记录，未捏造原进程退出码（保留 null）。
2. 测试台大于 signed32 上限的延时字面量溢出，已缩减为明确合法的全局 watchdog；原失败记录保留。
3. HLS 优化了 `completed_nodes` 的中间赋值，不能用 CSR 输出 valid 观察每个节点。改为经实物 RTL 核对的图循环退休状态，公共合同说明它只用于成功后读取 320。
4. IP 包装器移除了无用 AXI USER 端口。网表连接按实际声明核对，只允许已审查的无用字段消失；不改动算术电路。
5. AXI 总线读可覆盖 payload 末端所在对齐 word，尤其奇数尺寸；独立内存模型允许分配 slot 内的读 padding，但写仍逐 WSTRB 检查真实 payload，未把 padding 当图像像素。
6. 当前 HLS pointer depth 覆盖最大整图，而小向量 C 测试台只分配实际大小；禁止直接运行 vendor co-sim，以免自动 transactor 按最大深度越过小数组。实际 RTL 验证使用独立有界 AXI 内存，C 仿真/综合继续正常使用。
7. 新核导出门禁原先只重读 PASS 记录和网表身份，现增加冷暖原始输出的长度/SHA、仿真退出码/日志 SHA 以及负对照记录复核。实际 1 LSB 输出篡改和日志篡改均被拒绝；历史测试文件未修改。
8. 显式指定 `--golden` 时，报告的 `case` 改为实际 Golden 目录名。历史 `frame_rtl_odd02` 的 `case=size_4x4` 是旧报告标签缺陷，真实 `case_shape=[5,7]`、Golden 路径和输出均为 5×7；历史证据不覆盖。
9. 继续核查发现全局 watchdog 原来只允许 60,000,000 周期，比单帧上限短。改为显式单帧预算及覆盖冷暖两帧的全局周期预算；原 33×47 部分运行保留为中止，采用新目录重跑，不修改计算核或拿超时预算冒充实测性能。

## 未完成和边界

布局布线、实际全系统 DDR 路径功能回归、最终 bit/XSA 仍须完成。当前没有单设备超时中止/AXI 排空复位器、物理指针/跨区域别名硬件验证或 AXI 错误诊断；正常请求依赖可信调用方与独占合法 DMA。共享复位不能冒称独立故障恢复。大图的整图硬件执行、实际 DDR 分配及真板画质/速度未验证。

## 工作区与提交建议

`griddehaze_fpga` 没有独立 `.git`。只读参考仓库仍在 `weather_fpga_integration`，HEAD `e8662ce5bd177f4014da469ab9885eca06e396f3`，本次检查工作区干净。没有执行 git add、commit、push 或切换分支。运行数据在忽略的 `work/`，A 原始包仍在忽略的 `a_candidate/`，没有自动上传。

建议 Commit Message：`feat(griddehaze): add full graph scheduler and isolated legacy system integration`。
