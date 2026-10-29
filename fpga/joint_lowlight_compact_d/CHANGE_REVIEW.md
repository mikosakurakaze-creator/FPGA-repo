# 本轮修改审核

日期：2026-10-29。目标：承接用户补交的前三项冻结交付，完成任务 4–6。任务 4 数值/RTL/IP 验证完成；六核 BD、地址校验、联合综合、布局布线与独立 routed 验收均已通过。联合 bit/XSA/HWH 和完整硬件包已生成并通过逐文件、XSA 配置/规范 bit、顶层 HWH、ZIP CRC 及哈希验收；未上板。

## 1. 文件、原因和关键差异

没有修改既有 tracked 文件。全部新增在 `fpga/joint_lowlight_compact_d/`，按职责列出：

| 文件 | 原因和关键差异 |
| --- | --- |
| `.gitattributes` | 保持源码/证据原始字节，避免换行转换破坏哈希 |
| `README.md`、`REMOTE_AUDIT.md`、本文件 | 记录真实进度、首次远端审阅历史、补交后的新基线和审核边界 |
| `docs/fusion_contract.md` | 冻结 Q14/Q15、一次 RNE/最后裁剪、寄存器/地址、错误、帧 ID 和恢复合同 |
| `rtl/joint_fusion.v` | UINT32 权重合法性检查，启动快照，signed64 累加，AXI 读写/响应、64-byte 对齐、LOW DDR 和输出重叠检查 |
| `tests/tb_joint_fusion.sv` | 独立 signed-floor Golden；全码域/全帧、非法调用零 DDR、等待/背压、响应错误、忙时重写与启动快照 |
| `runtime/controller.py`、`tests/test_controller.py` | 单 owner 单帧调度；prepare 后并行 CNN/D，CNN→Bilinear→Curve 与 D 均成功后才启动融合；失败/超时禁止复用 |
| `runtime/run_pynq.py`、`runtime/mmio_fence.c`、`docs/loading_order.md` | PYNQ MMIO/DMA/cache ownership、ARM 屏障、hash/HWH 校验和加载调用顺序；失败后保留仍可能被 AXI 引用的物理内存 |
| `scripts/run_checks.py`、`fusion_package.tcl`、`fusion_ooc.tcl`、`fusion_verify.tcl` | 真正执行 RTL、封装、OOC 和独立 checkpoint 复核，保留退出异常；fusion revision 2 取消写死 FREQ_HZ，跟随真实 BD 时钟，RTL 未变 |
| `scripts/check_dependencies.py` | 正式包逐文件匹配旧冻结清单，拒绝将不同 component/revision 的旧候选冒充正式包 |
| `scripts/build_system.py`、`system_build.tcl` | 从锁定 Git 对象只读取源，在 D 盘独立重建六核系统；真实综合/实现/导出门禁、命令/退出码/日志/源码哈希和不可覆盖的失败记录 |
| `scripts/make_joint_golden.py` | 在 RGB8 输入边界中心裁剪到 1272×720；新尺寸重跑全部模型，先比较历史 CNN 19,080 标量，再生成新同图 Golden |
| `tests/test_joint_models.cpp`、`scripts/verify_joint_models.py` | 真实冻结 HLS C/native 模型全帧比较；真实融合 AXI RTL 用同图 I/L/D 输出再比较，不冒充完整六核 RTL |
| `scripts/accept_system.py`、`tests/test_acceptance.py` | 实际 routed setup/hold/pulse-width、完整 bus-skew、无钟/未约束、route、严重 CDC/DRC 与同身份数值门禁；按真实 Vivado whitespace CDC 与 pipe DRC 两种格式解析，缺证据拒绝 |
| `docs/clock_coverage.md` | 记录综合 8 个 PS8 输出的诊断，独立 routed/export 零负载证明；保留各阶段原始计数，不加假时钟、false-path 或 waiver |
| `scripts/collect_delivery.py` | 真通过后才打包；核 XSA CRC、两次 bitgen 配置逐字节一致、规范 bit 与 XSA 完全一致，从多个 HWH 中唯一识别六核 system.hwh；核全部 DDR LOW masters/时钟/复位/版本/地址，归档真实日志/Tcl，生成 manifest、SHA256SUMS 和 ZIP |
| `scripts/collect_review.py` | 独立融合核 ABI、ZIP、源 RTL 和 OOC checkpoint 复核；不替代联合系统状态 |
| `evidence/*.json` | 保留旧失败和缺件历史，新增正式补交核验和本轮阶段结果；最终 source_hashes 记录可审核文件身份 |

## 2. 已实际验证

- 补交基线 `3c9e41a35fc08d44ba0552ce6916a421f98f94d7`。正式 ZIP SHA256=`b5b69f1d3d1e3f69e9f825be5453b086c58b4d863a3a9889693a247101b9c2cf`；406/406 文件与旧冻结清单逐字节匹配，原缺件阻塞解除。Compact D 保持 `d8880cce7241628f5472a36802b1791e85935e27` 和原 ZIP/bundle 身份。
- 原融合 RTL 单元/图样全帧通过：655,360 标量覆盖全 INT16 编码、权重/裁剪/RNE；另完整生产帧 2,747,520 标量零差异。9 个非法调用零 DDR，覆盖读写错误、背压、忙时重写和启动快照。
- 同图 Golden：仅在 RGB8 输入中心裁剪 `[4,0,1276,720]`，两模型用同一 1272×720 输入重跑；未裁剪旧 1280 宽 D 输出。历史 CNN 19,080 标量零差异；全部 22 个 D 软件整数节点新尺寸执行完成。
- 实际锁定 HLS C/native 模型共 13,775,760 标量零差异，包含 prepare 三输出、CNN、Bilinear、Curve、D 最终全帧。真实融合 AXI RTL 再比较同图 2,747,520 标量零差异；4,121,280 次 32-bit 读和 1,373,760 次写。
- fusion revision 2 IP integrity、ZIP CRC、20 个 UINT32 寄存器、AXI4/AXI4-Lite 宽度、生产 count 和打包 RTL 核验通过。prepare 锁定源码真正重建成功，并核实际导出 header 的 64-bit pointers 和 ABI。
- 六核 BD 真正重建并 validate 通过。A000–A005 六个 64 KiB 地址不冲突；所有新增 master 实际映射 2 GiB DDR LOW；D 双时钟 SmartConnect 和分别同步复位实际接线。PS 时钟元数据 99,999,001 / 199,998,001 Hz。
- 26 个 controller/报告验收单元测试和 Python 编译检查通过。涵盖实际 Vivado CDC 文本格式、bus-skew 缺项/负 slack、未知/有负载无钟项和 raw=0 与额外 8 引脚证明的区分；原始日志见 `evidence/unit_tests_final.log`。

融合 OOC 原进程写 DCP 后发生 EXCEPTION_ACCESS_VIOLATION，原 ooc_result 仍为 false。独立 Vivado 正常退出，重开同 SHA DCP 并重出报告：LUT 1,836、FF 926、DSP 6、BRAM/URAM 0，100 MHz OOC WNS +2.023ns / WHS +0.109ns。它不是联合 routed 签核。Windows DLL/厂商 Python 环境和 BD 时钟元数据失败日志保留在外部目录，没有覆盖为成功。

## 3. 联合实现与验收

联合综合和布局布线均正常退出，实际 routed 结果如下：

| 项目 | 最终结果 |
| --- | --- |
| LUT | 78,753 / 117,120（67.24%） |
| FF | 92,793 / 234,240（39.61%） |
| BRAM | 72.5 / 144 tiles（50.35%） |
| URAM | 58 / 64（90.63%，主要容量瓶颈） |
| DSP | 922 / 1,248（73.88%） |
| Setup / Hold / Pulse-width | WNS +0.032ns / WHS +0.010ns / WPWS +1.700ns |
| 布线 | 183,014 / 183,014 routable nets；routing errors=0 |
| Bus-skew | 全部 17 项通过；最差 slack +3.898ns |
| 最终原始时序覆盖 | no_clock、constant_clock、multiple_clock、unconstrained_internal_endpoints 均为 0 |

实际 routed DCP SHA256=`a189968e406be1ec94bd0355f97bd63758813ef75101b50eb26b7f064ad85b2a`。独立 `coverage` 阶段重开该 DCP，额外逐项证明 8 个未用 PS8 EMIO 输出零 PL 输入负载、零顶层端口、零关联时钟。综合阶段的原始 no_clock=8 仍保留，未拿综合证明替代 routed 验收。

保留的告警：471 项 CDC-15 Warning，逐项均在 cnn_data_sc/curve_ddr_sc 的 XPM memory FIFO；DSP 流水线 DPIP-2=447、DPOP-3=202、DPOP-4=384；RTSTAT-10=1（35 条无可布线负载的内部网）。没有 Critical CDC、DRC Error 或 Critical Warning。原始报告没有被压制。setup 余量较小，修改 IP/时钟/集成后必须重新实现，不能复用此签核。

实现 attempt 1–5 的 false receipts 和日志全部保留：早期脚本使用不支持的阶段名、误用整个流程的 100% 进度判断、部分 run 的 `open_run` 限制及不支持的通用 Tcl `redirect`。最终按 Vivado 实际阶段状态、NEEDS_REFRESH、route 完成标记和 checkpoint 验证，直接打开已完成的 route DCP，真实执行 post-route `phys_opt_design`，attempt 6 正常退出。物理优化报告没有 setup 违例且未改网表；未重复综合/布线，未降频或新增 false-path。最终 bit/XSA 正常导出，打包器和独立复核均通过。

未执行：完整六核系统联合 RTL 仿真、KV260 板端编译/加载/数值核对/实际耗时或 FPS 测量。未连接板卡，未训练或修改官方模型/参数/权重。

## 4. 本地工件

- 正式融合 IP：`D:/weather_builds/joint_fusion_package08_20261029/package/joint_fusion_ip.zip`，SHA256=`7ece7f03c2d9aca56e5a9284dea1f507832e52ac51daa603d5c6ce3eac65dedc`。
- 新同图 Golden：`D:/weather_builds/joint_golden01_20261029/`。
- 实际 HLS C 模型结果：`D:/weather_builds/joint_model_host02_20261029/`。
- 同图融合 RTL 结果：`D:/weather_builds/joint_fusion_image01_20261029/`。
- 联合系统：`D:/weather_builds/joint_system05_20261029/`，联合实现、独立验收和导出均通过，原始失败及成功证据仍保留。


- 最终硬件目录：`D:/weather_builds/kv260_joint_delivery_20261029/`，状态 `HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED`。
- 最终 ZIP：`D:/weather_builds/kv260_joint_delivery_20261029.zip`，204,274,955 字节，SHA256=`01f0ac7214f1ed8fad6df4adb2b453a31fe751e8ebd38b8462fd91a6ea39a047`。
- Build ID=`ddc052ce9f6385f3ac7d`；111 个 payload + manifest + SHA256SUMS 共 113 文件；112 条 checksum、ZIP CRC 和 payload 哈希全部核验。完整加载顺序、DMA/CMA 环境要求和未验证范围随包提供。
- XSA 包含 6 个 HWH；按六核完整实例集合唯一识别 `system.hwh`，其余为 SmartConnect 子模块。最终根目录 bit/HWH 均与 XSA 对应成员逐字节一致。
- 两次 bitgen 的原始 bit 只有创建时间头不同；已严格核 design/part 与全部 7,797,692 配置字节相同。构建目录原件保留，交付根目录采用 XSA 内嵌 bit；没有将原来不相等的完整文件哈希记作相等。证据在 `evidence/bitstream_equivalence.json`。
- XSA 导出日志保留 `WARNING::74 Unsupported FPGA device name xck26-sfvc784-2LV-c`；命令正常退出并报告 Hardware platform 生成成功。该日志随包交付；Vitis/BSP 生成与目标板编译均未执行。

模型数组、IP 构建目录、checkpoint、波形和大工件留 D 盘，未上传 GitHub。

## 5. 建议 Commit Message

`feat(fpga): integrate locked KV260 pipelines with Q14 three-way fusion`

## 6. 分支与工作区状态

开发工作树 `C:/Users/wzh16/Desktop/github clone/feat-software`，分支 `feat/software`，HEAD=`9ef5fafa90ffd3c8ededbf22b3cf8ccb3bf16fce`。仅本目录为新增未跟踪文件，既有 tracked 文件未修改。

队友工作树 `C:/Users/wzh16/Desktop/github clone/codex-curve-fp32-baseline` 保持 clean，位于 `codex/curve-fp32-baseline@3c9e41a`。未执行 add/commit/push、创建/切换分支、合并/PR、删除、reset、clean 或 force push。本地清单和真实结果已整理完毕；到此停止并等待用户审核，不自动执行任何 Git 发布操作。
