# 提示词及决策记录

以下为本轮新增复用模板，不是历史用户或 AI 的逐字原话。

```text
用证据驱动方法审阅 FPGA 问题：{symptom_and_stage}。
工程/平台及工件身份：{source_versions_image_firmware_sha}
只读来源范围：{project_logs_sessions_reports}
当前授权：{host_only_or_explicit_bounded_experiment}
输出位置：{new_archive_directory}

分别列出原始观察、当时假设、实际命令/工具、结果、反证、人工判断与修正。
每项绑定原始文件和行号/交易号/测试路径及 SHA；缺原始会话时标“根据日志重建”，不要补写对话。
区分配置、clock 活动、控制访问、单/双帧正确性、RTL 性能与真实持续 FPS。
多项修复后的成功不得等同于单一根因证明。
没有启动 ABI、内存/DMA owner 或时间域证据时列 NOT_PROVED，不能试跑补证。
保留失败和停止点，列已执行/未执行及下一步最小所需材料。
```

逐事件记录模板：

| 字段 | 内容 |
| --- | --- |
| event_id / time / continuation | 本问题事件 ID、来源时间、关联会话；未知不得猜测 |
| symptom / raw_observation | 原始记录摘录及精确 locator；去除公开不必要的个人信息 |
| hypothesis / status | 具体假设和 PROPOSED/REFUTED/SUPPORTED/NOT_PROVED |
| intended_experiment | 能区分假设的最小观察、预期差异、执行预算及停止条件 |
| actual_command / result | 当时真实工具/命令与日志；计划不得写成 EXECUTED |
| counter_evidence | 哪项观测不支持前一假设；还存在何种混杂因素 |
| human_decision / correction | 可定位的用户选择；归属待核时不擅自认领 |
| evidence / hashes | 原件逻辑 ID、SHA、源码/提交/测试路径与来源平台 |
| claim_boundary / next | 本结果证明什么、未证明什么、继续需哪些材料 |
