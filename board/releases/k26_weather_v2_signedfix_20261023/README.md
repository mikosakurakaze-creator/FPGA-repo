# K26 天气核 DSP 符号边界修正版

状态：新布局布线、最终布线网表四帧数值回归、原生 XSA/bit 导出和 Bootgen BIN 转换均已完成。由 `manifest.json`、`SHA256SUMS` 和本地核验命令约束这套文件的身份。本目录是待真板复测的修正候选，不是已经完成板端验收的版本。

## 修改原因

2026-10-22 版本在同一组 8×8、task=0 真板测试中有 171/192 个标量不匹配。原布线后功能网表能逐字节复现全部错值。原因是 `opt_design` 将末级一个 DSP 原来的 `M + sign_extend(previous_P[21:0])` 改为 `M + previous_PCOUT[47:0]`，没有保留截断后的符号扩展语义。仅恢复该接收端就能在仿真中恢复 Golden。

本版在 Vivado 2025.2 进程内关闭 `logicopt.enableDSPCascadeFixing`，从原已链接综合检查点重新布局布线。没有修改网络、权重、整数规则或接口。这个工具选项和精确层次检查是当前版本的定向解决方案；更换工具或重综合后必须重新检查，不能直接照搬 PASS。

## 接口与运行范围

- 器件：KV260/K26，`xck26-sfvc784-2LV-c`，PL0 100 MHz。
- 天气控制基址：`0xA0030000`；input `0x18/0x1c`，output `0x24/0x28`，height `0x30`，width `0x38`，task `0x40`。
- 输入输出：RGB NCHW、小端有符号 INT16 Q14；task=0 去雨、task=1 去雾；H≤720、W≤1280。
- 输入经 HP0、输出经 HP3；HLS master 32-bit，PS 侧128-bit；两个独立、已正确分配的低2 GiB DDR缓冲区，无外部特征工作区。
- 先串行互斥运行。诊断中低照度其他 master 保持空闲，没有验证低照度和天气并发。

## 文件身份

目录包含相互匹配的 `weather_system.bit`、`weather_system.bit.bin`、`weather_system.xsa`、`weather_system.hwh`、PS 初始化文件、生成驱动、布线报告和四帧实际输出。

本次使用独立 DCP 实现流程，最终 XSA 由 Vivado `write_hw_platform -fixed -include_bit` 从新 routed DCP 原生生成，没有手工编辑或重封装归档。第一次调用被当前目录中的空格触发工具内部命令解析错误；改在无空格目录重试成功。`reports/native_xsa_first_attempt_status.txt` 只记录第一次失败，成功结果见 `reports/native_platform_console.txt` 和 `reports/native_platform_identity.json`。

新 XSA 含59个成员。HWH、PS初始化和所有驱动与原平台逐字节相同；Vivado更新了 `sysdef.xml`、`xsa.json`、`xsa.xml` 并增加 `.nts`。XSA内部bit名为 `weather_signedfix_native02.bit`，外部命名为 `weather_system.bit`，两者字节完全相同；内部引用保留工具原生名称。其配置payload也与另一次从相同DCP独立生成的bit一致。

| 文件 | SHA-256 |
|---|---|
| `weather_system.bit` | `2b2d54452ca3ab65b40e9caa60691039b0f747c9490ae5b396696be9dfb67c2e` |
| `weather_system.xsa` | `74a25b0142d08a85f0d671e796583cdf3775dc05257d98f3692072c007db0694` |
| `weather_system.bit.bin` | `3cc937d0b921c87ef3b2101309ae2fc3261c132dfd5f95c90539087a1fe86ebd` |

原故障版 `../k26_weather_v2_20261022/` 不覆盖。`reports/corrected_build_provenance.json` 记录原始输入、新 opt/routed 检查点、当前未提交源码及执行脚本快照；单独引用旧 HEAD 不能完整标识本轮修改。

## 实际完成的离线核验

- 重新place、phys_opt、route；100 MHz setup WNS +0.638 ns，hold WHS +0.010 ns，pulse width +3.500 ns；166,311/166,311个可布线net完成，0 routing errors。
- 最终新布线网表保留真实天气核、复位、控制/HP0/HP3 SmartConnect父层连线，连续task=0、0、1、0四帧均192/192等于各自Golden，周期2401、2376、2376、2376拍。task=1使用之前通过独立RTL验证的8×8向量，没有其真板capture。
- 严格检查实际DSP全部48根C输入的来源和OPMODE；旧错误检查点拒绝，新布线检查点通过。
- XSA CRC、内部/外部bit、HWH、PS初始化、驱动、BIN与bit payload、完整清单和数值证据均独立核验。
- 存在普通DRC Warning：DPIP-2 533、DPOP-3 211、DPOP-4 250、DPREG-7 18、RTSTAT-10 1；没有Error/Critical Warning。DPREG-7只补了稳定二值选择模式检查，不能描述为零告警或覆盖物理瞬态。

## 复测要求

加载本目录同一套文件，先重跑用户包内的原始8×8、task=0输入，冷态及暖态均应逐值匹配原 Golden。Golden 二进制 SHA-256：`bbb5e6f343e1a4b6f0b05c8f18fbce48655e30ed532194e1a4e32fcf250b8697`。

再做 task=1、切回 task=0、尺寸变化与连续帧。板端分配、缓存一致性、完整 PS/DDR 运行配置仍由真实平台确认；四项 AFI 位宽字段匹配不等于完整平台验收。无需根据本次错误盲改 HP0/HP3 配置。

本版没有新 ELF、BOOT.BIN、Linux 设备树或 ILA/LTX。功能网表仿真不含 SDF；没有修正版真板、真实 DDR 吞吐、720p 持续帧率及低照度并发验收结果。此前导出 RTL 的720p周期证据不能直接当作本版真板性能。

## 本地核验

在仓库根目录运行：

```powershell
python tools/board_artifacts.py verify --release board/releases/k26_weather_v2_signedfix_20261023
```

该命令核验清单、文件对应关系、离线时序和保存的数值证据，不会操作板卡，也不会提交或推送 Git。
