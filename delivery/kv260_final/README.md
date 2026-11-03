# KV260 最终可复现工程包

整理日期：2026-11-03。最终 PL Build ID：`c6496c6dc89aa54c4500`。硬件算法与镜像不变；PS 软件为六槽不同输入批处理版，界面不显示 FPS。

本目录是最终交付入口。仓库其他目录保留历史开发记录，不作为本版本启动入口。包内不包含技能包、作品报告、论文、PPT、完整数据集、虚拟环境或工具链安装程序；`hardware/reports` 是交付要求中的综合/实现工具报告，`validation` 是原始验证证据。

## 交付内容

| 交付要求 | 对应目录 |
|---|---|
| RTL、HLS 与 PS 源码 | `hardware/source/rtl`、`hardware/source/hls`、`hardware/source/implemented_inputs`、`source_models`、`ps` |
| 仿真、功能验证 | `hardware/evidence`、`hardware/source/tests`、`validation/host`、`validation/board` |
| 综合与实现、资源、时钟、时序 | `hardware/reports`、`hardware/manifest.json`、`hardware/clock_reset.md` |
| 上板产物、实测记录及 Golden | `hardware/joint_system.*`、`hardware/golden`、`validation/fifo_hardware`、`validation/package_board` |
| 可复现构建与运行 | `scripts`、`ps/launch.sh`，具体步骤见下文 |

## 环境

- 板卡：KV260 / K26，Ubuntu 22.04 aarch64，Python 3.10。
- 已验证内核：`5.15.0-1027-xilinx-zynqmp`，需安装对应 headers，驱动须在目标板编译。
- 系统依赖：`build-essential device-tree-compiler python3-pip python3-gi python3-gi-cairo python3-numpy python3-pil gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good`。
- `runtime_assets` 提供 ONNX Runtime 1.23.2 的 Python 3.10 ARM64 wheel、其纯 Python 依赖、SSD 模型与 FFmpeg 7.0.2 ARM64 静态发行包；不包含误下载的 Windows protobuf wheel。NumPy 与 Pillow 使用板端系统包。
- 硬件重新构建：Vivado 2025.2，安装 Zynq UltraScale+ 器件与 KV260 board files；如重新执行 HLS 则另需 Vitis HLS 2025.2。工具链不随包分发。

## 最短复现流程

将本目录完整复制到板端任意普通用户可写目录，先进入该目录。应用不依赖 `/home/ubuntu/traffic_hdmi` 等历史路径。

```sh
python3 scripts/verify_package.py
sh scripts/install_runtime.sh
sh scripts/build_driver.sh
python3 scripts/load_board.py
```

首次启动应从正常重启后的官方 base 镜像开始；关闭旧硬件任务。加载程序默认只做检查，以下命令才实际加载本包镜像：

```sh
sudo python3 scripts/load_board.py --execute
sudo sh scripts/start_service.sh
```

硬件服务在前台保持运行。另开普通用户终端，在板端桌面会话中启动：

```sh
sh ps/launch.sh
```

SSH 启动图形界面时需使用实际桌面 `DISPLAY` 与 `XAUTHORITY`；已验证系统为 `DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority`。图像由 PS Linux/GTK/Cairo 绘制，经系统显示链路输出至外接显示器，PL 不直接绘制界面。

界面支持本地图片/视频、原图与增强滑动对比、检测框开关、视频暂停/继续及任务记录。两个静态展示样例随包提供，可通过“开始处理”再次调用硬件。演示视频未随包附带，可打开用户自己的视频文件。原图/低照度/去雨雾/最终融合可分别选择；当前融合权重冻结为 `[10923,10923,10922]`，并非界面可调参数。

当前界面只显示状态、帧号及目标数量。结果写入 `ps/results/<任务标识>/`，包含 `job.json`、`frames.jsonl` 和图像，视频任务另存 `annotated.avi`。板端 SSD 检测器与离线检测评估所用 Faster R-CNN 不同，不能混用其 AP 结果。

## 实际输出核对

保持硬件服务运行，普通用户执行：

```sh
python3 scripts/smoke_golden.py --frames 1 --out validation_new/single.json
python3 scripts/smoke_golden.py --frames 6 --out validation_new/batch6.json
```

脚本分别调用低照度、去雨雾与融合分支，按驱动相同的 Q14→RGB8 舍入/饱和规则转换 Golden，逐字节核对全部输出，并保存实际 RGB 文件及 SHA256。每次使用新输出文件名，以保留前次证据。

硬件服务独占驱动，禁止同时运行其他 MMIO/PYNQ/benchmark 入口。发生超时或硬件错误时不自动重试、卸载驱动或释放潜在在途 DMA；保留现场并正常重启恢复。默认服务不自动重启。

## 从源码重新构建硬件

```sh
python3 scripts/build_hardware.py --stage prepare --out /absolute/ascii/path/new_build
python3 scripts/build_hardware.py --stage create --out /absolute/ascii/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage synth --out /absolute/ascii/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage implement --out /absolute/ascii/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage coverage --out /absolute/ascii/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage export --out /absolute/ascii/path/new_build --vivado /path/to/vivado
```

入口使用冻结的已实现 IP、BD seed 和全部 132 份 SmartConnect sim/synth wrapper，替换原开发电脑绝对路径及父构建依赖。Prepare 与各模型的生成 RTL 随包提供；对应 HLS 原始源码另放 `source_models` 和 `hardware/source/hls`。原交付中的历史构建脚本原样保留供追溯，默认使用上述可移植入口。

新布局布线不保证逐字节生成同一 bitstream，必须重新检查 setup/hold、DRC、CDC、路由、未约束时钟与板端 Golden，不能沿用旧镜像验收结论。本次整理验证了 prepare 阶段、源码恢复与主机回归，未重新执行耗时的综合/布局布线；交付镜像及其原始通过证据保持不变。

```sh
python3 scripts/run_host_tests.py --out validation_new/host
```

## 证据与边界

原硬件 `manifest.json` 的 `HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED` 是交付生成时状态，未作改写；后续板端通过记录另见 `validation/fifo_hardware/result.json`。该记录包含 43 项、1800 帧；逐帧 Golden/CRC 的覆盖范围以每个 case 的 `golden_check` 和原日志为准，不能把所有帧都称为完整 Golden 校验。

GUI 处理速度与已解码同图重复 benchmark 口径不同。`validation/board/fast_ui_validation.json` 记录了完整软件路径约 3.79 帧/s 的无检测视频测试；硬件 benchmark 不包含压缩解码、显示、保存与检测。包内不包含先前为作品表格临时编写的 CLAHE/Restormer 占位性能数据。

更多目录对应关系与实测统计见 `docs/ENGINEERING_INDEX.md`、`docs/VALIDATION.md`；第三方来源见 `docs/THIRD_PARTY.md`。
