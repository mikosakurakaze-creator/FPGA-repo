---
name: evidence-driven-fpga-debug
description: Reconstruct and audit FPGA debugging decisions across observations, bounded experiments, failed hypotheses, and corrected plans. Use for requested bring-up fault analysis, AI collaboration evidence, or runtime-plan reviews; distinguish host tests, historical board evidence, and untested performance.
---

# Evidence-driven FPGA debugging

把“候选解释→最小证伪实验→实际观察→修正/停止”连成可追溯链。适用于 PS/PL bring-up、运行环境和性能方案审阅；不提供通用寄存器恢复序列。

## 环境与输入

需要只读工程/报告、原始日志与会话摘录、硬件和固件身份、用户本次授权范围。Host 文档审阅不需要板卡。若缺原始对话，输出“根据日志重建的事件摘要”，不可补写 Master 或模型原话。

输入至少含：问题时间/症状、原始观测、候选假设、当次工具与命令、执行边界/停止点、实测结果、反证、人工决策、相关源码/提交/日志身份。输出为有序事件与可核验的结论、未证明项、下一步最小材料。

## 操作步骤

1. 按问题与证据身份关联跨会话记录，保留中断/压缩与来源缺口。统一使用下列状态：`PROPOSED`、`EXECUTED`、`OBSERVED`、`REFUTED`、`SUPPORTED`、`NOT_PROVED`、`NOT_TESTED`。
2. 原样提取症状、错误、实际调用与返回；命令 exit 0 不足以证明语义成功。区分寄存器配置、活动观测、成功 AXI 访问、完整算法输出、持续性能，不能互相代替。
3. 每个假设列支持证据和能排除它的最小观测。把多项修复组合后的成功与单因素根因分开；没有单因素隔离证据，不写唯一根因。
4. 对已执行的最小实验核实范围、停止条件及真实交易。AXI 超时或 hang 发生后保存现场，不自动重试、reset、PMU/GPIO 写或反复读以“看会不会恢复”。本轮 Host-only 时只整理既有实验。
5. 性能方案先审核实际 ABI/启动链、时间域、内存与 DMA owner，再讨论运行。允许覆盖某地址与有独占 owner 证据不同；未知环境的试运行不能作为安全前提的补证。
6. 出现反证就明确撤回/降级原假设，保存旧失败；提出替代路线和缺失材料。用 [decision record](references/prompt_template.md) 写清人工选择。案例仅参考 [project cases](references/project_cases.md)，不要复制平台固定写值。
7. 汇报执行过与未执行事项，按能力分别给结论。Host mock、native RAM、RTL FPS、JTAG 会话耗时均不得升级为实板稳态 FPS。

## 验收与边界

应能从每项结论返回原始文件/行号或测试路径及 SHA；缺失项必须显式可见。原始证据与公开材料分离，公开目录只放经过脱敏的逻辑 ID/摘要。工具/模型版本只记录实际会话元数据。

本技能不授予硬件访问、环境安装、外传、Git 提交或团队消息权限；遵守当前指令和仍有效的已有授权。KV260 GPIO95、PMU、AXI 地址、image 和固件都属于特定案例，不包装成其它 FPGA 的恢复处方；绑定旧工件的批准不会自动覆盖不同工件的新实验。

失败排查和本轮实际验证见 [validation](references/validation.md)。跨项目迁移时重新建立平台身份、启动契约、总线/owner 和停止条件；当前通用流程属于项目内提炼，尚未经过第二平台验证。
