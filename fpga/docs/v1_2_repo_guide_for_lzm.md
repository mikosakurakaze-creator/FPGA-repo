# KV260 V1.2 仓库使用说明

当前正式版本已完成 **CNN → DDR → Bilinear → DDR → Curve** 的 RTL 级 30FPS 验证、正式 CNN IP 固化、100MHz post-route 和 bitstream/XSA 交付；**真实 KV260 板测尚未完成，BOARD_30FPS = NOT_TESTED**。

这份导航供 LZM、WZH 和其他队友使用，对应 `codex/curve-fp32-baseline` 分支。先读下面的入口，普通接续工作不需要先运行验证或构建脚本。

## 最重要的入口

以下路径均相对仓库根目录。

| 入口 | 用途 |
| --- | --- |
| [fpga/docs/v1_2_status_for_team.md](v1_2_status_for_team.md) | **先看这个**，知道项目做到哪了、还缺什么。 |
| [fpga/docs/v1_2_hardware_handoff.md](v1_2_hardware_handoff.md) | 写 PS 软件、接续板测的主入口：控制地址、DDR 布局、IP 关系和当前硬件交付信息。 |
| [fpga/docs/v1_2_hw_register_map.json](v1_2_hw_register_map.json) | 机器可读的 CSR、pointer offset、DDR payload/layout 和 release identity；写 PS 程序或自动生成 driver 时优先用它。 |
| [fpga/reports/v1_2_phase4f_short_multiframe.md](../reports/v1_2_phase4f_short_multiframe.md) | 三模块 8 帧流水、RTL steady-state 30FPS PASS 的正式证据。 |
| [fpga/reports/vivado_three_module_v1_2_implementation.md](../reports/vivado_three_module_v1_2_implementation.md) | Vivado implementation、route、post-route timing、DRC 和资源结果。 |
| [fpga/reports/vivado_three_module_v1_2_bitstream_xsa.md](../reports/vivado_three_module_v1_2_bitstream_xsa.md) | 最终 bitstream/XSA 的路径、大小、SHA256 和 hardware handoff 证据。 |

约 **30.24 FPS** 来自 Phase4F 的 8 帧 RTL 测试，按 100MHz 和最差稳态输出间隔计算。当时验证的是 write-credit overlay；Phase4G 随后将相同的三个 writer 固化为正式 CNN IP，并通过 CNN 同源单帧验证，详见 [Phase4G 报告](../reports/v1_2_phase4g_implementable_cnn_ip.md)。

## 各目录是干什么的

| 目录 | 看它的理由 |
| --- | --- |
| [fpga/ip/cnn_v1_2_writecredit/](../ip/cnn_v1_2_writecredit/README.md) | **正式 CNN V1.2 IP 的可复现构建 recipe**，需要重建正式 CNN IP 时从这里开始。 |
| [fpga/hls/zero_dce_cnn_v1_2_30fps/](../hls/zero_dce_cnn_v1_2_30fps/) | CNN 优化源码和 candidate；正式数值基线仍来自 frozen r4，write-credit 性能修正通过正式 IP recipe 固化。 |
| [fpga/perf/v1_2_phase4e/](../perf/v1_2_phase4e/) | CNN write-response retirement 优化及验证脚本。 |
| [fpga/perf/v1_2_phase4f/](../perf/v1_2_phase4f/) | 8 帧完整系统流水 30FPS 验证脚本。 |
| [fpga/perf/v1_2_phase4g/](../perf/v1_2_phase4g/README.md) | 正式可实施 CNN IP 固化、同源审计与集成验证脚本。 |
| [fpga/perf/v1_2_phase5/](../perf/v1_2_phase5/) | implementation、route、timing、DRC 的运行与审计脚本。 |
| [fpga/perf/v1_2_phase6/](../perf/v1_2_phase6/README.md) | bitstream、XSA、hardware handoff 的执行与审计脚本。 |
| [fpga/reports/](../reports/) | 权威结果和 checkpoint；判断当前是否 PASS，优先看本页链接的正式报告。 |

正式 CNN 的构建流程是 **frozen r4 export → SHA gate → deterministic overlay patch → package**。不要直接手改 generated RTL，也不要把实验 candidate 直接替换正式 release。

Phase4E/F/G/5/6 主要用于复现、审计和查证，普通队友通常不需要执行。仓库并非空 clone 后即可完整构建：还需要冻结的 r4 export、参数/数据及相关外部 IP、工具和历史构建输入。准备复现前先读 [release 复现边界](v1_2_release_reproduction.md)，再按各 recipe 的输入要求安排。

## 我要做什么，就看哪里

| 如果我要…… | 从这里开始 |
| --- | --- |
| 看现在做到哪 | [当前状态](v1_2_status_for_team.md)。 |
| 写 PS 软件 | [hardware handoff](v1_2_hardware_handoff.md) + [register map](v1_2_hw_register_map.json)。 |
| 看 CNN 接口 | 正式 CNN driver/header（位置见下文）+ [register map](v1_2_hw_register_map.json)。 |
| 重新构建 CNN 正式 IP | [正式 CNN recipe](../ip/cnn_v1_2_writecredit/README.md) + [复现边界](v1_2_release_reproduction.md)。 |
| 查 30FPS 证据 | [Phase4F 报告](../reports/v1_2_phase4f_short_multiframe.md)。 |
| 看 100MHz 是否收敛 | [Phase5 implementation 报告](../reports/vivado_three_module_v1_2_implementation.md)。 |
| 找 bitstream/XSA 信息 | [Phase6 bitstream/XSA 报告](../reports/vivado_three_module_v1_2_bitstream_xsa.md)。 |
| 板子到了继续干 | [hardware handoff](v1_2_hardware_handoff.md) + [当前 checkpoint](../reports/v1_2_phase4_checkpoint.md)。 |

正式 CNN driver/header 位于外部正式 package 的 `drivers/zero_dce_cnn_top_v1_0/src/`，包括 `xzero_dce_cnn_top.h` 和 `xzero_dce_cnn_top_hw.h`；package 当前路径为 `E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/`。它们随正式 package/XSA 交付，不在源码仓库中，具体位置和 header 校验信息见 handoff。

## 不要直接拿这些当正式版本

- 旧 V1/V1.1 实验文件、历史 candidate、superseded probe、aborted run。
- 本机 `E:/HLS/...` 下任意 build 目录、xsim 临时文件；只有正式报告绑定的产物才是本次交付。
- 旧 DDR contract 中与正式 fixed-point 协议冲突的描述。

**数值算术协议**以 [v1_fixed_point_protocol.md](v1_fixed_point_protocol.md) 和 [v1_fixed_point_protocol.json](v1_fixed_point_protocol.json) 为准。**当前硬件接口、拓扑和 DDR buffer 布局**以 V1.2 handoff/register map 为准：旧协议里的单 m_axi、4,070,400-byte workspace 已由六 m_axi 和六个 skip tensor 的 **2,442,240-byte workspace** 取代；workspace 各 slot 的小数位不同，不能全部当成 Q14。

## bitstream / XSA 在哪里

Git 不提交 `.bit`、`.xsa`、`.dcp` 或 Vivado build outputs；正式产物在报告里记录 **path、size、SHA256**。当前路径位于本机 `E:/HLS/kv260_three_module_v1_2_phase4/` 下：

| 产物 | 相对上述外部目录的路径 |
| --- | --- |
| bitstream | `phase4g/integration_01/project/v12_wc.runs/impl_1/system_wrapper.bit` |
| XSA | `phase6/bitstream_xsa_01/kv260_three_module_v1_2_writecredit.xsa` |

这些是当前构建机器的路径，**pull 仓库不会自动得到 .bit/.xsa 文件**。领取和核对正式 artifact 时，以 [Phase6 报告](../reports/vivado_three_module_v1_2_bitstream_xsa.md) 里的路径、大小和 SHA256 为准。团队以后可通过独立 Release、网盘或 artifact server 共享，生成物不要随手塞进 Git。

## 当前下一步

PC 侧 FPGA 开发已经基本结束。等真实 KV260 到手并安排板测后，按下面顺序接续：

1. 上电，检查 JTAG 和串口。
2. 下载正式 bitstream。
3. 做 PS AXI-Lite smoke test。
4. 分配真实 DDR buffer；仿真 BFM 地址不能直接作为板端分配地址。
5. 处理 cache flush/invalidate。
6. 跑 CNN → Bilinear → Curve 单帧，检查各阶段数值。
7. 跑 100+ frame，检查连续运行。
8. 测量真实稳态 FPS，验收 BOARD_30FPS。
9. 检查最终图像。

**BOARD_30FPS = NOT_TESTED**。RTL 30FPS、100MHz 时序收敛和 bitstream/XSA 完成，均不能替代真板验收。

## 如果你只想记住三句话

1. 三模块 RTL 流水已在 8 帧测试中验证约 **30.24 FPS**。
2. Vivado **100MHz route/timing、bitstream、XSA** 都已经完成。
3. 仓库现在主要用于复现和板测接续；下一步是 **KV260 真板验证**，当前不需要继续改 PL 算法。
