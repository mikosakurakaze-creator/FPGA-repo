# KV260 V1.2 软件与实体交接清单

2026-10-09。Master决定现在开始向lzm交接；不把完成Linux或30 FPS当作交接前置条件。本次范围是Host核验、文档与选择性Git提交/正常Push，没有新板端操作或自动外发。

| 项目 | 当前结果 / 接收动作 |
| --- | --- |
| 阅读入口 | [START_HERE](kv260_v12_START_HERE.md)，随后[软件交接](kv260_v12_software_handoff.md) |
| Git源码 | 正式BD、release recipe/HLS、权威实现报告已存在；本次补现有Linux接口/native校验/测试与最新交接资料 |
| 真板功能 | 单帧PASS；S1 A/B双帧各模块2次、六输出11,028,240 INT16零差异、120/120 Guard；[证据摘要](../reports/kv260_v12_board_validation.md) |
| 本次诊断bit | SHA256 `347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86`；没有配套诊断XSA |
| 正式bit/XSA | 独立保留，不等同诊断image；不能自动继承诊断板测PASS |
| 独立文件 | bit/XSA、A/B模型输入Golden、真实输出及既有构建产物；[大文件清单](kv260_v12_large_artifacts.md) |
| 冷启动 | 历史最小恢复已实跑，依赖PMU服务/GPIO95 release；具体顺序见交接说明，非Linux开机服务 |
| Cache/MMU | 最后D-Cache OFF、MMU未评估；没有当前实时状态证明 |
| 30 FPS/长期运行 | NOT_TESTED，后续双方共同验收 |
| Linux | 启动环境匹配、实际驱动装载、11 master/4HP DMA域、Cache/生产buffer、自动加载与相机显示未完成 |
| 旧go | 已停止，不作为推荐运行步骤或当前批准 |
| 分发 | Git Push回执记录分支/commit；本地大包未外发，渠道由Master安排 |

## 现在的交接动作

1. lzm取得本次Git commit并阅读START_HERE；检查正式设计及当前ABI。
2. Master按独立manifest安排大文件渠道；接收方逐项核bytes/SHA，确认A/B数据和九份真实输出齐备。Linux第三方软件包不随本次Git/独立包再分发。
3. 记录板卡/启动介质、供电及线缆、加载image身份、最后可信运行状态、历史日志保管方和接收人。敏感本机连接配置单独保管。
4. 本次不查询或改变板状态。实际交板前由Master安排确认存储和IP无在途事务、调试连接处理；未确认空闲不能宣称可安全断电。异常不自动reset/power-cycle。
5. lzm牵头Linux启动/驱动/DMA/Cache/调用链，硬件端提供设计接口和支持；双方另行批准并完成真实30 FPS验收。

当前有效状态保持：BOARD_BRINGUP_BASE=PASS；BOARD_MULTI_FRAME=S1_TWO_DIFFERENT_FRAME_PASS；BOARD_30FPS=NOT_TESTED。
