# 工程交付索引

1. 最终硬件身份：`hardware/manifest.json`、`hardware/SHA256SUMS`；BIT/BIN/HWH/XSA 四件套不得混用其他版本。
2. 精确实现输入：`hardware/source/implemented_inputs`；其中包含五类 IP 和 Prepare 生成 RTL、BD 重建 seed、集成脚本；六 FIFO 定向修改对应 `hardware/source/generated_smartconnect` 的 132 份 wrapper。
3. HLS C 原始模型：`source_models/fpga/hls`、`source_models/fpga/perf`、`source_models/compact_d`；Prepare C 与融合 RTL 在 `hardware/source/hls`、`hardware/source/rtl`。低照度来源锁定 `3c9e41a35fc08d44ba0552ce6916a421f98f94d7`，去雨雾参数 bundle `2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`。
4. 冻结权重：`hardware/model`；去雨雾内嵌参数与生成脚本在 `source_models/compact_d`。
5. 地址、接口、时钟：`hardware/address_map.json`、`hardware/register_map.*`、`hardware/clock_reset.md`；主通路约100 MHz，去雨雾约200 MHz。
6. PS：`ps/app.py` 为 GTK 前端，`engine.py` 为处理/检测/视频，`compare_view.py` 为 Cairo 滑动对比，`hardware_service.py` 为独占服务；`ps/driver` 为 Linux 六槽批处理驱动与 DT 源码。
7. 上板兼容工具：`ps/legacy_loader` 仅包含所有权检查、官方 base 状态检查和 overlay 写入函数所需源码，不携带旧镜像。`ps/driver/load_reference.py` 供新加载入口调用 `load_image()`，其历史 benchmark main 不作为当前运行入口。
8. 综合/实现证据：`hardware/reports/routed_utilization.rpt`、`export_verified_timing.rpt`、`routed_cdc.rpt`、`routed_drc.rpt`、`route_status.rpt` 和 `hardware/evidence/timing_margin_audit.json`。
9. 验证：`validation/host` 为打包后运行的主机回归；`validation/board` 为原软件优化测试；`validation/fifo_hardware` 为最终硬件长测试原记录；`validation/package_board` 为本次整理脚本在真实板端调用的输出比较。
10. `validation/historical_scripts` 和硬件包内历史脚本保留原路径与历史语境；可移植的复现入口是本包 `scripts/`。原证据中的绝对路径属于来源记录，不是当前构建必需路径。
