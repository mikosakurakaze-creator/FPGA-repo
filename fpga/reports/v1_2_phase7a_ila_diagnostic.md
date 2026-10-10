# V1.2 Phase7A 观察通路与冷启动诊断

更新：2026-10-09，交付审核版。完整历史正文、原始交易和 Host 日志仍由 Master 离线保管；共享版只保留已核验结果与证据身份，不上传重复日志、机器专用配置或板卡序列号。

当前软件交接从 [START HERE](../docs/kv260_v12_START_HERE.md) 开始；最新 [权威板测摘要](kv260_v12_board_validation.md) 记录 A→B 不同输入 S1 双帧 PASS，以及 `p7cold_resume_1009_02` 冷恢复。本页下方单帧和 cold01 证据保留为历史；超过两帧的持续运行和真实 30 FPS 尚未验证。

| 真板状态 | 结果 |
| --- | --- |
| BOARD_CONTROL_ACCESS | PASS |
| BOARD_BRINGUP_BASE | PASS（真实单帧） |
| BOARD_MULTI_FRAME | S1_TWO_DIFFERENT_FRAME_PASS |
| BOARD_30FPS | NOT_TESTED |

真板证据 ID：`p7single_frame_1009_01/attempt02`，`actual_evidence.json` SHA256 `15871215a8fc5568f15e9a69ef3ce6dd0ff61d150a093663d161dfacf2ab4c6b`；独立原始对账 `actual_scope_audit.json` SHA256 `2d06e122417f77ef0a34dce953ca841aa5f4f02d56f9f050d9a3aa0ff15d9186`。冷启动控制恢复证据 ID：`p7cold_resume_1009_01/recovery01`，根目录 `cold_recovery_evidence.json` SHA256 `8e535d6641923abf798043a93ff5f6ecae0f4b2fdaef5abf7e0575c46229b7ef`。

公共入口：[软件联调交接](../docs/kv260_v12_software_handoff.md)、[精确库/小样本/单帧复现](../bringup/kv260_v12/README.md)、[连续运行及性能验收计划](../docs/kv260_v12_acceptance_plan.md)。

## 观察通路结论

本报告沿用历史 ila_diagnostic 文件名；最终证据来自静态网表、EMIO 观察和 PS/PL 实际访问，不声称已有 ILA waveform 捕获。
诊断 routed DCP 已证明 EMIO6 的 signature 由 VCC 常量 1 驱动，EMIO6→global GPIO84→bank3 bit6 对应无误；旧 DATA_3_RO 连续 16 次为 0 时，整条输入交付尚未成立，不能据同一路径判定 PL0 没活动。

独立观察器从 STARTUPE3/CFGMCLK 驱动；它不取自 PL0、不回馈功能 reset 或 clock。
EMIO bits7..0 分别为 EOS_sync、VCC_signature、independent_seen、independent_counter[24]、peripheral_aresetn、interconnect_aresetn、PL0_seen、PL0_counter[24]。
其 routed DCP SHA256 `8ead58f3b7641e179693d7fa64fbc7f7ade05d5ec821365e8fcbfc9b0fd532b9`，41,098,381B；对应 bit 身份见 checkpoint。静态 source 身份与真板状态证据应分别理解。

## 冷启动最小恢复已重演

已实际执行：只读 U-Boot 环境盘点与独占/身份门禁 → GPIO DATA LOW 时 DIRM/OEN bank5 bit31 各 RMW 置位 → 同一诊断 bit program 一次且不 PS reset → CONFIG 门禁 → PMU 两笔服务 → signature 恢复 → 一次 masked GPIO release → canonical reset/PL0 观察 → 三个 AP_CTRL 各读一次为 `0x00000004`。
PMU Host 写为 `0xFFD80118←0x00800000`、`0xFFD80120←0x00800000`；release 为 `0xFF0A002C←0x7FFF8000`。执行仍需当次批准及库中的全部前提，不是通用 U-Boot/Linux 初始化脚本。

PMU 后 VCC、EOS、独立观察和 PL0_seen 交付恢复；release 后两项 canonical reset HIGH，DATA3 实际观察 `0xEF→0xEE`，PL0 counter bit0 有变化。
此处证明活动，不是实测 100MHz 频率。随后真实 DDR/三模块数值运算验证了功能通信。

项目“GPIO95”是 **EMIO95/global GPIO173/bank5 bit31**，不能按 global GPIO95 操作。
8-bit user EMIO 配置与 reserved reset95 的关系已通过真实 IP/primitive/netlist 独立核对，且真板 release 生效；不能仅凭 `C_EMIO_GPIO_WIDTH=8` 推断 reset95 被截掉。

## 未知与安全边界

尚未直接定位原始输入交付失败涉及的具体 isolation bit、缺失 firmware 分支或系统级启动配置。
旧观察失败不能证明芯片损坏、PL0 停止或 bit 未配置。最终成功记录不等于 cold boot 自动修复。
再上电须重新取得 CONFIG、GPIO、PMU、reset、AP_CTRL 等易失证据；严禁扩大为完整 psu_init、reset、直接 power/isolation/clock 写。
