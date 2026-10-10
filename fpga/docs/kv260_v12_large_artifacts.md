# KV260 V1.2 独立大文件交接

交接整理：2026-10-10；真实板测日期：2026-10-09。本次Git共享源码、接口、报告和本清单，不上传大型二进制或第三方Linux软件包。

## 当前准备包

本地规范目录名为 `large_artifacts_handoff/`，包含176个payload文件，共91,974,788字节（约87.7 MiB）。Git中的[transfer manifest](kv260_v12_transfer_manifest.json)与本地inventory.json逐字节一致，SHA256为 `aecd6b2f1bae5529089a17569cb36b5dea16099231e263a281c7b1774d20bd2f`。接收者须获得完整payload目录，以manifest逐项核大小/SHA；只取得Git清单不代表已收到文件。

| 文件组 | 内容与用途 |
| --- | --- |
| artifacts/ | 已真实验证的diagnostic_v12_independent_clock.bit及必要诊断源追溯 |
| formal/ | 独立正式bit/XSA、XSA提取HWH和三个寄存器头、正式BD；不自动继承诊断板测PASS |
| data/A 与 data/B | 各九份输入/模型参数/三个Golden，little-endian INT16 Q14 |
| evidence/ | 三份单帧、六份S1真实输出及120份S1保存Guard读回，脱敏摘要与独立身份 |
| linux/ | 既有AArch64 clock_probe/libkv_hotpath.so及对应小源码；不是DMA/MMIO驱动 |

以上为payload下的组名，精确文件名以manifest为准。九份真实输出已重新完整对照Golden，120份Guard保存读回已核原始SHA；这是Host离线验证，没有新读板或新FPS结果。Linux二进制只完成Host交叉编译/ELF审核，未在目标系统运行；当前源码/说明以本次Git版本为准。

## 保留但不随规范包分发

原始诊断routed DCP含生成环境元数据，Windows Host DLL只用于Host测试，均保留本地，可由Master在确定渠道后另审。五份固定本机路径Tcl配置也不随包发送；未改任何已验证原件来隐藏路径。排除项的名字/大小/SHA及原因保存在manifest，不是缺失或覆盖。

可选三组冻结HLS/IP导出408件、13,532,882字节仅提供身份清单；需要重建时另行确认依赖、厂商许可与传输范围。完整工程/runs/cache、私有原始Host/设备日志及官方Linux deb/kernel/DTB/rootfs不在包中，Git保留正式源码和recipe入口。正式工程和recipe不等于本次已经完整重建。

24个文本文件、29个非数值外层文件及XSA内49个成员经过指定本机路径/用户/主机/网络身份扫描，没有命中；这是有范围的核查，不承诺二进制完全没有公共工具/运行时路径。

## 缺项、传输与现场状态

诊断配套XSA仍缺；现场匹配bootchain/完整rootfs、实际Linux DMA/MMIO/UAPI驱动和Kbuild/装载、11路master/4HP地址域及DMA/Cache所有权、真实30 FPS和相机显示尚未完成。候选kernel/headers不能代替这些证据。

大件目前本地已准备，尚未外发；交付渠道和实体板卡安排由Master确定。Git Push不等于大件已经传输或授权执行其中程序。实体交接前应安排核对实际idle/存储/供电与连接状态；本次未连接板卡，不能依据最后Cache OFF记录保证当前可安全断电。任何新板端操作须精确范围另批。

入口：[START_HERE](kv260_v12_START_HERE.md)、[软件接口](kv260_v12_software_handoff.md)、[交板清单](kv260_v12_delivery_checklist.md)。
