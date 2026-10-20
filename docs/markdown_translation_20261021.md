# 中文文档整理记录

日期：2026-10-21。用户要求将 README 等 Markdown 说明直接改为中文，并把本次天气 FPGA 工作提交、推送到 `weather_fpga_integration` 分支。

## 修改内容与原因

本次检查 Git 已跟踪和拟新增的全部 36 份 Markdown 文档。原来已使用中文的文档保留；翻译或补齐以下 15 份文档中的英文说明，方便项目成员核查接口、复现流程和当前完成范围。文件名继续保留英文，原有中文命名的历史文档没有重命名。

| 文件 | 修改内容 |
|---|---|
| `README.md` | 总览、实现、验证、文档导航、原 A 组输入和 Git 状态说明改为中文 |
| `deployment/README.md` | PS 控制标题与 A53 裸机后端说明补齐中文 |
| `experiments/onchip_frame/README.md` | 实验标题改为中文 |
| `experiments/stream_frame/README.md` | 流水架构、复现入口、验收与结果改为中文 |
| `docs/a_compute_handoff.md` | A 组交付身份、接口、原始证据与历史跟进改为中文 |
| `docs/candidate_package.md` | 软件候选、整数规则与 IP 证据范围改为中文 |
| `docs/frozen_build_inputs.md` | 冻结输入表的英文说明改为中文 |
| `docs/image_evaluation_request.md` | 画质评测所需样本、元数据和原始输出要求改为中文 |
| `docs/open_items.md` | 已通过和未完成验收清单改为中文 |
| `docs/system_integration_20261020.md` | 寄存器表补齐中文字段说明 |
| `docs/v1_2_reuse_matrix.md` | 旧系统参考与天气模块独立验收要求改为中文 |
| `docs/vitis_windows_startup.md` | 启动故障、修复、命令及历史验证范围改为中文 |
| `docs/weather_dataflow.md` | 模式、v1 分块、v2 流水、上板与集成边界改为中文 |
| `docs/weather_ddr_contract_draft.md` | v1 DDR/AXI-Lite 合同改为中文 |
| `model/zero_dce_pp/weights/README.md` | 官方权重来源、哈希与使用限制改为中文，未修改权重文件 |

历史说明增加了时间范围或当前报告链接；数据流中分别说明 v1、旧串行整帧和当前流水版，避免将旧“未执行”状态理解成当前状态。没有改变计算核、模型结构、量化算术、寄存器偏移或外部 ABI。

## 实际核验

- 15 份修改文档的代码块与翻译前一致，包括示例命令和原始诊断日志。
- 文档中的提交身份和 SHA-256 集合与翻译前一致；UTF-8 可解码，没有引入替换字符。
- 当前流水核源码/脚本和 PS 控制器源码仍与已通过的主机/HLS/驱动报告哈希一致。
- Python 脚本语法检查通过。
- 提交前核对文件范围、忽略规则、远端上游和暂存内容；不提交 `work/`、`build/`、数据或运行输出。

这是文档整理，没有重新运行 HLS、RTL 或布局布线，也没有进行板测。原硬件通过记录及 A53 ELF、真板、持续视频等未完成项见 [当前流水版报告](stream_revision_20261020.md)。

## 提交范围

本次提交包含已经审核过的天气流水核、控制与验证脚本、接口和验证报告，以及本次中文文档整理。当前工作分支为 `weather_fpga_integration`，推送目标为 `origin/weather_fpga_integration`，其他分支不在本次范围。

Commit Message：`feat: integrate weather frame pipeline with Chinese documentation`。最终提交身份和远端是否同步以实际 Git 结果为准。
