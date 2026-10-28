# 低照度三模块 + Compact D 联合资源检查

2026-10-28，Vivado 2025.2，器件 `xck26-sfvc784-2LV-c`。实际综合已完成；结论来自 `open_run synth_1` 读入全部 OOC checkpoint 后的完整联合网表。

**本报告仅包含 CNN、Bilinear、Curve、Compact D 四核及 PS/AXI/DDR/跨时钟互连；编码适配和三路融合尚未计入。以下余量不是最终全系统余量，也不是可上板或时序收敛证明。**

## 联合实测资源

| 资源 | 已用 | 器件容量 | 占比 | 剩余 |
|---|---:|---:|---:|---:|
| LUT | 72,262 | 117,120 | 61.70% | 44,858 |
| DSP48E2 | 904 | 1,248 | 72.44% | 344 |
| BRAM Tile（36 Kb） | 72 | 144 | 50.00% | 72 |
| URAM288 | 58 | 64 | 90.63% | 6 |
| FF | 83,644 | 234,240 | 35.71% | 150,596 |

BRAM 使用 `RAMB36 + RAMB18/2` 的 Tile 口径，不与 HLS 的 BRAM_18K 数直接混用。综合 LUT 数仍会在实现阶段变化。

URAM 是最紧的资源：D 使用 40 个、CNN 使用 18 个，只剩 6 个。后续适配、融合和系统缓冲不能把上述余量当成已完成设计的保证。DSP 已用 72.44%；共享 DDR 的并行带宽、仲裁和最终布线拥塞仍需后续系统集成/实现验证。

## 四核保留证据

`get_cells -hierarchical` 在联合网表内分别找到唯一核层级，且下表为后综合每核独立资源报告；四核均有非零 LUT。未解析 blackbox 数为 0，随后成功写出完整联合 `joint_synth.dcp` 和整行 `JOINT_FOUR_CORE_SYNTHESIS_PASS`。

| 联合实例 | LUT | DSP | BRAM Tile | URAM |
|---|---:|---:|---:|---:|
| `system_i/zero_dce_cnn_top_0` | 20,035 | 89 | 62.5 | 18 |
| `system_i/bilinear_fixed16_buffered_0` | 4,173 | 33 | 1.5 | 0 |
| `system_i/curve_image_fixed16_0` | 3,207 | 24 | 1 | 0 |
| `system_i/compact_d_top_0` | 29,279 | 758 | 7 | 40 |

四核 LUT 合计 56,694，其余 15,568 为 PS 包装、AXI 控制/DDR 互连、跨时钟和复位等逻辑。本报告未使用顶层 run 默认的 OOC 占位资源报告，也未把两个独立镜像的资源简单相加。

## 冻结来源和隔离工程

- 低照度从正式 `phase4g/integration_01/project/v12_wc.xpr` 的保存 BD 复制重建，保留 PS/DDR 配置和原三核。CNN 使用 `phase4g/ip_primary_05` writecredit 包，revision `2114810448`；Bilinear/Curve 使用该工程的 `stable_ip_repo` 副本。
- D 使用 `origin/weather_fpga_integration` 提交 `8c202508d267151c4ae034975b17947818be7865` 内的正式 `compact_d_fpga/board/k26_compact_d_20261025/compact_d_ip.zip`，revision `2114844623`。ZIP SHA-256 为 `7d276942544f3785bde9267484da6d08bbae819cd46b8bb8e7214ea8a5603bc4`。没有使用旧 `direct`/`row_oc8` 原型。
- 四份 IP 均复制到独立 `E:/HLS/joint_lowlight_compact_d_20261028/ip/` 后使用；禁用 IP cache，独立生成输出产品并运行真实综合。原工程、原 IP、队友分支不修改。
- 低照度使用 PS PL0 名义 100 MHz；D 使用新增 PS PL1 名义 200 MHz。联合 clock report 的周期为 10 ns / 5 ns；PS 配置实际值为 99.999001 / 199.998001 MHz。
- D 使用独立 `rst_ps_d`，同源低有效 PS reset 经各域同步释放。控制互连增加第 4 个输出；CNN 数据互连和 Curve DDR 互连各增加第 4 个输入及 200 MHz 时钟，交由 SmartConnect 做跨域。
- D 控制地址沿用 `0xA0050000/64K`；输入与 CNN 共享 HP0，输出与 Curve 共享 HP3。原低照度地址和 HP1/HP2 通路保留，D DDR 只映射低 2 GiB。两模型完成后启动融合的调度属于后续任务 5。
- 联合脚本沿用 D 构建中的 `logicopt.enableDSPCascadeFixing false` 设置；本轮未进行实现优化、布局或布线。

## 已执行与未执行

已执行：冻结输入 SHA 校验、独立复制、四核 BD 校验、全部 OOC 和顶层综合、完整网表链接、联合/层级/每核资源报告、时钟/综合时序/DRC 报告、四核保留和零 blackbox 门槛、联合 checkpoint、输入原件及副本 SHA 重核。

综合后 setup WNS `+0.672 ns`、TNS `0`；hold WHS `-0.093 ns`、THS `-3506.644 ns`，时序报告明确为 **constraints not met**。另外存在 8 个 `no_clock` 检查项；DRC 有 1,008 个 DSP 流水线 Warning（436/192/380），无 Error/Critical Warning。后续集成需定位未时钟项并在布局布线后完成 hold、时序、CDC/bus-skew 检查；不能把本轮 setup 数字作为实现时序签核。

未执行：含适配/融合的最终系统综合、联合功能仿真、布局布线、最终时序收敛、bitstream/XSA 交付、上板数值和耗时测量。

## 证据与复现

工程和完整 checkpoint 位于 `E:/HLS/joint_lowlight_compact_d_20261028/`。仓库内保留约 3 MB 文本证据；[资源汇总与 SHA-256](../reports/resource_summary.json) 含原始报告、完整输入清单和 checkpoint 哈希。[联合资源](../reports/resource_joint_utilization.rpt)、[联合层级](../reports/resource_joint_utilization_hierarchical.rpt)、[时序](../reports/resource_joint_synthesis_timing.rpt)、[时钟](../reports/resource_joint_clocks.rpt)、[DRC](../reports/resource_joint_synthesis_drc.rpt) 和每核报告可直接审查。

在仓库根目录运行下列四步；`prepare` 要求目标目录尚不存在。复现依赖上述正式低照度本地包和仓库 D 提交，所有新输出写入指定的隔离目录。

```powershell
$resourceOut = 'E:\HLS\joint_lowlight_compact_d_rebuild'
.\fpga\joint_lowlight_compact_d\scripts\resource_run.ps1 -BuildDirectory $resourceOut -Stage prepare
.\fpga\joint_lowlight_compact_d\scripts\resource_run.ps1 -BuildDirectory $resourceOut -Stage create
.\fpga\joint_lowlight_compact_d\scripts\resource_run.ps1 -BuildDirectory $resourceOut -Stage synth
.\fpga\joint_lowlight_compact_d\scripts\resource_run.ps1 -BuildDirectory $resourceOut -Stage collect
```

`collect` 只接受真正执行到终点的整行成功标记，并验证四个后综合核均有非零 LUT、冻结副本与原低照度文件/原 D ZIP 均未改变，随后收集资源和文件哈希。本轮未执行任何 Git 写操作。
