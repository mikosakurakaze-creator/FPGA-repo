# 可转发给 lzm 的交接消息

2026-10-09。本文是消息草稿，本次没有自动发送。

lzm，KV260 V1.2 现在开始软件端交接，请先读 [START_HERE](kv260_v12_START_HERE.md)，再读 [完整接口说明](kv260_v12_software_handoff.md)。诊断 bit 的 CNN→Bilinear→Curve 单帧与 A/B 不同输入 S1 双帧已真板 PASS：各模块两次启动，六输出 11,028,240 个 INT16 全量零差异，120/120 Guard 通过；最小冷恢复也已成功复现。

真实 30 FPS、长期运行和 Linux 驱动装载尚未验收。现有 Linux 计时接口与 native C 校验代码可供集成，实际 DMA/MMIO backend 仍需实现。成功实验依赖 JTAG/U-Boot，固定 DDR 地址及 dcache off 不能直接作为生产方案，旧 go 性能路径已停止。

bit/XSA、A/B 模型输入与 Golden、真实输出通过独立 manifest 另行传输，渠道由 Master 安排。诊断 bit 与正式 bit/XSA 不同，当前没有诊断配套 XSA。lzm 牵头 Linux 启动环境、驱动、DMA/Cache/buffer 与调用链，硬件端提供已验证设计、接口及支持；双方后续共同验收 30 FPS，性能验收不是现在交接的前置条件。
