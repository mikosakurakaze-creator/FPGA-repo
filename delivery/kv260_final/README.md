# KV260 工程文件与源码

版本：2026-11-03。PL Build ID：`c6496c6dc89aa54c4500`。

## 工程组成

| 内容 | 目录 |
|---|---|
| RTL、HLS、IP与集成工程 | `hardware/source`、`hardware/ip`、`source_models` |
| PS应用与Linux驱动 | `ps`、`ps/driver` |
| 仿真与功能验证 | `hardware/source/tests`、`hardware/evidence`、`validation/host` |
| 综合、实现、资源及时序报告 | `hardware/reports`、`hardware/manifest.json`、`hardware/clock_reset.md` |
| 上板镜像及参考数据 | `hardware/joint_system.*`、`hardware/golden`、`hardware/model` |
| 实际输出与参考比对 | `validation/package_board` |
| 构建与运行脚本 | `scripts`、`ps/launch.sh` |
| 离线运行依赖 | `runtime_assets` |

## 运行环境

KV260，Ubuntu 22.04 aarch64，Python 3.10；内核 `5.15.0-1027-xilinx-zynqmp`，安装对应内核头文件。

系统软件包：`build-essential device-tree-compiler python3-pip python3-gi python3-gi-cairo python3-numpy python3-pil gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good`。

硬件工具：Vivado 2025.2及KV260器件/板卡支持；HLS源码开发使用Vitis HLS 2025.2。

## 上板运行

将完整目录复制到板端，进入该目录执行：

```sh
python3 scripts/verify_package.py
sh scripts/install_runtime.sh
sh scripts/build_driver.sh
python3 scripts/load_board.py
```

在正常重启后的官方base镜像状态加载工程并启动服务：

```sh
sudo python3 scripts/load_board.py --execute
sudo sh scripts/start_service.sh
```

另开普通用户终端，在板端桌面会话中启动界面：

```sh
sh ps/launch.sh
```

SSH启动图形界面时使用实际桌面环境变量，例如 `DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority`。

界面支持图片与视频输入、处理通路选择、检测阈值设置、原图与增强滑动对比、检测框显示、视频暂停/继续及结果保存。结果目录为 `ps/results`。融合权重为 `[10923,10923,10922]`。

## 功能验证

主机回归覆盖控制器执行顺序、帧号关联、缓冲复用和异常处理：

```sh
python3 scripts/run_host_tests.py --out validation_new/host
```

保持硬件服务运行，执行三分支输出比对：

```sh
python3 scripts/smoke_golden.py --frames 1 --out validation_new/single.json
python3 scripts/smoke_golden.py --frames 6 --out validation_new/batch6.json
```

脚本将低照度、去雨雾、融合三分支的实际RGB输出与参考Q14数据按相同转换规则逐字节比较。随包 `validation/package_board/single.json` 及三个 `.rgb` 文件给出单帧功能验证结果，三分支不匹配字节数均为0。仿真结果见 `hardware/evidence`，主机回归结果见 `validation/host`。

硬件服务独占驱动；出现硬件错误时停止提交任务，正常重启后重新加载工程。

## 硬件构建

下列入口使用随包IP、BD重建脚本与SmartConnect源码，输出至新建的ASCII路径：

```sh
python3 scripts/build_hardware.py --stage prepare --out /absolute/path/new_build
python3 scripts/build_hardware.py --stage create --out /absolute/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage synth --out /absolute/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage implement --out /absolute/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage coverage --out /absolute/path/new_build --vivado /path/to/vivado
python3 scripts/build_hardware.py --stage export --out /absolute/path/new_build --vivado /path/to/vivado
```

构建后检查生成的资源、时序、DRC、CDC与路由报告，再运行输出比对。地址接口见 `hardware/register_map.*`、`hardware/address_map.json`，时钟复位见 `hardware/clock_reset.md`。第三方依赖说明见 `docs/THIRD_PARTY.md`。
