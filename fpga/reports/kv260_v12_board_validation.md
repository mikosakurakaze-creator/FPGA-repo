# KV260 V1.2：真实板测交接摘要

2026-10-09。本文汇总已完成的真实板测，不新增运行。公共机器摘要为[s1_two_frame_evidence.json](../bringup/kv260_v12/s1_two_frame_evidence.json)；软件工作先读[START_HERE](../docs/kv260_v12_START_HERE.md)。

| 状态 | 当前结果 |
| --- | --- |
| BOARD_BRINGUP_BASE | PASS |
| BOARD_MULTI_FRAME | S1_TWO_DIFFERENT_FRAME_PASS |
| BOARD_30FPS | NOT_TESTED |

## 已完成的真实验证

单帧 `p7single_frame_1009_01/attempt02`：CNN→Bilinear→Curve完整计算，三输出5,514,120个INT16原码全量零差异，各IP一次START，60次Guard通过。

最新S1 `p7s1_prepare_1009_02`：A→B两种不同输入，三个模块各启动两次；六份输出共11,028,240个INT16标量全量零差异，120/120 Guard检查通过。每次保存本帧输出、捕获新的done/idle，帧间无reset，不复用前帧结果。B为Q14数值补集，低分辨率19,074/19,080、全分辨率2,747,520/2,747,520元素改变，三输出对均不同。

冷恢复 `p7cold_resume_1009_02`：一次诊断program、GPIO模式两笔、PMU服务两笔、GPIO95 masked release一笔后，三个AP_CTRL均为0x4；没有DDR写或IP启动。GPIO95是EMIO95/全局GPIO173/bank5 bit31。随后功能验证已证明所用PS/PL初始化、AXI控制与实验DDR数据通路可工作。具体历史初始化步骤在[交接说明](../docs/kv260_v12_software_handoff.md)。

## 硬件身份与证据边界

真板成功image为7,797,826B的 `diagnostic_v12_independent_clock.bit`，SHA256 `347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86`。正式Phase6 bit/XSA另有身份，诊断image没有配套XSA；不能把正式XSA当成已验证诊断Linux平台。

最后D-Cache OFF，MMU未评估；本次没有重新连接确认当前板态。单/双帧依赖guarded JTAG/U-Boot流程。Host观察耗时、715.841秒S1调试会话、RTL 30.236 FPS、Host mock/native RAM测试均不是真实计算FPS。

未完成：真实30 FPS、长期连续运行、Linux DMA/MMIO装载执行、匹配完整Linux启动环境、全部11 master/4HP地址域与DMA所有权、生产Cache/buffer管理、自动加载及相机到显示。

## 原始证据身份

原件本地保留；下列逻辑ID和SHA绑定未脱敏原件，不代表它们自动随Git克隆提供。独立传输包包含保存的真实输出及脱敏摘要。部分原始日志含设备/主机信息，需Master按接收渠道单独审阅。

| 原始证据ID | SHA256 |
| --- | --- |
| `p7s1_prepare_1009_02/S1_handoff.md` | `16d0cefe2eab8215437888192032f46a7ecc5324b9e08a62fe66e80bbc6acfbc` |
| `p7s1_prepare_1009_02/actual_s1_evidence.json` | `9491bbf18fc51e18bd7bbd0cad7f8fa5599cb2daadb34be8b7f746ebde5fb253` |
| `p7s1_prepare_1009_02/runner_candidate/actual_scope_audit.json` | `532b536fc6e80fa9fdc11a4d029305371138b4f7e5b4f17f15c328057ba2dc4e` |
| `p7s1_prepare_1009_02/runner_candidate/actual_data_audit.json` | `49dd38e61f17209d9a1b22e05090d5bae87cc4db53616c1805f597a657bf5656` |
| `p7single_frame_1009_01/attempt02/actual_evidence.json` | `15871215a8fc5568f15e9a69ef3ce6dd0ff61d150a093663d161dfacf2ab4c6b` |
| `p7single_frame_1009_01/attempt02/actual_scope_audit.json` | `2d06e122417f77ef0a34dce953ca841aa5f4f02d56f9f050d9a3aa0ff15d9186` |
| `p7cold_resume_1009_01/cold_recovery_evidence.json` | `8e535d6641923abf798043a93ff5f6ecae0f4b2fdaef5abf7e0575c46229b7ef` |
| `p7cold_resume_1009_02/cold_recovery_evidence.json` | `88a0906048623f8c3881d499dab9d80b5c8ccd6366a5d510cc05c5f70186e060` |
| `p7cold_resume_1009_02/recovery01/actual_scope_audit.json` | `465bf4f276b33ee045386070269afff512a47cc15c452a262647db8096d9c1ac` |

本次Host核验重算摘要/独审及九份真实输出，原始文件、正式release与历史失败记录未覆盖。未进行新板端配置、Cache/DDR/CSR写、IP启动或Linux启动。
