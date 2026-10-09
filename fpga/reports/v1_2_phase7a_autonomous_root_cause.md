# V1.2 自主根因排查与修复结论

更新：2026-10-09，交付审核版。完整历史正文、原始交易和 Host 日志仍由 Master 离线保管；共享版只保留已核验结果与证据身份，不上传重复日志、机器专用配置或板卡序列号。

| 真板状态 | 结果 |
| --- | --- |
| BOARD_CONTROL_ACCESS | PASS |
| BOARD_BRINGUP_BASE | PASS（真实单帧） |
| BOARD_MULTI_FRAME | NOT_TESTED |
| BOARD_30FPS | NOT_TESTED |

真板证据 ID：`p7single_frame_1009_01/attempt02`，`actual_evidence.json` SHA256 `15871215a8fc5568f15e9a69ef3ce6dd0ff61d150a093663d161dfacf2ab4c6b`；独立原始对账 `actual_scope_audit.json` SHA256 `2d06e122417f77ef0a34dce953ca841aa5f4f02d56f9f050d9a3aa0ff15d9186`。冷启动控制恢复证据 ID：`p7cold_resume_1009_01/recovery01`，根目录 `cold_recovery_evidence.json` SHA256 `8e535d6641923abf798043a93ff5f6ecae0f4b2fdaef5abf7e0575c46229b7ef`。

公共入口：[软件联调交接](../docs/kv260_v12_software_handoff.md)、[精确库/小样本/单帧复现](../bringup/kv260_v12/README.md)、[连续运行及性能验收计划](../docs/kv260_v12_acceptance_plan.md)。

## 最可能原因及证据强度

共同现象最有力的解释是 **运行环境的 PS/PL 初始化或输入交付未完成**。
bit 已 DONE/EOS，而网表 VCC signature 读为 0；执行经审核的 PMU PL 服务后 signature 与独立/PL0 观察同时恢复；GPIO95 方向/使能及 release 恢复 canonical reset；AXI 控制读取及三模块真实单帧运算随后通过。
这是观察到的因果恢复链，不是对某个 isolation bit 或特定 bootloader bug 的直接定位。

## 已排除或已纠正的方向

- EMIO6 signature 逻辑和 GPIO84/bank3 bit6 映射错误：已独立静态核对。
- 以旧失效 EMIO 读值推断 PL0 没活动：推论撤销；恢复后活动有实际证据。
- 把 user EMIO width8 当作 reset95 不存在的直接证据：真实 primitive/网表与 release 反证。
- AP_CTRL idle 读取即功能成功：已由真正 DDR staging、三次计算、完整 golden 与 guard 检查补足。
- Host PowerShell 自动加载失败：Host-only 修复且在首次硬件访问前停止，无额外硬件 retry。

没有证据支持必须更换硬件；当前功能链成功并不证明所有启动软件或缓存配置已经生产化。

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

## 交付仍需完成

共享 Git 保留正式设计与可复用操作库；机器独占、串口身份、外部冻结 IP/export、大数据和调试日志不自动上传。
不同输入/连续多帧、真实稳态 30FPS、生产缓存与 DDR 分配、Linux 驱动、开机自动加载和实体交板验收仍待完成。
先完成两帧重复启动验证，再按性能计划测量可归属的板端执行区间和端到端吞吐。
