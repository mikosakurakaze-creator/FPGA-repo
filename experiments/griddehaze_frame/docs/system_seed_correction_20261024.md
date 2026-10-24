# 系统来源纠正与交付门禁

日期：2026-10-24。

## 实际发现的问题

第一次新增五核系统 `D:/weather_builds/grid_system01` 错把历史 `system02` 串行 tile 版作为旧核来源。它有相同的 IP 名称及 VLNV，但不是当前流水旧核，寄存器和计算实现也不能视为相同。此前 BD 审计只证明了“与所选 seed 一致”，并未证明 seed 就是当前已验证版本；这是集成脚本的来源选择错误。

该候选完成了综合，但在 implementation 的 signed-DSP PRE 检查处停止：预期的流水算术接收 DSP 不存在。保护检查没有删除或放宽，未生成这版最终 bit/XSA。其综合 BRAM 为 151.5/144，也不能作为当前正确五核系统的资源结论。

`grid_system01` 及失败记录保留，仅用于排查。该目录的 preimpl XSA 不是交付件。对它运行的新核/互连诊断即使通过，也不能证明当前旧流水核保留成功。

## 修正方式

- 新候选改在 `D:/weather_builds/grid_system02`，采用 `D:/weather_builds/stream_system01` 的实际 BD 和四套冻结 IP。
- 构建前将 seed weather 的全部 254 份 Verilog/ROM 与 `board_diag_20261023_signedfix_route_repro01/run.json` 的身份逐项比较；本次比较零差异。
- 同时核对 seed 自身 manifest 的全部 IP 文件，防止只检查 top 名称而漏掉 ROM、子模块或低照度 writer。
- 保留原 signed-DSP PRE/POST 精确连接及 OPMODE 检查；新实现必须重新通过，不能继承旧 checkpoint 的时序结论。
- 已实际执行负检查：指定历史 `system02` 后，脚本在创建输出目录、启动 Vivado 前拒绝，错误为 `Seed weather IP differs from the reviewed signed-fix baseline`。
- 导出 bit/XSA 增加同版旧 weather 全系统布线后冷暖回归门禁；已有新去雾核门禁继续保留。仅 timing clean 不满足交付条件。

## 测试工具修正

当前安装的 Vivado 2025.2 `xelab` 不接受脚本中新加的 `-O 3`。首次全系统回放因此未启动仿真，失败保留在 `work/grid_physical_synth01`。按本机工具实际帮助删除该选项，使用默认优化；不会把进程返回 0 当作测试成功，仍要求完整 PASS 标记及输出文件哈希。

全系统网表自身可能已包含 `glbl`；后续回放只在缺失时补入厂商文件。PS 49 位 DDR 地址显式零扩展到有界内存模型的 64 位地址，避免依赖隐式端口补位。

综合前导出的系统还保留 `const_locked` 实例；首次 PS 回放遗漏该模块，导致复位无法释放。适配器改为保留实际常量模块，并新增每个 CSR 握手的超时，修正后错误 model 检查已实际通过。该修改只改变仿真边界，不改变综合后的模块体或硬件数据路径。

50,000 周期的单核网表有界探针实际完成，参数读计数从 92 持续增长到 194，证明早期布局审查在推进。该探针不是最终数值回归，结果有意保持 `pass_result=false`。由于门级整网仿真耗时很长，重复的单核长跑和历史 seed 全系统诊断已停止，保存 `interruption.json`；完整数值验收留给当前版本的最终布线系统，不能将停止当作通过。

导出 RTL 用更新后的 CSR 超时和 WSTRB 传输 lane 检查重新完整执行，4×4 冷暖两帧全部 320 节点一致，错误 Golden 被检出（`work/frame_rtl05`）。更新后的 128 位有界内存自测也通过（`work/memory_model02`）。

后续网表完整回归仍实际运行冷暖两帧；SV 检查最终结果后，Python 再对原始输出逐字节、长度和哈希核对。网表的 1 LSB 负对照使用本次实际捕获文件检验独立比较器，不再声称额外重跑一次数小时的 DUT。导出 RTL 模式继续保留实际 SV 错误 Golden 注入；报告分别注明两类负对照的范围。

## 验证范围

这次来源纠正不修改 A 参数、Golden 或算术 HLS。此前全节点 C 仿真、4×4/5×7 导出 RTL 结果仍对应同一个新核。正确五核系统的综合、实现、网表回放及最终 bit/XSA 状态需以 `grid_system02/build.json` 和实际结果为准；本记录不预先宣称完成。

没有修改只读旧仓库，没有暂存、提交、推送或切换分支。
