# 本地候选的复现入口

最终候选目录有 `ip_repo/{cnn,bilinear,curve,weather}`、`system_seed.bd`、`recipe/` 和 `verification/`。原始 `system_recreate.tcl` 保留构建路径作为出处；跨机器重建使用下面的显式输入脚本。

## 从 IP 重建硬件

在候选目录中执行，输出路径须是新的目录。工具版本为 Vivado/Vitis 2025.2，器件为 `xck26-sfvc784-2LV-c`，KV260 SOM board part 1.4。

```powershell
$weatherPython = 'D:/Dev/Miniconda3/python.exe'
$weatherVivado = 'D:/vivado/2025.2/Vivado'
$weatherBuild = 'D:/weather_builds/reproduce01'
& $weatherPython recipe/tools/run_windows_desktop.py -- `
  $weatherPython recipe/tools/build_system.py `
  --output $weatherBuild --stage create --vivado $weatherVivado `
  --seed system_seed.bd --cnn ip_repo/cnn --bilinear ip_repo/bilinear `
  --curve ip_repo/curve --weather ip_repo/weather
```

确认 `create` 返回成功后，依次运行相同入口，将 `--stage` 改成 `synth`、`impl`、`package`；保留 `--output` 和 `--vivado`，后续阶段不再传 IP/seed。每阶段都需要前一阶段成功。脚本核对复制后的输入哈希，不允许在中途静默替换 IP。

`impl` 保存 post-route timing、utilization、route status、DRC 和 checkpoint，并检查最差 setup/hold。`package` 再核对时序后生成 bit 与含 bit 的 XSA。最终收集脚本还检查 pulse width、RTL/ROM 身份、XSA 内嵌 bit 与外部 bit 相等。报告里的综合估算、RTL 周期、routed 时序和板测是不同证据，不能混用。

## 重新核查天气数值与 RTL

`recipe/experiments/onchip_frame/scripts/verify_host.py` 是主机逐层/整帧入口；A fixture 子集为 `verification/a_delivery/weather_restore_lab/a_compute`。`verification/a_delivery/DELIVERY_MANIFEST.json` 保留原 A 清单，但目录只包含本测试使用的部分数据，不是完整 A 交付。

先用新的 output 执行 host `--full-frame`，再将新生成的 `verification.json` 传给 `recipe/experiments/onchip_frame/scripts/run_hls.py --host-report ... --through package`。后者通过 `recipe/tools/run_windows_desktop.py` 启动，参数样例见实验 README。host 与 HLS 会核对当前源码哈希。

对该 HLS 输出分别运行 `recipe/tools/run_sequence_cosim.py` 和 `recipe/tools/run_rtl_memory_test.py`。前者使用 vendor co-sim；后者直接模拟相同的 IP RTL/ROM、独立 AXI-Lite 和有停顿 DDR，并生成/检查自己的 A reference Golden 和负对照。所有 output 都使用新目录。

PS 控制 host 测试入口为 `recipe/deployment/tests/verify_driver.py`。A53 BSP/ELF 构建另见 [板端联调](board_bringup.md)；本轮未构建成功 ELF，未连接真板。

## 保留证据

`manifest.json` 不包含自身；它记录候选中其余文件的大小与 SHA-256。复现会产生新的路径、时间戳和元数据，因此无需期待新 bit 的 SHA 与历史 bit 一定相同；应重新保留自己的构建日志、接口核查、时序结果及最终文件身份。没有自动执行任何 Git 操作。
