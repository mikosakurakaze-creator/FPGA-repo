# KV260 V1.2：runtime替代方案交接

2026-10-09。本文保留已审核的候选设计与结论，供lzm集成；本次不继续开发FPS框架、不板端操作。BOARD_30FPS=NOT_TESTED。

## 旧go已经停止

Host有界检索已有工程、备份、可访问介质和候选归档，没有找到能可信绑定当前板卡U-Boot/BOOT.BIN构建的材料。部分归档和VM guest文件系统未检查，不能声称全机绝无备份。文件存在、相近版本/日期、相同DT都不证明当前bootchain匹配；没有候选BOOT.BIN可进行分区身份审核。

完整go ABI/CPU异常级/返回约定及DDR运行时所有权没有证明，GO_RUNTIME_CONTRACT=NOT_PROVED。不得通过试运行来补证；旧裸机go固件和执行脚本只在本地历史目录保留，不作为推荐交接流程。

## 推荐集成边界

受控AArch64 Linux + 独占DMA/MMIO资源驱动，由OS管理进程、MMU/Cache和buffer生命周期。复用现有[计时/所有权接口](../tools/kv260_v12_linux_perf/README.md)与native prepare/verify helper；实际backend未实现。时钟候选为CLOCK_MONOTONIC_RAW/ktime_get_raw_ns，必须记录实际arch timer频率、clocksource与时间域依据，不能把纳秒单位当硬件1 GHz频率。

优先保留已验证诊断bit，但完整boot/script/rootfs/FPGA manager/clock/reset策略须先审核。官方system-boot候选不是完整rootfs或现场固件证明；候选脚本存在system.bit时可能加载PL，不应盲用。详见[Linux backend审阅](kv260_v12_linux_backend_review.md)。

## 小buffer与完整正确性

1.4 GiB不是算法必需；旧120份完整三输出archive主要为把校验移到窗外。现有三槽参考payload70.766 MiB，对齐/Guard/日志前缀预算75.366 MiB；其中DMA payload约49.7 MiB、普通CPU Golden约21 MiB。实际OS、allocator、页对齐和日志另计，75.4 MiB不是CMA设置或已批准地址图。

固定 `slot=global_frame_id%3`、A/B交替，只有全部三输出完成并全量校验后才能复用。每个输出word先poison；六Golden中实核0xA5A5不存在，不能仅用少量sentinel证明整帧更新。每帧poison11,028,240B、copy阶段输入5,533,200B、比较5,514,120标量与384B输出Guard。共享模型/输入/workspace/其它Guard由真实backend另审。

现有接口默认两段各6预热+120有效帧，由双方后续审核实际产品路径后确定，不构成本次执行申请。连续producer窗口包含真实输入准备、poison、软件控制、等待与校验竞争，validated窗口另包含末尾校验drain；不拼接service窗口、不事后扣除校验时间来声称持续FPS。性能边界为Q14内存→增强DDR，不包括相机/量化/下采样/显示。

若低于30先区分测试checker/poison与生产路径瓶颈，不能直接判硬件失败。现有审阅还保留约0.7 GiB的60帧archive候选用于必要时窗外全量校验，但尚无实现/授权，不自动切换或扩容。没有内部PL计数器不能拆纯算术与DDR stall。

## lzm需要确认的精确材料

- 完整可复现Linux启动镜像/rootfs、Image或image.fit、DTB/DTS/overlay、boot.scr/extlinux/bootargs、启动介质及启动记录。
- 匹配BOOT.BIN/分区镜像与SHA、BIF/load/entry/CPU/EL、U-Boot ELF/map/config/commit/patch、FSBL/PMUFW/BL31构建记录和固件内存/其它核/DMA职责。不需要私钥。
- 准确kernel release/config/vmlinux/System.map/Module.symvers/build headers、toolchain、已有driver/UAPI/binding源与构建结果。候选headers不是实际系统身份。
- PL加载/clock/reset/PMU策略、reserved-memory/CMA/dma-ranges/SMMU、全部11路AXI master跨4HP的DMA地址域、CSR唯一所有者证据。
- 当前diagnostic bit/A-B/Golden身份及最新调用合同；新性能结果后续用完整原始日志/时钟依据与独立审核归档。

硬件端提供设计、身份、协议与支持；lzm牵头软件平台与驱动；双方共同真实验收30 FPS。任何后续板端启动/加载/Cache/DMA/DDR/CSR/PL操作须冻结精确范围另行批准，首错停止，无自动retry/reset/reprogram。
