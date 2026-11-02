# 项目案例：可迁移的判断，平台特定的操作

本文件是根据工程报告与已保存工件整理的事件摘要；逐字提示词和 AI 回答由本轮会话索引另行关联。未经逐行会话核对，不把某方案归给特定模型或人。

以下均为 2026-10-15 整理的历史案例。工程路径和会话索引属于原来源，可能不在单独分发的技能目录或当前分支；它们是出处而非使用依赖。历史“未实现/未测”不覆盖团队后续版本。

## 案例一：从“GPIO 已释放”到实际时钟/复位证据

1. `fpga/reports/v1_2_phase7a_board_bringup.md:427-446`：debugger region 登记成功，首个真实 Bilinear AP_CTRL 仍 timeout。说明地址白名单阻断解除不等于 AXI 工作。
2. 同报告 `:495-509`：纠正 PMU 状态地址误标签，配置 clock 计算与 GPIO 回读仅能说明配置；不能推导实测频率或完整功能 reset。
3. 同报告 `:5-24`、`:54-74`：CPU/U-Boot 只读路径能取 PS 基线，但一次 PL 读仅回显后挂起，30.0587448 秒有限观察无数据/prompt，保留失败并停止；不能把未见 exception 写成无错误。
4. `fpga/reports/v1_2_phase7a_autonomous_root_cause.md:19-29`：bit DONE/EOS、VCC signature=0，PMU PL 服务之后 signature 与独立/PL0 活动观测恢复；GPIO95 direction/enable/release 恢复 canonical reset，随后真实 AXI 控制和功能通过。不同步骤证明的对象不同，不把整个初始化缺失压缩为一条普遍 GPIO 修复命令。
5. `fpga/reports/kv260_v12_board_validation.md:13-25`：历史单/双帧与冷恢复被分别记录；当前板态、长期运行、Linux、30 FPS 均未重新或未曾确认。

可复用结论：配置/活动/接口/完整功能各需自己的证据；保留先前错误标签与失败记录。PMU/GPIO 的具体值只适用于绑定 image/固件的 KV260 历史案例，本技能不提供写入执行器。

## 案例二：未知 U-Boot go 路径停止，改为 Linux 小 ring

1. `fpga/docs/kv260_v12_30fps_execution_status.md:3-5`、`:25-35`：存在历史批准，仍因现场 `go` ABI/同 EL 调用/返回和全部 DDR runtime owner 证据缺失，在连接板卡前停止。有限目录没有材料不等于全电脑没有材料。
2. 同报告 `:39-49`：缺 live proof 的装载门禁拒绝、注入 I/O=0，DDR/CSR/IP/start/计时全部0；此处是 Host gate 检查，不是板端失败。
3. `fpga/docs/kv260_v12_runtime_alternative_review.md:17-25`：约1.4 GiB主要为120帧完整输出 archive；提出三槽约75.366 MiB参考预算，复用条件绑定每帧三输出全量验证，未把该预算当成 CMA 设置或已批准地址图。
4. `fpga/docs/kv260_v12_linux_backend_review.md:19-34`：三个模块实际11路AXI master跨4HP，DMA handle 不能不经证明跨device通用，CSR和 AP_CTRL reader 需唯一 owner。
5. 同报告 `:36-50`：STOP 请求与确认不同，未知 DMA 要 quarantine；未完成真实 Kbuild/资源驱动/backend，故 Host native RAM 正确性和速度不证明板端运行或30 FPS。

可复用结论：批准不等于技术前提已成立；适时停止未知运行环境，用 OS ownership 路线降低不确定性；性能必须绑定真实计时窗、输入更新和完整正确性。

## 来源分层与可复查测试路径

- `fpga/bringup/kv260_v12/test_host_only.py`：原项目 Host mock/文件验证；若本轮没有重跑，不能引用成新增测试。
- `fpga/tools/kv260_v12_30fps/test_gates.py`、`test_host.py`：历史 go 路线 Host 门禁/准备测试；不执行旧硬件候选。
- `fpga/tools/kv260_v12_linux_perf/test_ring.py`：历史 ring 状态与 mock 测试；`native_hotpath/test_hotpath.py` 为 Host RAM 比较器验证。
- 私有逻辑工件：`kv260_v12_30fps_preparation/approved_attempt01/preflight_stop.json`、`host_revision02/host_validation.json`、`host_revision03/independent_native_test.json`。公开引用只保留逻辑 ID，原件地址不写入公共模板。

这些文件给出方案与工程结果；原始会话证据还需按 `session_index.csv` 核定，不能用报告重建“逐字对话”。
