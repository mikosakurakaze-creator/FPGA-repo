# GridDehazeNet FPGA 加速器候选

本目录保存 B 组新增的 GridDehazeNet 去雾核、整图 PL 调度器、DDR/控制接口、Vivado 系统脚本和复现工具。它与旧天气核并列集成；不替换旧去雨、旧去雾或低照度路径。Linux 驱动、设备树、上传和 HDMI 由软件侧负责。

## 当前状态

- 固定 A 组户外模型 INT16 bundle：`5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710`。
- 整图调度器已完成主机原生和 Vitis 48 位 C 仿真，8 组向量的 320 个节点逐位匹配。
- 新旧核系统已完成 Vivado 综合与布局布线。当前 routed 报告：100 MHz，WNS `+0.729 ns`、WHS `+0.010 ns`、WPWS `+3.500 ns`；191,089/191,089 个 routable nets 完成。
- Routed DRC 有 1,102 条普通 Warning（含 19 条 DPREG-7），无 Error/Critical Warning。已对实际 routed 网表的 19 个 DPREG-7 单元做 OPMODE 稳定组合审计，未发现稳定 P 反馈选择；审计范围和限制见 `docs/dpreg_opmode_audit_20261024.md`。
- `test_frame.exe` 已按用户授权重新运行：8 组、共 2,560 个节点逐位匹配，11 项错误描述符检查通过，进程退出码 0。该证据只属于本机 C++ 整图验证。
- 33×47 导出 RTL 冷暖帧回归曾按严格门禁启动，随后为尽快交付按用户要求停止；它没有被记录为通过，routed 新核/旧核数值回归也暂缓。
- reduced gate 已完成 bitstream/XSA 导出，发布文件位于 `../../board/releases/k26_weather_griddehaze_reduced_20261024/`；该目录的 README 列出真实完成项和延期项。

## 本轮主机验证记录

2026-10-24 已从该副本编译并运行新生成的 `test_frame.exe`：8 组 case 的 320 个节点逐位匹配，共核对 2,560 个节点输出和 8 个最终输出，11 项错误描述符检查通过。首次直接启动被 Windows 拒绝，之后经仓库已有的 `run_windows_desktop.py` 启动成功。详细结果、EXE 哈希和范围限制见 `docs/native_verification_20261024.md` 与 `.json`。这只证明主机 C++ 路径，不代表 HLS/RTL、post-route、真板或 DMA 验证。

本地副本预检发现并已补全 A 组交付包的源码哈希校验文件夹；预检通过。`work/` 与 `a_candidate/` 仍由本目录 `.gitignore` 排除，因此本机参数和 Golden 不会意外进入 Git。
## 目录

- `hls/`：卷积/反卷积 tile、逐元素核、整图调度器和 C++ testbench。
- `src/`：独立 CPU 整数参考与固定点数学工具。
- `system/`：新系统 BD、综合/实现/导出 Tcl、AXI 内存 testbench。
- `tools/`：参数审计、内存规划、HLS/RTL/Vivado 构建门禁与结果收集脚本。
- `docs/`：接口合同、执行记录、假设与限制审查。
- `a_candidate/`：本机复现所需的 A 组参数包和小型 Golden 向量。本目录级 `.gitignore` 将其排除在 Git 外；未复制 675×1280 和 720p 大图样本。
- `work/`：生成的仿真、报告、日志和工具项目，排除在 Git 外。

## 本机复现入口

在本目录启动 PowerShell。`work` 使用全新子目录名，不覆盖已有结果：

```powershell
New-Item -ItemType Directory -Force work | Out-Null
python -B tools/preflight.py --out work/preflight_local01
python -B tools/frame_trial.py --stage native --out work/native_local01
```

完整 Vivado 工作流需使用当前安装的 Vitis/Vivado 2025.2、已验证的 Windows 工具启动器和独立构建目录。详细命令、阶段门禁和限制见 `docs/reproduce_frame_system.md`。RTL 仿真可能持续数小时；仿真周期数不是板端耗时或帧率。

## 数据与交付边界

仿真 DDR 地址只用于无重叠地址空间检查，不能证明真板连续 DMA 内存可分配。450 MiB 是当前 720p 逻辑 scratch 容量，不是已测 CMA 结果。100 MHz 是实现约束和 routed timing 报告，不代表实测板端吞吐。当前 bit/XSA 是 reduced-gate 本地硬件候选；完整数值回归和真板验证仍由后续联调完成。

