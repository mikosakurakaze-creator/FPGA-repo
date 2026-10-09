# KV260 V1.2 实体交板验收清单

2026-10-09。当前 **可开始软件联调，尚未完成最终性能验收**。
Master 保存板卡及原始日志；不向 lzm 自动发送消息或交付硬件。

| 项目 | 当前结果 / 交板前动作 |
| --- | --- |
| Git 源码 | 现有开发分支上的正式 HLS、write-credit recipe、BD 与构建配置已核验；交付 commit 由本次 Push 回执确定 |
| 接口及启动说明 | [软件联调交接](kv260_v12_software_handoff.md) |
| 可复用功能验证 | [Host-only 单帧准备及完整输出比较](../bringup/kv260_v12/README.md)，live guarded wrapper 需另行转交配置 |
| 诊断 bit | `artifacts/diagnostic_v12_independent_clock.bit`，SHA256 `347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86`；本次真实单帧所用 |
| 正式 bit/XSA | 原 Phase6 artifact 未替换；身份见 [正式 register map](v1_2_hw_register_map.json)；正式 bit 真板复验仍需另行批准 |
| 完整测试数据 | `manifest.json` 的九个 raw 资产；六个小型 hex 已入库，三个大文件另行分发并校验 SHA |
| 环境 | Vivado/Vitis 2025.2、K26、实际 U-Boot 2023.01；版本字符串是已盘点结果，不证明已取得可复现 boot firmware/source |
| 冷启动 | 最小恢复已实跑；每次恢复须新证据和明确修改范围，禁止直接完整 psu_init |
| 连续多帧 | NOT_TESTED；重复启动→不同输入 A→B→A→长批次逐级验收 |
| 真实 30FPS | NOT_TESTED；四类时间及板端计时要求见 [验收方案](kv260_v12_acceptance_plan.md) |
| 生产软件 | Linux driver、buffer 分配/缓存同步、开机自动加载未实现，不能把 JTAG/U-Boot 调试器当生产交付 |

## 完整交板动作

1. Master 审核新的板端范围并完成连续/性能验收，记录 Git commit、bit SHA、实际环境。
2. 把 hash 匹配的诊断 bit、正式 bit/XSA、九文件数据、必要 frozen IP/export、
   原有 guarded wrapper 的本机配置另行转交；不要把凭证、私有环境或大日志 Push。
3. 由 lzm 按最小恢复文档在授权情况下复现单帧，记录输入、输出 SHA、guard 与板态。
4. 交板记录包含总帧数、总时间、平均 FPS、帧间/最大延迟、错误数量及数据正确性。
   同帧稳定性成功不能替代不同帧或 30FPS 结果。
5. 停止运行，保存日志，核对无存储/IP 未完成事务，关闭本轮 UART/JTAG；
   无法确认空闲则报告风险，不能宣称安全断电或自动 reset/power-cycle。

## 避免重复底层排查

没有新失败证据时直接沿已验证最小序列恢复，按失败阶段记录一次即可。
GPIO95 是 EMIO95/global GPIO173；若 signature 尚未交付，不用旧 clock 观察判断 PL0。
若 CSR/DDR 不返回或数值/guard 异常，停止提交，不自动 reset、retry、rollback 或扩写寄存器。
保留精确日志交由 Master 批准下一次最小恢复。
