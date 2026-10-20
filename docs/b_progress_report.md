# B 侧继续开发与核查报告

日期：2026-10-20。工作目录：`C:/Users/wzh16/Desktop/competing/weather_fpga_integration`。

最新进展以 [系统集成记录](system_integration_20261020.md) 为准：修正版新核两任务实际 CSim/综合/8×8 RTL/IP、连续变尺寸 RTL 和独立 AXI RTL 已通过；合并系统完成布局布线，100 MHz 时序通过。最终 bit/XSA 状态见该记录。本文下方保留此前开发轮次的历史状态，不作为当前待办清单。

后续更新：本报告记录的 Vitis 启动阻塞已定位并修复。通过项目内桌面启动器已完成后续 HLS/Vivado 构建，工具版本为 2025.2；见 [启动修复报告](vitis_windows_startup.md)。下文关于启动失败和未执行流程的描述仅保留原始轮次证据。

## 历史轮次做到什么程度

本轮已完成新的整帧 DDR/片上 C8 计算原型、现有 A 组 tile IP 的 portable PS 控制和 CPU 拼图适配，并完成可复现主机验证。去雨、去雾各 30 个官方节点逐位一致，两任务 720×1272 和 720×1280 整帧与原始核分块结果逐位一致。

这还不是完成上板交付。新核的 Vitis 启动检查失败，未进入 vendor CSim/综合/RTL。PS 控制的板端 DMA/cache/MMIO 后端、Vivado 系统连接、implementation、真板与持续视频测试尚未完成。A 原核已有的 HLS/8×8 RTL 结果，和旧低照度系统的 bitstream/时序结果，都不能作为新 weather 原型的结果。

本轮工作在独立目录中进行；文件名使用英文。没有训练或重新量化模型，没有修改队友原始交付。

## 修改和新增的文件及原因

以下路径相对于本工作目录。该目录无 Git，因此这里按本轮交付单元列明内容，不伪造 Git diff。

| 文件 | 原因与关键差异 |
|---|---|
| `experiments/onchip_frame/src/weather_frame.cpp` | 增加整帧 top；PL 内部 halo gather，片上 RGB/C8 bank，通道展开和平衡加法树，融合残差/ReLU，只写有效 core，移除新接口的外部 scratch |
| `experiments/onchip_frame/src/weather_frame.h` | 定义实验 ABI v2、任务选择、范围、返回值和 host-only trace hook |
| `experiments/onchip_frame/src/weather_kernel_reference.cpp`、`weather_kernel.h`、`params_derain.h`、`params_dehaze.h` | 固定 A 原始参考和两模型参数，用 SHA-256 校验来源；参考源本身不做优化 |
| `experiments/onchip_frame/tests/test_weather_frame.cpp` | 比较真实原型输出/trace，覆盖全部 30 节点、边界、拼接、极值、连续调用和非法调用 |
| `experiments/onchip_frame/hls/tb_weather_frame.cpp` | 独立 Golden TB，读写小端原始 INT16，比较全量输出，不把参考核一起综合 |
| `experiments/onchip_frame/scripts/verify_host.py` | 校验参考/Golden 身份、严格编译、主机数值/整帧/负对照验证，保存可复现日志和哈希 |
| `experiments/onchip_frame/scripts/run_hls.py` | 将匹配 passing host report 的源码及 A fixtures 放到新 ASCII 目录；生成 K26/10 ns 配置，按真实版本/输出/报告/IP 产物判定结果 |
| `experiments/onchip_frame/README.md` | 给出主机验证、HLS 准备/运行命令和工具限制 |
| `deployment/weather_control.h/.c` | C11 控制层支持 v1/v2，校验 buffer、配置 64 位地址、有界轮询、所有权切换、启动前回滚、超时隔离及 reset/drain 恢复 |
| `deployment/weather_tiled.c` | 支持 A v1 IP 的 core64/128、halo6 CPU gather/crop/scatter，先查空闲再搬输入，故障报告已完成 tile 数 |
| `deployment/tests/test_weather_control.cpp`、`tests/verify_driver.py` | 用真实 C++ 核配合 MMIO/DMA mock，核查控制故障与拼图，保留编译/运行证据 |
| `deployment/README.md` | 说明板端后端必须满足的 MMIO、DMA/cache、缓冲区和恢复合同 |
| `tools/weather_budget.py` | 增加原核逻辑激活访存、staging/整帧两种外部流量、计算通道需求和原型 core-only tail 预算；将物理 DSP 与假设 MAC 通道分开 |
| `docs/performance_optimization.md` | 解释优化落点、带宽与计算预算，以及 URAM 映射/II/时序待验证风险 |
| `docs/weather_frame_v2_contract.md` | 发布新原型的独立 shape/layout/Q14/DDR/CSR/所有权/时序约定，并标明尚未生成硬件 |
| `README.md`、`docs/open_items.md`、`weather_dataflow.md`、`weather_ddr_contract_draft.md`、`v1_2_reuse_matrix.md`、`a_compute_handoff.md` | 同步实际进度，保留 v1 原包事实，补充 v2 及主机/硬件边界，修正“工具不存在”为实际启动失败 |
| `.gitignore` | 补充 `work/`、`build/`，排除本地可执行程序、原始 trace、工具运行目录等生成物 |
| `evidence/b_progress_20261020.json`、本报告 | 保存小型验证快照和完整人工核查说明；不包含数据集或运行张量 |

## 接口选择与兼容性

已有 A IP：`derain_top` / `dehaze_top`，固定任务，单次 tile 最大 140×140，input/output/scratch 三个 DDR master，ABI v1。原包仍在 `ip_repo/`、`ip_archives/`，没有被新原型替换。

新增原型：`weather_frame_top(input,output,height,width,task)`，整帧最大 720×1280，RGB NCHW、小端 INT16 Q14，两套固定参数按任务切换，两个 DDR master，没有外部 scratch 或 AXI Stream。它是 ABI v2，`0x30` 为 height；A v1 此处是 scratch 指针，严禁混用。v2 寄存器来自源码显式约定，须在真实导出后再与头文件、`component.xml` 核对。

weather 两个接口均输出增强后的整帧/整块 RGB；低照度链的 `A_low → Bilinear → Curve` 是另一路。当前工作未把 weather 输出接入 Bilinear 或 Curve。

## 实际执行过的验证

编译器：`D:/vivado/2025.2/tps/mingw/8.3.0/win64.o/nt/bin/g++.exe` 及同目录 gcc，Python：`D:/Dev/Miniconda3/python.exe`。C11/C++11，`-O2 -Wall -Wextra -Werror`；普通主机编译对 HLS pragma/标签作必要忽略，Windows 测试程序静态链接。

| 验证 | 实际结果 | 证据 |
|---|---|---|
| 固定源与参数身份 | 4 个 pinned 文件 SHA-256 一致 | [主机报告](../work/onchip_host_20261020_02/verification.json) |
| 官方 96×96 Golden | 每任务最终输出完全相等；共 60 个节点文件逐位/逐哈希相等 | 同上及 `derain_trace/`、`dehaze_trace/` |
| 合成输入逐层验证 | 共 12 组 30-node 用例：两任务、1×1/7×11/140×140、普通/极值 | [selftest 日志](../work/onchip_host_20261020_02/selftest.log) |
| 合成整帧/边界 | 20 个 frame 用例，含 145×149 四类输入、core64/128、单行/单列和六次交替任务/shape | 同上 |
| 大整帧 | 两任务 × 720×1272/720×1280 共 4 组，和原 A 核 core128 分块结果逐位相等 | 主机报告各 `*_720x*.log` |
| 非法调用及越界防护 | 11 次非法维度/任务调用通过，输出 guard 和输入不变检查通过 | selftest |
| 比较器负对照 | 两任务各破坏输出 1 LSB，均被相同输出比较器拒绝 | `*_negative_control.log` |
| 独立 HLS TB 的主机运行 | `__SYNTHESIS__` 路径编译；两任务各 96×96、8×8 实际输出字节等于 Golden | `*_hls_tb_host_*.log`；不是 Vitis/RTL |
| portable PS 控制 | C11 编译、C++ 链接及状态机全部通过 | [driver 报告](../work/driver_host_20261020_02/verification.json) |
| PS tile 拼图 | 两任务 core64/128 的 145×149，mock MMIO 调实际 A C++ 核，结果逐位相等 | [driver 日志](../work/driver_host_20261020_02/driver_suite.log) |
| PS 故障与任务切换 | >4 GB 地址、stale done、连续调用、别名/容量/溢出、busy、auto-restart、回滚、不确定启动、超时/停止时钟、失败/成功恢复、CPU sync 故障、v2 任务 0→1→0 通过 | 同上 |
| 计算预算复核 | 1×1 有效 MAC/读写手工计数一致；整帧 I/O 两场景数值一致 | [预算 JSON](../work/weather_budget_720x1272.json) |
| A 原始交付最终复核 | 3,179 文件长度及 SHA-256 全部一致；两个 IP ZIP 哈希与原交付一致 | [最终清单复核](../work/a_manifest_final_20261020.json) |

先前已重跑 A 审计 143 项通过，记录在 `work/a_delivery_audit_rerun.json`；本轮最后做了上表的全清单复核。外层 ZIP 本地仍缺失，不能复算外层 ZIP 哈希。

这些主机测试验证整数结果、内存边界和软件状态机。mock 的 DMA 地址和缓存操作是模拟的，不证明真实 AXI 事务、缓存一致性、内存吞吐或时序。

## HLS 实际尝试与未执行项

已生成两任务的 staged sources、经 A manifest 校验的 fixtures 和 K26/10 ns 配置。执行带 `Vitis/settings64.bat` 的 `vitis-run.bat --version` 后，退出码是 0，日志为空。新 runner 将其判为失败；[HLS 运行报告](../work/onchip_hls_20261020_01/run.json) 的 `pass=false`、`completed_through=prepare`。直接可执行程序的先前探测也出现 Windows 启动错误，尚未定位缺少的运行库。

新原型未执行成功的项目：vendor CSim、HLS 综合、RTL co-sim、IP 导出、生成 CSR 核对、Vivado BD 集成、布局布线、bitstream/XSA、真板单帧及连续帧。HLS runner 的后续命令也尚未在可工作的 Vitis 环境验证。

板端尚未实现/验证的项目：实际 DMA 分配与 cache ownership 回调、有序 MMIO 后端、reset 后停止并排空在途 DDR 事务、采集/显示、模式策略、生产视频传输和低照度共存。不能把这些列为“B 组全部完成”。

## 性能结论与后续顺序

720×1272 的整帧原型理想外部 I/O 为 11.95344 MB/帧，30 FPS 折算 358.6032 MB/s；这是包含 halo 重读的源码预算，不是 DDR 实测。原 tile ABI 在假设片上特征但保留 DDR staging 时为 36.82368 MB/帧；A 原核的 2.82076608 GB/帧是逻辑数组引用，不是总线实测或加速倍数。

原 tile 工作量在 100 MHz 下理想需要 298 条 1 MAC/周期通道，新原型 core-only tail 预算约需 296 条。37 DSP 不能直接视为 37 条 MAC 通道；源码展开和 II 请求也不能证明达到 30 FPS。744,800 字节片上数组、URAM reshape、ROM 并行读、部分字写与真实调度仍需综合确认。

接下来先修复或换用正常 Vitis 环境，跑 CSim/综合并查看资源、II、周期，再做两任务 RTL 以及生成 CSR 对照。并行可在板端绑定现有 v1 IP 的 PS 后端，按单 tile → 拼整帧 → 多帧逐级验收。随后才做系统 implementation、连续视频和性能优化。详细门槛见 [待办](open_items.md)。

## Git 与人工审核状态

本工作目录不是 Git checkout，没有绑定分支，因此此处没有“已经在 feat/software”或“已经 push”的状态。相邻 `C:/Users/wzh16/Desktop/competing/fpga clone` 仍是 `main...origin/main`，有进入本轮时就存在的修改/未跟踪文件，检查前后列表一致。本轮未操作该 checkout 的内容，也未拉取远端或判断 ahead/behind。

没有执行分支创建/切换、`git add`、`git commit`、`git push` 或 PR。当前是本地文件待人工核查状态。依据根 `AGENTS.md`，修改说明和验证已在本报告列明，后续 Git 操作须获得当次明确批准；不能直接把此目录全部自动上传。

建议 Commit Message：

```text
feat(weather): verify on-chip frame core and add portable PS control
```

迁入获准的 `feat/software` 时，应保留源码、脚本、合同和小型证据快照，按仓库目录说明放置；`work/`、测试可执行程序、原始 trace、数据集、本地备份和运行输出不进入 Git。原有 A IP 包如需再次上传，先核对目标仓库已有内容和体积。
