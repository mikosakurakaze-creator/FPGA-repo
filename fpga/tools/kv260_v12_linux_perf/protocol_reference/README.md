# 三模块协议参考接口

`pipeline.c` 和 `pipeline.h` 为旧Host候选中的原字节接口副本，仅保留三模块的参数写入、读回、单次AP_START和fresh AP_DONE观察协议。源文件未因本次交接改变，来源身份记录在Host审阅清单中。

此接口没有真实Linux DMA allocator、MMIO资源所有权、ioctl、设备映射或kernel STOP机制，尚未在真实Linux板端运行。`kv_io`回调只有抽象read/write/ticks/barrier；任何模拟回调和Host测试结果都不是板端性能测量。它不能直接装载为Linux driver，也不能直接替代`ring_runner.Backend.compute`：软件端必须实现逐模块STOP与提交原子性、永久DMA引用、错误隔离、Cache/DMA同步和全部11路AXI地址域审核。

该参考代码按固定顺序CNN → Bilinear → Curve，使用CNN `0xA0020000`、Bilinear `0xA0000000`、Curve `0xA0010000`；完整寄存器及数据格式以[硬件寄存器映射](../../../docs/kv260_v12_register_map.json)和[软件交接说明](../../../docs/kv260_v12_software_handoff.md)为准。参数中的64-bit地址必须是实际设备可见且拥有的DMA总线地址，不能填CPU虚拟地址或猜测固定DDR地址。

旧U-Boot go计时方案已停止。本目录不提供其入口、链接脚本、固件、下载或执行脚本；不要将本接口的历史来源理解为旧go仍可执行。
