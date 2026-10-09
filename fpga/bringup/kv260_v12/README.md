# KV260 V1.2 已验证诊断与单帧复用包

从 [软件交接](../../docs/kv260_v12_software_handoff.md) 开始。
本目录保留实际成功批次使用的四个 Tcl 操作库、TCF transport、诊断观察器
RTL/XDC 的原始字节，并以 `manifest.json` 锁定 SHA256。正式 CNN/Bilinear/Curve
源码、正式 BD、bit/XSA 构建 recipe 继续使用现有 release，未替换。

`single_frame_evidence.json` 是 2026-10-09 历史真板成功结果的公共摘要。
三个完整输出 bit-exact、每个 IP 一次 START、60 次 guard 检查通过。
多帧与 BOARD_30FPS 尚未实测。原始日志另行保管，不能把此摘要作为当前板态证明。

## Host-only 最简复现准备

Python 3.9+，不需要 JTAG/UART，不操作板卡。六个小型 `samples/*.hex`
保存原始低分辨率输入、参数与 CNN golden；解码后的字节 SHA 必须匹配 manifest。
三个大文件 `model_input_q14.bin`、`expected_a_full_q14.bin`、
`expected_enhanced_q14.bin` 通过外部 artifact 包取得，不能从 CNN 小图简单推造。
完整九文件集按 manifest 校验，固定 night_01 为已经实跑的同一帧。

```text
python fpga/bringup/kv260_v12/prepare_payloads.py --data-root <artifact-data-dir> --output <new-local-run-dir>
python fpga/bringup/kv260_v12/verify_outputs.py --data-root <artifact-data-dir> --actual-dir <saved-actual-dir>
python -m unittest discover -s fpga/bringup/kv260_v12 -p test_host_only.py
```

第一条仅在本机生成 30 个 staging 文件、全套参数数据和 `core_policy.tcl`。
`sf_core_policy` 只供 `::single_frame::run` 的 callbacks 复用；它**没有** live
transport 必需的 SET/GET 白名单、metadata、独占、设备身份或当前 CONFIG 门禁。
`transport.tcl` 只有配齐原有审核过的 guarded wrapper/whitelist 后才能使用。
本目录不提供自动连接或真实执行入口，也不将已消耗预算的旧执行目录再次运行。
Linux/bare-metal 软件可按交接实现 callbacks，必须重新验证缓存和设备所有权。

## 冷启动库的边界

按交接中的已验证顺序复用 `gpio95_mode_candidate.tcl`（两笔 RMW，保持 DATA LOW）、
`pmu_pl_recovery_candidate.tcl`（最多两笔 PMU 服务写）与
`gpio95_release_candidate.tcl`（一次 masked release）。每个库检查明确批准 token，
调用一次即消耗预算；传输错误、超时或前提变化时停止，不 reset、不 retry/rollback。
source 这些 Tcl 仅定义程序，不会连接硬件。冷启动 program 不在本目录自动执行。

`diagnostic/` 只是已验证额外观察逻辑的精确源码。独立 CFGMCLK 是状态观察，
不是功能 PL0 时钟或性能计时器。完整诊断工程依赖外部冻结 catalog、BD 与 build
audit；不声称仅靠这两个文件能复现相同 bitstream。

## 板态和交付限制

当前仅有上次实测的 D-cache OFF、MMU NOT_ASSESSED 记录；不推断此后未变化。
诊断 64MiB scratch 的专用覆盖许可只属于当次实验，**不是软件固定分配地址**。
生产软件需拥有 DMA buffer，并进行 clean/invalidate、memory barrier 和同步。
任何新 DDR/CSR/IP/cache/program 操作须取得对应范围批准。
交板前还需完成 [连续运行与性能验收](../../docs/kv260_v12_acceptance_plan.md)，
并将 hash 匹配的 bit/XSA、完整测试数据、原有执行封装和环境说明另行交付。
