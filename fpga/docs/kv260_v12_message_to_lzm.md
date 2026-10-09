# 可转发给 lzm 的交接消息

lzm，KV260 V1.2 的 CNN→Bilinear→Curve 已真板单帧通过，三个完整输出逐位一致、60 次 guard 检查通过，最小冷启动恢复也已验证。请从 `fpga/docs/kv260_v12_software_handoff.md` 开始开发 PS 串行调用、DDR buffer 分配和 Cache 同步；复用材料在 `fpga/bringup/kv260_v12/`。实跑的是文档指定的诊断 bit，正式 release 保持原样；bit/XSA 和完整数据另行按 SHA 交付。多帧、30 FPS、Linux 驱动和开机自动加载尚未验收。实验固定地址和 dcache off 不能当生产方案；上次 Cache OFF、MMU 未独立确认。实体交板前由 Master 完成性能验收。
