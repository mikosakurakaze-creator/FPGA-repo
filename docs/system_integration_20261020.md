# Weather 与低照度系统集成记录

历史说明（2026-10-21）：本文保留 `frame04/system02` 串行 tile 版的执行证据，该版不能满足 720p30。当前 `stream02/stream_system01` 流水版及其新时序、周期、交付位置见 [修正记录](stream_revision_20261020.md)。下文“当前”均指本文记录时的旧版状态。

## 当前状态

本轮按用户要求实际执行 HLS、系统集成及 Vivado 构建。初版 `frame03/system01` 完成了小图 RTL 和系统综合，但在追加变尺寸回归时发现输出写回卡死，已取消其交付资格。现已通过行缓存拆分计算与 DDR 写回，修正后 host 全量比较、`frame04` 两任务 HLS 流程、五帧 vendor co-sim、七次独立 AXI RTL 及负对照全部通过。最终系统 `D:/weather_builds/system02` 已完成综合、布局布线、bitstream 和含 bit 的 XSA，100 MHz 时序通过，最终 32 项离线核查全部通过。这是可进入上板联调的硬件候选；PS ELF 尚未构建，真板尚未运行。

工作目录是独立的 `weather_fpga_integration`，不是 Git 仓库。没有修改 Git 克隆、切换分支、暂存、提交或推送。

## 1. 与原系统怎样连接

沿用保存的 V1.2 `system.bd`，器件 `xck26-sfvc784-2LV-c`、KV260 SOM、PS PL0 名义 100 MHz。保留 PS 的全部 385 项配置，以及低照度三个模块的控制地址和 DDR 连接。

| 模块 | AXI-Lite 地址 | DDR 路径 |
|---|---|---|
| Bilinear | `0xA0000000` | 原 HP2 |
| Curve | `0xA0010000` | 原 HP3 |
| 低照度 CNN | `0xA0020000` | 原 HP0 数据/工作区、HP1 参数 |
| 新 Weather Frame | `0xA0030000` | 输入共享 HP0，输出共享 HP3 |

新核与旧链路是独立模式。Weather 直接输出增强 RGB，不能将它当作曲线参数送进 Bilinear。首版调度串行使用一个加速模式，共享 DDR 的 SmartConnect 负责仲裁；没有证明多模式并发的吞吐量。

Weather 只开放低 DDR 的 `[0, 2 GiB)` 地址窗口。该窗口是硬件可达范围，不表示 CPU 可以任意覆盖其中内存。实际缓冲区由裸机应用链接器分配，Linux 仍需平台 DMA 分配与映射。

## 2. 新核接口合同

`weather_frame_top(input, output, height, width, task)`，`ap_ctrl_hs`，两路 `m_axi`，一组 `s_axi_CTRL`。实际生成接口是 32-bit AXI 数据、64-bit 地址。每个图像元素是 signed INT16，Q14，即 `real = raw / 16384`；RGB、NCHW、little-endian、连续无 stride。

- `height = 1..720`，`width = 1..1280`。
- `task=0` 去雨，`task=1` 去雾。
- 输入与输出互不重叠，每份至少 `6*H*W` 字节。
- 正常图片输入 `[0,16384]`；支持完整 signed16 数值边界，输出限制 `[0,16384]`。
- 无外部 scratch、无动态权重、无 AXI Stream。
- 一次一帧；关闭 auto-restart；超时保留设备所有权，不自动 reset 或复用缓冲区。

| 寄存器 | offset |
|---|---|
| AP_CTRL | `0x00` |
| 返回状态 | `0x10` |
| 输入地址 input 低/高字 | `0x18 / 0x1C` |
| 输出地址 output 低/高字 | `0x24 / 0x28` |
| 高度 height | `0x30` |
| 宽度 width | `0x38` |
| 任务 task | `0x40` |

这些偏移已与实际生成的 driver header、BD、RTL 核对。返回 0 成功，1 尺寸非法，2 任务非法。整数格式与 A 交付保持一致；CNN 内部层激活不是统一 Q14，仍遵守各层原始缩放、RNE 舍入及饱和规则。

Vivado 会提示 HLS 的 2-bit AXI LOCK 与 SmartConnect 的 1-bit LOCK 宽度不同。已检查新核实际生成 RTL 的两个 LOCK 输出固定为零，丢弃高位不会启用锁定事务。其余 SmartConnect 内部宽度提示保留在构建日志，不能简单把提示数量当作 timing fail。

## 3. 为了能综合做了哪些修正

第一次真实 HLS 发现整份参数 ROM 被并行读端口反复复制：501 BRAM18K，超过 K26 的 288 块；最长估算 11.418 ns。没有将这版作为可交付硬件。

修正为每层先从固定模型 ROM 顺序加载权重、偏置与缩放参数，再由小型分区寄存器供并行 MAC 使用；重定标函数增加流水级。卷积拓扑、固定权重、节点舍入/饱和顺序和输出公式没有变化。

| 天气核 HLS 估算 | 修正前 | 修正后 |
|---|---:|---:|
| BRAM18K | 501 | 86 |
| URAM | 32 | 32 |
| DSP | 113 | 109 |
| LUT | 58,202 | 50,470 |
| FF | 15,036 | 22,029 |
| 估算时钟周期 | 11.418 ns | 8.348 ns |

该表是 HLS 估算，不是整个系统的 post-route 资源/时序。片上缓存仍是 128×128 core 加 halo6、最大 140×140；PL 自己按帧地址读入 tile，卷积中间特征留在片上，最后仅写有效 core。

另修正 RTL 测试台：即使测试 8×8，vendor wrap-C 也按声明的最大 m_axi depth 复制缓冲区。测试台现在分配完整 depth，比较有效输出并检查剩余 guard，解决原来的越界 SIGSEGV。

追加回归还发现了真正的 DDR 写回卡死：131×1 输入读完后输出为 0 beat。自动合并的深计算流水和行 burst 请求/响应形成循环等待。现将一行尾层计算写到片上 row buffer，再由独立短循环写 DDR，禁止外层循环合并。独立 AXI-Lite/有停顿 DDR RTL 测试负责回归，具体失败证据与修正见 `ddr_writeback_deadlock.md`。

## 4. 缺失的旧 IP 怎样处理

Git 克隆不包含历史 `E:/HLS` 构建产物，用户确认没有另存包。因此将冻结低照度源码及三个 include 依赖复制到独立输出目录重新综合。

重建 CNN 的 305 项历史 payload 中 303 项逐字节相同，差异只有 `component.xml` 和 `dfx_runtime.txt`；三个原始 writer RTL 的 hash 全部与原补丁前输入相同。随后将历史三个 write-credit writer 补丁按既定 hash 恢复，综合与仿真均选择 Verilog 视图。

新包有新的身份，不声称重建出了历史完整 bitstream 的相同 SHA，也不继承历史板测结果。Bilinear/Curve 源码原样重建。

## 5. 实际完成的验证

- `work/onchip_host_20261020_06/verification.json`：行缓存修改后全部通过，包括两任务 60 个 Golden 节点、边界、任务/尺寸交替、720×1272 与 720×1280 整帧比较、1 LSB 负对照。
- `work/frame03/run.json`：历史小图 HLS 流程通过，但被 `work/rtl_memory03` 的变尺寸 RTL 反例淘汰，不能作为当前可用核。
- `work/frame04/run.json`：行缓存修正版两任务 CSim、综合、8×8 RTL 和导出全部通过；8×8 实测各 **13,543 cycles**。
- `work/driver_host_20261020_04/verification.json`：C11 控制/分块适配、真实 C++ 核与模拟 MMIO/DMA 测试通过。
- `D:/weather_builds/system02/interface_audit.json`：实际生成 BD、寄存器偏移、32-bit AXI/64-bit 地址、时钟/复位、两路低 DDR 窗口共 25 项离线核对通过。
- `D:/weather_builds/system02/interface_final_audit.json`：上述核查加实际综合用 Verilog/ROM 身份、四份 ROM 成功读取记录、天气核综合 checkpoint、XSA CRC/内嵌 bit/HWH，共 **32 项通过**。Vivado 将 Verilog 放在 `ipshared`，ROM `.dat` 放在具体生成 IP 目录；核查器已分别读取实际目录，不将未找到共享目录下的 ROM 误判为内容差异。首次路径错误报告保留在 `interface_final_audit01_path_failure.json`，未更改硬件。
- `work/sequence05/run.json`：五次连续 vendor RTL co-sim 通过，含 task 0→1→0 与 131×1、1×133。
- `work/rtl_memory05/run.json`：同一实例七次 AXI-Lite 配置与有停顿 DDR RTL 通过，两任务各一个 131×133 与原 A reference 逐位相等，实测分别 3,536,087 / 3,536,339 cycles（包含测试台控制轮询和总线停顿）。检查地址、4 KiB burst 边界、WSTRB、WLAST、背压时稳定性、尾部 guard；额外延迟 B 写响应，在硬件 `ap_done` 当拍检查 DDR drain；故意改变 Golden 的 1 LSB 被拒绝。这些小图结果不能推出实际 720p FPS。

没有运行真板，没有当前板卡状态、生产缓存一致性、连续视频、实际 720p FPS 或相机到显示证据。

## 6. PS 缓存、控制与板端测试

新增 A53 standalone backend，调用 BSP 的 `Xil_In32/Out32`、`Xil_DCacheFlushRange/InvalidateRange`、`XTime_GetTime` 和 `dsb sy`。只接受缓存线隔离、linker-owned、identity-mapped 低 DDR 分配；不适用于 Linux 用户态。

测试应用包含两个独立 64-byte 对齐的最大帧缓冲区，按 0→1→0 切换模型，比较固定 8×8 Golden、输入不变性、整份输出尾部 guard，并输出启动至完成的微秒数。先将 guard 写回 DDR 再启动；完成后 invalidate，有错误就停留，超时不释放或复用缓冲区。

程序本身不配置 bitstream、PMU、电源或系统时钟。系统应按 KV260 的正常固件启动流程进入可运行状态后，再显式加载/启动 ELF。没有自动对真板执行任何操作。

实际尝试 BSP/ELF 构建后确认：本机是 HLS/Vivado 组件安装，缺少 `aarch64-none-elf-gcc` 和完整 Embedded SDK。Vitis 能生成 SDT，但平台创建失败。`work/standalone03/standalone.log` 有明确的缺编译器门禁；当前没有编译成功的 ELF，裸机后端尚未经过目标交叉编译或真板验证。脚本和源文件保留，补装匹配版本的 AArch64 Embedded 组件后可继续。

## 7. 新增/修改文件及原因

| 文件组 | 原因与关键差异 |
|---|---|
| `experiments/onchip_frame/src/weather_frame.cpp` | 层参数缓存、重定标流水、片上行缓存与独立 DDR writer，消除窄行写回卡死 |
| `experiments/onchip_frame/hls/tb_weather_frame.cpp` | 最大 AXI depth 分配和 guard 检查 |
| `system/*.tcl` | 可复现 create/synth/route/bit/XSA 阶段，独立工程 |
| `system/tb_weather_sequence.cpp` | 同一核模式切换与 tile seam RTL 验证 |
| `tools/rebuild_lowlight.py`、`restore_writecredit.py` | 缺失 IP 重建、原 writer 输入哈希门禁和补丁恢复 |
| `tools/build_system.py`、`audit_system.py` | 输入清单、阶段日志、生成后 ABI/DDR 核查 |
| `tools/run_sequence_cosim.py` | 复用已验证综合，独立运行五帧 RTL |
| `system/rtl_memory_test.sv`、`make_rtl_vectors.cpp`、`tools/run_rtl_memory_test.py` | 独立 AXI-Lite 配置、有停顿 DDR、7 次调用和 1 LSB 负对照，复现并回归写回故障 |
| `deployment/weather_xilinx_standalone.*` | 真正的裸机 MMIO、缓存与计时后端 |
| `deployment/standalone/*` | 可上板执行的三帧测试源与固定 Golden |
| `tools/prepare_smoke_vectors.py`、`build_standalone.py`、`run_standalone.py` | 固定向量清单核验和 BSP/ELF 构建脚本 |
| `tools/package_release.py` | setup/hold/pulse width、12 类时序约束检查、完整布线、阻断 DRC、RTL/ROM 身份、执行日志/脚本和 XSA 内嵌 bit 一致性门禁，收集本地候选与 SHA-256 清单 |

文档新增/同步：`README.md`、`deployment/README.md`、`experiments/onchip_frame/README.md`、`docs/weather_frame_v2_contract.md`、`docs/system_integration_20261020.md`、`docs/ddr_writeback_deadlock.md`、`docs/frozen_build_inputs.md`、`docs/board_bringup.md`、`docs/reproduce_system.md`、`docs/open_items.md`、`docs/b_progress_report.md`、`docs/candidate_package.md`；`evidence/system_lineage_20261020.json` 记录已通过报告、最终产物与 writer 溯源哈希。文档区分历史失败候选、当前构建和未执行的板测，避免把主机或 HLS 数据写成真板结果。

新增硬件构建脚本为 `system/create.tcl`、`system/synth.tcl`、`system/impl.tcl`、`system/package.tcl`；新增 RTL 测试源为 `system/tb_weather_sequence.cpp`、`system/rtl_memory_test.sv`、`system/make_rtl_vectors.cpp`。部署源包括 `deployment/weather_xilinx_standalone.c`、`.h`、`deployment/standalone/main.c`、`weather_smoke_vectors.h`。所有新增文件名为英文。

`tools/run_windows_desktop.py` 与 `docs/vitis_windows_startup.md` 保留已验证的 Windows vendor 启动修复；不修改系统安装、全局 Git 配置或原始 IP。

## 8. 性能与验收边界

当前是串行复用 tile engine 的功能集成候选。小图 RTL 周期已实测；720p 整帧是 host 数值比较，尚不是完整 RTL/真板 FPS 结果。**不能按已达到 720p30 或连续视频目标交付。** 后续仍需根据真板测时进一步并行化卷积、流水重叠和优化视频 DMA。时序 100 MHz 通过只代表布线后每拍满足时钟约束，不代表一帧能在 33.3 ms 内算完。

完整生产链路仍缺 Embedded A53 工具链/ELF、真板 DDR/缓存与连续帧验证、Linux DMA 后端（如选 Linux）、采集/格式转换/显示及正式画质样本评估。板端联调和硬件复现入口分别见 `board_bringup.md`、`reproduce_system.md`。

## 9. 工作区和 Git 状态

本轮所有实现都在独立非 Git 目录 `C:/Users/wzh16/Desktop/competing/weather_fpga_integration`；硬件临时构建在 `D:/weather_builds/`。共享 `competing/fpga clone` 仍为 `main...origin/main`，保留此前的 README/configs/deployment/docs/evaluation/model 等修改和未跟踪量化文件；本轮未触碰这些改动。没有对 `github clone/main` 写入，没有暂存、提交、推送、切分支或合并。构建二进制、样本与运行输出仅作本地交付，不自动进入 Git。

建议 Commit Message：`feat: integrate weather frame core with K26 DDR system and standalone control`。仅为建议，没有执行 Git 操作。

## 10. 最终系统的布局布线结果

证据为 `D:/weather_builds/system02/routed_timing.rpt`、`routed_utilization_summary.rpt`、`route_status.rpt`、`routed_drc.rpt`，不是 HLS 估算。

| 指标 | Post-route 实际值 |
|---|---:|
| PL 时钟周期 / 频率 | 10.000 ns / 100.000 MHz |
| Setup WNS / TNS / 失败端点 | +0.088 ns / 0 / 0 |
| Hold WHS / THS / 失败端点 | +0.010 ns / 0 / 0 |
| Pulse width WPWS / TPWS / 失败端点 | +3.500 ns / 0 / 0 |
| 已完成 / 可布线网络 | 128,824 / 128,824 |
| 路由错误 | 0 |
| CLB LUT | 67,994 / 117,120，58.05% |
| FF | 63,809 / 234,240，27.24% |
| BRAM tile | 107.5 / 144，74.65% |
| URAM | 50 / 64，78.13% |
| DSP | 256 / 1,248，20.51% |
| CLB 占用 | 12,817 / 14,640，87.55% |

最终 timing summary 的 setup 余量是 +0.088 ns；不能用此前 router 中途的 +0.056 ns 替代。`check_timing` 的 12 类问题计数均为 0，包括无时钟、未约束内部端点、无输入/输出 delay、组合环等。时序已达标，但余量较小，后续改核或改连接必须重新 implementation。

DRC 没有 Error/Critical Warning，保留 249 项 Warning：DPIP-2 共 99、DPOP-3 共 81、DPOP-4 共 68，属于 DSP 流水建议；RTSTAT-10 共 1，列出 25 条无可布线路由负载的网络，不等于 25 条未布线网络。另有 methodology 的 ULMTCS-1 控制集合建议。本文不将这些结果表述为“零警告”。

BRAM、URAM 与 CLB 位置占用已明显高于旧三模块设计，后续性能扩展需要结合这些资源余量评估。当前结果证明本次组合硬件完成布线并满足 100 MHz；尚未证明实时帧率或真板运行。

## 11. 本地交付位置与文件身份

本地候选目录：`C:/Users/wzh16/Desktop/competing/weather_fpga_integration/build/weather_system_k26_v1/`。

| 文件 | 用途 | 大小 / SHA-256 |
|---|---|---|
| `weather_system.bit` | 当前组合系统 bitstream | 7,797,826 bytes；`cf1d7b02828d2e494cf6b5cffc182c4e33b4c1df1f5adfdaa3c72301dfe4100c` |
| `weather_system.xsa` | PS 平台构建所用硬件描述，内含相同 bit | 4,189,362 bytes；`7a7ead84cb1ddc6aae521d6e808a9fc02da0cfa4d18020a8e98cc4c2b89efade` |
| `system_routed.dcp` | 当前已布线 checkpoint | SHA-256 见候选 `manifest.json` |
| `integration_report.md` | 本报告副本 | 与收集时本文一致 |
| `implementation_qualification.json` | 时序、约束完整性、布线和 DRC 门禁结果 | 包含警告分类，不能解释为板测通过 |
| `manifest.json` | 每份 payload 的大小与 SHA-256 | 不包含自身 |
| `ip_repo/`、`system_seed.bd`、`recipe/` | 四模块 IP、BD seed、源文件、冻结参数、PS 源码、脚本与文档 | 可按 `recipe/docs/reproduce_system.md` 重建到新目录 |
| `verification/` | host/HLS/RTL、旧核重建、writer 审计、系统执行日志和实际使用的 A fixture 子集 | 原 A 清单保留；该子集不等于完整 A 包 |

完整当前 Vivado 工程仍在 `D:/weather_builds/system02/project/weather_system.xpr`。候选包通过显式 IP/seed 重建，避免依赖旧机器的 `E:/HLS` 或某个原 Git 克隆位置。

候选的 `status.json` 明确记录 `board=NOT_TESTED`、`standalone_elf=NOT_BUILT_MISSING_A53_TOOLCHAIN`、Linux DMA/采集显示未集成和实际持续 720p FPS 未测。下一步是在完整 Vitis Embedded 环境构建匹配 XSA 的 ELF，再按 `recipe/docs/board_bringup.md` 运行板端 Golden/guard；当前 smoke 只覆盖 Weather，旧低照度 PS 调度需沿用并单独复验。
