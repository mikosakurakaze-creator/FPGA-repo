# KV260 V1.2 当前权威 checkpoint

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

## 真实单帧结果

CNN→DDR→Bilinear→DDR→Curve 各 START 一次。三份完整输出逐 byte 匹配冻结 night_01 golden：

| 输出 | 字节数 | SHA256 |
| --- | ---: | --- |
| CNN A_low | 38,160 | `31abdd23520d32efe75928ef394017bd2f515b2805144a85735eebc9481dddd1` |
| Bilinear A_full | 5,495,040 | `ebfa58eafb70385af39b92b6c9ed2b81c3319ca63662ce002d1219051f8b2067` |
| Curve enhanced | 5,495,040 | `869e62a41010e047c3760aa6a614f0ff883566d52c3fbee273cf2a865f7eb951` |

累计 5,514,120 个 int16 元素无差异，60 次 guard 校验全部一致；27 个参数 word 写后回读符合预期。DDR staging 19,025,659B，CSR 写 120B，共 346 SET、590 GET，PS 只读 102 次、CONFIG 8 次。各模块 AP_CTRL poll 为 1→14，done/idle/ready 置位，start 和 auto_restart 为 0。Windows/JTAG poll 耗时包含 Host 传输，不能当作纯计算延迟或 FPS。

本次功能阶段无 program、PMU/GPIO/clock 写、PS reset、psu_init、硬件 retry 或 rollback。
此前 Host 首次入口因 PowerShell module 自动加载问题在任何硬件访问前停止，物理预算为 0；修复后实际硬件实验只执行一次。冻结操作库未为让门禁 PASS 而改变。
原始 category 文本为 `netlist`，原样保留；功能 PASS 由原始交易、完整输出及 guard 独立确认，不依赖此标签。

上次最后确认 D-cache OFF，MMU 未独立验证。UART、调试客户端、63 个临时 metadata 和本轮 owned server 已关闭；这些是结束时证据，不无依据推断之后板态。诊断 scratch 的当次覆盖授权不构成最终软件固定地址或后续实验授权。

## 正式 release 与当前诊断 image

真实单帧使用额外 EMIO/独立 CFGMCLK 观察器的诊断 bit `artifacts/diagnostic_v12_independent_clock.bit`，7,797,826B，SHA256 `347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86`。
正式 Phase6 bit SHA256 `8a6c315b50799fb22cb8bfb6f376e3e6992ac41da0abe9c87a8ffc9ced85c915` 和 XSA SHA256 `09661c4822f05b8c54b000d2fc13893fac3356a970acb4c70a8ca89fb2693ead` 未覆盖；正式 bit 尚未独立重演本次真实功能链，不能继承诊断 bit 的单帧 PASS。

既有正式 CNN 数值/overlay/build 配方、Bilinear/Curve 源码及 BD 保持不变。前一次实测保护核对的 481 个文件未改。本次只整理交付说明、三份报告与新增复用包，不改正式设计或模型。

## 保留的正式历史里程碑

- [Phase4E 写回 retirement 优化](v1_2_phase4e_write_retirement_optimization.md)。
- [Phase4F 8 帧 RTL](v1_2_phase4f_short_multiframe.md)：100MHz 下最差稳态输出间隔 3,307,317 cycles，约 30.236 FPS；属于 RTL 证据，不是真板 FPS。
- [Phase4G 正式 CNN IP](v1_2_phase4g_implementable_cnn_ip.md)：固化同源 write-credit overlay，单帧同源数值验证。
- [Phase5 implementation](vivado_three_module_v1_2_implementation.md)：100MHz routed timing/DRC 已完成。
- [Phase6 bit/XSA](vivado_three_module_v1_2_bitstream_xsa.md)：正式产物及接口身份记录。

## 接续边界

先按软件交接开发拥有 DDR buffer、正确缓存同步及可靠板端计时的运行程序。
第一次连续测试采用明确授权的两帧复用，逐阶段全量比对；不同输入 A→B→A 和长批次另行准备/批准。
真实 30FPS、Linux driver、开机自动加载及完整实体交板验收尚未完成。
