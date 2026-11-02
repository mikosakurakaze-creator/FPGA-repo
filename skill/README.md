# 技能包

按竞赛指南 3.3.5.2 和 3.3.5.4，将可独立复用的技能放在仓库根目录 `skill/`。每项均包含 `README.md`、`SKILL.md`、使用方法、适用/失效条件、经验来源与验证边界。

| Skill | 适用任务 | 使用入口 | 当前验证范围 |
| --- | --- | --- | --- |
| PYNQ Overlay 联调与校验 | 区分 MMIO master/AXI DMA，检查接口合同、完整 Golden、guard 和 A/B 输出 | [说明](pynq-overlay-validation/README.md) · [SKILL](pynq-overlay-validation/SKILL.md) | Host 工具、示例和14项行为测试；本技能尚未在 PYNQ 真板验收 |
| 证据驱动 FPGA 排错 | 从观察与反证整理故障，设计最小区分实验，纠正无证据的根因或性能结论 | [说明](evidence-driven-fpga-debug/README.md) · [SKILL](evidence-driven-fpga-debug/SKILL.md) | 工程历史案例、Host 来源审阅与独立场景检查；不提供跨板通用寄存器恢复操作 |

## 复用

复制所需的整个子目录，读取其 `SKILL.md` 并按 README 提供自己的工程材料。PYNQ 离线工具只依赖 Python 3.9+ 标准库；排错技能只需文本阅读能力及使用者提供的原始记录。使用这两个技能无需原项目模型、数据集、bitstream 或私有聊天。

目录和辅助文件名使用英文；`README.md` 与 `SKILL.md` 保留标准入口名称。中文只用于文档正文。项目其他目录与竞赛推荐目录的对应见[根 README](../README.md#竞赛目录对照与技能包)。

Host 文件或文档检查不等于新板测；历史版本的结论仅适用于其绑定工件，不能外推到其他镜像或团队后续版本。
