# V1.2 Phase 4F — 8-frame short multi-frame system pipeline validation

日期：2026-10-03（Asia/Shanghai）。CURRENT STATUS：**SHORT_MULTI_FRAME_30FPS_PASS / WAIT_MASTER**。

仅完成固定 **FRAMES=8、READ_OUTSTANDING=WRITE_OUTSTANDING=2、DDR_DELAY=16、SERVICE_PERIOD=1、POLL_PERIOD=128、100 MHz** 的完整 CNN → DDR → Bilinear → DDR → Curve。保留现有双槽调度；每帧全量数值检查没有省略。

权威现场：[Phase 4E checkpoint 备份](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/checkpoint_before.md)；[Phase 4E write-credit report](E:/github/-/fpga/reports/v1_2_phase4e_write_retirement_optimization.md)。当前 write-credit 仍为 **RTL scheduling overlay，未形成新 HLS export / IP release**。

证据：[完整日志](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/system.log)；[独立分析](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/analysis.json)；[配置与source manifest](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/run_manifest.json)；[自然退出记录](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/exit_status.json)；[原BFM不变审计](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/harness_audit_after.json)。

## 8 帧数值与真实 RTL start/done

每帧 CNN A_low **19,080**、Bilinear A_full **2,747,520**、Curve enhanced **2,747,520** 个 raw INT16 全量比较；8 帧共 **44,112,960** 项。三阶段各 8 次检查：**raw mismatch=0；guard=0；hazard=0**。

下表 start/done 来自核内部 ap_start/ap_done，不含软件轮询误差；帧号从 0 开始。

| Frame | CNN start / done / cycles | Bilinear start / done / cycles | Curve start / done / cycles | Raw mismatch CNN / Bilinear / Curve |
| --- | --- | --- | --- | --- |
| 0 | 396 / 3,302,035 / 3,301,639 | 3,302,377 / 6,403,089 / 3,100,712 | 6,403,308 / 9,322,703 / 2,919,395 | 0 / 0 / 0 |
| 1 | 3,302,286 / 6,604,677 / 3,302,391 | 6,605,007 / 9,706,123 / 3,101,116 | 9,706,387 / 12,625,782 / 2,919,395 | 0 / 0 / 0 |
| 2 | 6,604,916 / 9,911,815 / 3,306,899 | 9,912,192 / 13,013,288 / 3,101,096 | 13,013,552 / 15,932,947 / 2,919,395 | 0 / 0 / 0 |
| 3 | 9,912,101 / 13,219,184 / 3,307,083 | 13,219,509 / 16,320,617 / 3,101,108 | 16,320,869 / 19,240,264 / 2,919,395 | 0 / 0 / 0 |
| 4 | 13,219,418 / 16,526,318 / 3,306,900 | 16,526,674 / 19,627,770 / 3,101,096 | 19,628,034 / 22,547,429 / 2,919,395 | 0 / 0 / 0 |
| 5 | 16,526,583 / 19,833,666 / 3,307,083 | 19,833,991 / 22,935,099 / 3,101,108 | 22,935,351 / 25,854,746 / 2,919,395 | 0 / 0 / 0 |
| 6 | 19,833,900 / 23,140,800 / 3,306,900 | 23,141,156 / 26,242,252 / 3,101,096 | 26,242,516 / 29,161,911 / 2,919,395 | 0 / 0 / 0 |
| 7 | 23,141,065 / 26,448,148 / 3,307,083 | 26,448,278 / 29,549,020 / 3,100,742 | 29,549,218 / 32,468,613 / 2,919,395 | 0 / 0 / 0 |

## 输出 frame interval 与 30 FPS gate

唯一 FPS 指标为 **Curve_done(N+1) − Curve_done(N)**。100 MHz 的精确 30 FPS budget=3,333,333.333… cycles；按整数 gate **max steady-state interval ≤3,333,333**。稳态预先固定为最后 4 个间隔（3→4、4→5、5→6、6→7），全部 7 个实测间隔同时保留。

这是有限 8 帧的后段输出 cadence 统计，包含系统排空尾部；三模块同时运行的实际范围由下面 start/done 时间线界定。

| Output frames | Curve done interval / cycles | ≤3,333,333 |
| --- | --- | --- |
| 0 → 1 | 3,303,079 | PASS |
| 1 → 2 | 3,307,165 | PASS |
| 2 → 3 | 3,307,317 | PASS |
| 3 → 4 | 3,307,165 | PASS |
| 4 → 5 | 3,307,317 | PASS |
| 5 → 6 | 3,307,165 | PASS |
| 6 → 7 | 3,306,702 | PASS |

| Scope | Min | Mean | Max |
| --- | --- | --- | --- |
| 全部 7 intervals | 3,303,079 | 3,306,558.571 | 3,307,317 |
| 后 4 steady intervals | 3,306,702 | 3,307,087.250 | 3,307,317 |

**SHORT_MULTI_FRAME_30FPS_PASS**。稳态 mean 对应 30.238 FPS；max 对应 30.236 FPS。

First-frame latency=9,322,307 cycles，仅报告延迟，不用于判断 FPS。

## 连续 stage start interval 与并发 stage latency

| Frames | CNN start interval | Bilinear start interval | Curve start interval |
| --- | --- | --- | --- |
| 0 → 1 | 3,301,890 | 3,302,630 | 3,303,079 |
| 1 → 2 | 3,302,630 | 3,307,185 | 3,307,165 |
| 2 → 3 | 3,307,185 | 3,307,317 | 3,307,317 |
| 3 → 4 | 3,307,317 | 3,307,165 | 3,307,165 |
| 4 → 5 | 3,307,165 | 3,307,317 | 3,307,317 |
| 5 → 6 | 3,307,317 | 3,307,165 | 3,307,165 |
| 6 → 7 | 3,307,165 | 3,307,122 | 3,306,702 |

| Stage | Isolated reference | 8-frame latency min / mean / max | Late latency min / mean / max | Late start interval min / mean / max |
| --- | --- | --- | --- | --- |
| CNN | 3,301,639 | 3,301,639 / 3,305,747.250 / 3,307,083 | 3,306,900 / 3,306,991.500 / 3,307,083 | 3,307,165 / 3,307,241 / 3,307,317 |
| Bilinear | 3,100,554 | 3,100,712 / 3,101,009.250 / 3,101,116 | 3,100,742 / 3,101,010.500 / 3,101,108 | 3,307,122 / 3,307,192.250 / 3,307,317 |
| Curve | 2,919,395 | 2,919,395 / 2,919,395 / 2,919,395 | 2,919,395 / 2,919,395 / 2,919,395 | 3,306,702 / 3,307,087.250 / 3,307,317 |

| Stage | Late previous DONE→START idle min / mean / max | Late ready→START control/poll lag min / mean / max |
| --- | --- | --- |
| CNN | 234 / 249.500 / 265 | 234 / 249.500 / 265 |
| Bilinear | 206,026 / 206,090.250 / 206,221 | 130 / 291.750 / 356 |
| Curve | 387,307 / 387,692.250 / 387,922 | 198 / 244.500 / 264 |

Ready boundary 取自身前帧 RTL DONE、当前 producer RTL DONE、同槽旧 consumer 的实际 RELEASE 中最晚者；ready→START lag 保留软件确认/CSR/poll 开销。逐次边界及输出 cadence 对照详见 analysis.json。精确恒等式：stage start interval=前帧 stage latency+当前 idle gap；Curve done interval=当前 Curve latency+当前 Curve idle gap。

## 实际跨帧 overlap 证据

对真实 ap_start/ap_done 区间取交集：max(三个 start) < min(三个 done) 才构成 overlap；没有由 scheduler 源码推断重叠。

| CNN frame | Bilinear frame | Curve frame | Overlap start | Overlap done | Overlap cycles |
| --- | --- | --- | --- | --- | --- |
| 2 | 1 | 0 | 6,605,007 | 9,322,703 | 2,717,696 |
| 3 | 2 | 1 | 9,912,192 | 12,625,782 | 2,713,590 |
| 4 | 3 | 2 | 13,219,509 | 15,932,947 | 2,713,438 |
| 5 | 4 | 3 | 16,526,674 | 19,240,264 | 2,713,590 |
| 6 | 5 | 4 | 19,833,991 | 22,547,429 | 2,713,438 |
| 7 | 6 | 5 | 23,141,156 | 25,854,746 | 2,713,590 |

Peak concurrent stages=3，overlap gate=PASS。完整 stage sweep：[stage_overlap_timeline.csv](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/results/stage_overlap_timeline.csv)。

| Timeline start | Timeline done | Cycles | 实际并行 stage/frame |
| --- | --- | --- | --- |
| 6,605,007 | 9,322,703 | 2,717,696 | CNN(2) + Bilinear(1) + Curve(0) |
| 9,912,192 | 12,625,782 | 2,713,590 | CNN(3) + Bilinear(2) + Curve(1) |
| 13,219,509 | 15,932,947 | 2,713,438 | CNN(4) + Bilinear(3) + Curve(2) |
| 16,526,674 | 19,240,264 | 2,713,590 | CNN(5) + Bilinear(4) + Curve(3) |
| 19,833,991 | 22,547,429 | 2,713,438 | CNN(6) + Bilinear(5) + Curve(4) |
| 23,141,156 | 25,854,746 | 2,713,590 | CNN(7) + Bilinear(6) + Curve(5) |

## Buffer ownership、RAW / WAR / WAW 与等待

**RAW/WAR/WAW PASS；guard=0；hazard=0**。80 次实际 acquire/release、40 个 frame/buffer 生命周期、10 个 slot occupancy 积分全部交叉核对；每次 slot 复用都晚于前一个 consumer 完成及实际 release。

| Buffer | Producer / consumer 与释放规则 |
| --- | --- |
| A_low[2] | CNN → Bilinear；Bilinear 完成并检查后 release |
| A_full[2] | Bilinear → Curve；Curve 完成并 host 检查后 release |
| enhanced[2] | Curve → host raw check；全量比较结束后 release |
| cnn_input[2] | 预载只读；CNN 完成检查后 release |
| model_input[2] | 预载只读；Curve 完成检查后 release |
| workspace / weights / bias / frac / LUT | workspace 只由单一串行 CNN 实例独占；参数 HP1 只读，AW/W=0；原 access checker 禁止写入 input/model/参数区域 |

| Stage | Dependency wait | Buffer wait | Both | Union blocked | Ready / CSR / poll |
| --- | --- | --- | --- | --- | --- |
| CNN | 0 | 0 | 0 | 0 | 1,633 |
| Bilinear | 4,737,778 | 0 | 0 | 4,737,778 | 1,989 |
| Curve | 9,111,979 | 0 | 0 | 9,111,979 | 728 |

等待以未 running 且有 next frame 的每周期实际状态计数；buffer wait 仅计算**其他帧**仍持有目标 slot，已排除自身 CSR reservation。Dependency 和 buffer 可重叠，union=dependency+buffer−both；这些状态计数不直接相加冒充吞吐损失。自身核运行、done 后轮询确认与控制启动时间可从实际 stage gap 另看。逐帧计数：[wait_stats.csv](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/results/wait_stats.csv)。

| Buffer | Slot | Occupied cycles | Peak occupied slots |
| --- | --- | --- | --- |
| A_low | 0 | 25,629,144 | 2 |
| A_low | 1 | 25,630,154 | 2 |
| A_full | 0 | 24,083,456 | 2 |
| A_full | 1 | 24,083,151 | 2 |
| enhanced | 0 | 11,678,497 | 1 |
| enhanced | 1 | 11,678,163 | 1 |
| cnn_input | 0 | 13,223,405 | 1 |
| cnn_input | 1 | 13,224,581 | 1 |
| model_input | 0 | 11,678,497 | 1 |
| model_input | 1 | 11,678,163 | 1 |

Owners 在 negedge 采样，标签与原事件可差 1 cycle；占用积分与实际 transition 完全一致。生命周期全表：[analysis.json](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_02/analysis.json)。

**56/56 CNN writer block drains PASS**：每帧 7 个 block credit_ws=credit_out=0、HP0 write queue/data/B 清空；**32/32 stage/HP release drains PASS**：CNN HP0/1、Bilinear HP2、Curve HP3 的 rc/wc/wp/RVALID/BVALID 全空后才释放。最终所有 HP responses 与全部 owners 清空。

## DDR 并发统计

DDR model v2 不变，O=2/2；下表为完整 8 帧全程实际累积统计。R_STALL 是有读请求且 RREADY 等待 RVALID 的周期；B_WAIT 是有写请求且 BREADY 等待 BVALID 的周期，均不是纯 contention，也不能与其他 stall 简单相加。

| HP | AR | AW | R beats | W beats | Useful write bytes | Read / write queue max | Read / write occupancy sum |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 146,760 | 98,344 | 1,955,520 | 1,310,400 | 19,843,200 | 2 / 2 | 5,613,607 / 26,637,962 |
| 1 | 664 | 0 | 10,368 | 0 | 0 | 2 / 0 | 35,622 / 0 |
| 2 | 10,688 | 696,608 | 27,640 | 2,747,520 | 43,960,320 | 2 / 2 | 236,853 / 24,318,276 |
| 3 | 1,373,760 | 686,880 | 5,495,040 | 2,747,520 | 43,960,320 | 2 / 2 | 35,999,802 / 24,184,331 |

| HP | AR stall | AW stall | R wait | R backpressure | W stall | B wait |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 334 | 3,467,028 | 0 | 241,832 | 26,202,488 |
| 1 | 13,009 | 0 | 9,284 | 1,818 | 0 | 0 |
| 2 | 86,135 | 1,095 | 99,368 | 0 | 330,722 | 22,606,919 |
| 3 | 203,224 | 0 | 15,063,567 | 0 | 416,903 | 22,667,048 |

| HP | AR→first R mean / max | AR→last R mean | AW→B mean / max |
| --- | --- | --- | --- |
| 0 | 18.702 / 62 | 38.250 | 270.865 / 85,899 |
| 1 | 27.880 / 70 | 53.648 | — / 0 |
| 2 | 19.436 / 38 | 22.161 | 34.910 / 39 |
| 3 | 21.454 / 36 | 26.205 | 35.209 / 40 |

Shared served=14,294,008 beats，contested=4,208,552 cycles，R/W concurrent=3,322,440 cycles。所有 HP read/write queue max≤2；AR=first-R samples，AW=B samples；AW→B latency sum=write occupancy sum；8 倍单帧 R/W/payload bytes conservation PASS。

### 三模块同时活动期间

真实 triple-active 共 16,285,342 cycles，6 个时间段；shared served=9,711,335，contested=3,502,705，R/W concurrent=2,699,459。

| HP | AR / AW | R / W beats | Read / write queue mean / peak | AR / AW / R / R back / W / B waits | Completed first-R mean / max | Completed B mean / max |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 87,621 / 72,630 | 1,167,628 / 967,680 | 0.225 / 1.009; peak 2 / 2 | 0 / 267 / 2,377,562 / 0 / 233,888 / 16,104,550 | 18.892 / 62 | 222.471 / 85,899 |
| 1 | 477 / 0 | 7,564 / 0 | 0.002 / 0.000; peak 2 / 0 | 9,832 / 0 / 7,976 / 709 / 0 / 0 | 28.545 / 68 | — / 0 |
| 2 | 7,486 / 457,127 | 18,593 / 1,802,995 | 0.010 / 0.981; peak 2 / 2 | 62,118 / 694 / 71,795 / 0 / 300,882 / 14,836,081 | 19.607 / 38 | 34.961 / 39 |
| 3 | 957,730 / 478,976 | 3,830,966 / 1,915,911 | 1.572 / 1.038; peak 2 / 2 | 193,257 / 0 / 10,785,845 / 0 / 391,657 / 15,806,288 | 21.733 / 36 | 35.279 / 40 |

完整 mask0..7、R backpressure/B wait 与所有 response sums 保留在 analysis.json。Snapshot 在 stage mask 变化的 negedge 记录，时间标签比真实 RTL event 晚 1 cycle，段长与实际 sweep 一致。Latency mean 来自该快照窗口内完成的响应，request 可能更早发出；队列积分代表窗口内真实占用。单周期 active-mask response maxima 独立保留 PHASE4F_TRIPLE，边界 response 的样本归属相差最多 1 cycle，不把这些重叠计数当成可直接相加的因果节省。

## 瓶颈与归因

结论为 **SHORT_MULTI_FRAME_30FPS_PASS**。全部 7 个 Curve done interval 的 min / mean / max 为 **3,303,079 / 3,306,558.571429 / 3,307,317 cycles**；预先固定的后 4 个间隔为 **3,306,702 / 3,307,087.25 / 3,307,317 cycles**。最差间隔低于整数 gate 3,333,333 **26,016 cycles**，即 100 MHz 下 **0.26016 ms** 余量；最差约 **30.235989 FPS**。不是使用首帧 9,322,307 cycles 的 latency 判 FPS。

**吞吐节拍由 CNN 的完成/再次启动链决定，随后由 Bilinear 和 Curve 传递。** 8 帧真实 stage latency 的最大值分别为 CNN **3,307,083**、Bilinear **3,101,116**、Curve **2,919,395 cycles**，都未超预算。CNN 后 4 帧 latency 为 3,306,900–3,307,083、mean=3,306,991.5；其 start interval 为 3,307,165–3,307,317、mean=3,307,241。逐次 launch readiness 证明 CNN 的最晚 prerequisite 始终是自身前帧 DONE，Bilinear 是当前 CNN DONE，Curve 是当前 Bilinear DONE；同槽旧 consumer 的 release 均更早。不能仅因某个 downstream start interval 与输出 interval 相同，就把那个 downstream 核判成瓶颈。

后 4 帧 CNN 自身 DONE→下一 START 的实际控制/轮询间隙为 **234–265 cycles，mean=249.5**，这是本批测得的额外节拍开销。Bilinear 自身前帧 DONE→当前 START idle 为 206,026–206,221 cycles，等待 producer 完成后 ready→START 的控制/轮询开销为 130–356 cycles；Curve 对应 idle 为 387,307–387,922 cycles，ready→START 为 198–264 cycles。Bilinear 和 Curve 尚有运行时间余量，其主要 idle 来自正常 RAW producer 依赖。逐项 stage/start/output 恒等式已核对，等待积分没有被当成可相加的因果延迟。

**真实 shared DDR 争用存在，但未把任何 stage 或输出 cadence 拖过预算。** 6 组 CNN(N+2)、Bilinear(N+1)、Curve(N) 的真实 RTL 交集全部非零，合计 **16,285,342 cycles**；这段共享服务 **9,711,335 beats**，contested **3,502,705 cycles**，全程 contested **4,208,552 cycles**。CNN 相对 Phase 4E isolated reference 3,301,639 的最大实测增加为 **5,444 cycles**；Bilinear 相对 3,100,554 的最大增加为 **562 cycles**；Curve 8 帧均为原 **2,919,395**。这是相同冻结模型下的实际跨帧观察，不把 AR/R/W/B stall 或 response latency 积分简单相加，也没有用额外 counterfactual 仿真宣称每一项差值的单独因果贡献。所有 HP read/write queue peak≤2，payload beats/bytes 均等于 8 倍完整单帧，全部 response 排空。

**Buffer ownership 与调度没有额外 consumer-slot 阻塞。** CNN / Bilinear / Curve 的 buffer wait 全为 **0**；dependency wait 分别为 **0 / 4,737,778 / 9,111,979 cycles**，包含流水填充和下游等待上游的正常 RAW 依赖。已排除各 stage 自己 CSR 配置期间的 buffer reservation。A_low 和 A_full peak occupancy=2；enhanced、cnn_input、model_input peak=1。80 次 acquire/release、40 个生命周期、56 个 CNN writer drain、32 个 stage/HP drain 全部通过；不存在提前复用、RAW/WAR/WAW violation 或尚未退休的事务跨 release。

CNN **HP0 AW→B 最大值为 85,899 cycles**。原 DDR 计时从 accepted AW 开始，到 accepted B 结束，包含排队、producer/data 供给等待、burst 数据传输和 B 退休全过程；它不是纯 DDR contention，也不是 WLAST→B 的退休等待。长 AW→B 与 writer 仍等待 producer 提供实际 W 数据可以同时存在，不能拿这个最大值直接当成可消除的输出周期损失。本批保持其真实值，未修改模型或隐去长响应样本。

**有限 8 帧的后 4 窗口含排空尾部。** 最后 6→7 输出间隔为 3,306,702，比中央交替的 3,307,165 / 3,307,317 略低；最终 Curve(7) 已在单 stage 排空阶段。预定窗口没有因此更改，全部 7 间隔与每个实际 active-mask 时间段都保留。窗口最大值 **3,307,317** 已出现在中央重叠段，因此本次最差值 gate 没有依靠更快的排空终点通过。本结论是当前模型和重复 night_01 输入的 short multi-frame gate，不扩大为 100-frame、真实板级 DDR 或真实采集/PS 传输保证。

本批没有触发用户定义的性能 FAIL 归因流程，也没有继续优化。**可实施 IP 固化仍是独立待办**：Phase 4E write-credit 是 RTL scheduling overlay，不是新 HLS export 或正式 IP release。完成当前 8 帧报告/checkpoint 后停止，等待 Master 决定下一批；不自动 implementation、route、bitstream/XSA、板测或 100-frame。

## 修改、验证与停止范围

前后 protection audit：原 5,235 文件、原 363 个 system source、3 个 Phase 4E overlay、16 份 PL/DDR/hex/ROM/options copy hash PASS；恢复原 TB 前缀后逐字一致，CNN 数学、DW/PW lanes、Bilinear、Curve、DDR v2、buffer layout、fixed-point 与原 scheduler 未改。仅重新进行 **XSIM simulation elaboration**，没有 HLS 重新综合或 export。

首次 phase4f_system_01 在 frame0 完成前中止：被动 buffer wait 计数误把自身 CSR reservation 算成 consumer stall；只修复观测归因，新建独立 system_02 完整运行，01 不用于数值或性能 gate。相关记录：[attempt_status.json](E:/HLS/kv260_three_module_v1_2_phase4/phase4f_system_01/attempt_status.json)。

新增/更新文件及原因：

| File | 原因 / 关键差异 |
| --- | --- |
| fpga/perf/v1_2_phase4f/prepare_system.py | 复用原完整 BFM，仅替换同三颗 Phase4E overlay；新增 passive owner/wait/DDR mask/drain 观测和严格 FRAMES=8 scope |
| fpga/perf/v1_2_phase4f/run_system.py | source/config/kernel hash gate 后唯一完整 8 帧自然运行；无后续自动流程 |
| fpga/perf/v1_2_phase4f/analyze_system.py | 独立核对 24 次全量检查、实际 overlap、所有权、7/4 intervals、DDR与payload conservation |
| fpga/perf/v1_2_phase4f/audit_harness.py | 前后只读保护审计，证明原 BFM/scheduler/DUT/model未改 |
| fpga/perf/v1_2_phase4f/finalize_reports.py | 仅完整gate后写权威report/checkpoint |
| fpga/reports/v1_2_phase4f_short_multiframe.md | 本批完整证据、性能结论与瓶颈 |
| fpga/reports/v1_2_phase4_checkpoint.md | 更新当前结果与交接；旧checkpoint外部保留 |

已执行：8 帧完整三模块 RTL 自然完成、24 次逐字数值/guard/hazard/IRQ 检查、实际三 stage overlap、80 owner transitions、wait/slot积分、56 writer及32 stage/HP drain、原DDR全run/mask并发统计、payload conservation、前后hash保护与独立一致性分析。

未执行：100-frame、HLS synthesis/export、Vivado implementation/route、bitstream/XSA、板测、Git add/commit/push、PR、切换/创建/删除分支。外部 E:/HLS 数据、snapshot、仿真日志与备份不上传。

输入为同一真实 night_01 预载到两个 input/model slot 后重复 8 帧；host数值检查不消耗模拟 cycles。本结论只覆盖该 DDR model 与三模块流水线，未计真实采集、PS input上传/输出搬运和板级DDR时延。

Branch=`codex/curve-fp32-baseline`，HEAD=`660010bfea9f43c99623ee2ba99662292783a02e`；tracked diff=empty；staged diff=empty。既有 untracked 保留，本批新增脚本/报告及checkpoint未跟踪；没有 Git 写操作。

建议 Commit Message：`test(fpga): validate eight-frame write-credit system pipeline`。

## NEXT STEP — WAIT MASTER

本批 8 帧分析与 checkpoint 完成后立即停止，等待 Master 审核。短多帧性能 gate 已通过；下一批须单独解决可实施 IP 固化问题，将 RTL scheduling overlay 转化为可审核的实施交付。不自动进入 100-frame、HLS export、implementation 或 bitstream。
