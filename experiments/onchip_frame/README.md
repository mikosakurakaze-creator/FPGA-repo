# 片上整帧计算核实验

实验 ABI v2：整帧 DDR 输入输出，片上复用 C8 tile engine。主机逐层/整帧验证、两任务 Vitis CSim/综合/8×8 RTL/IP 导出均通过，见 `work/frame04/run.json`。五帧 vendor co-sim 和七次有停顿独立 AXI RTL 回归也通过。旧候选的窄行写回卡死已由行缓存修正，见 ../../docs/ddr_writeback_deadlock.md。最终 implementation 状态见系统集成报告，尚无真板验证。当前根目录 `ip_repo/` 仍为 A 组原始 v1 IP；新核包在本次构建目录。

`src/weather_frame.cpp/.h` 是新原型。`weather_kernel_reference.cpp`、`weather_kernel.h` 和两个 `params_*.h` 来自 A 交付，SHA-256 固定校验。原始交付目录只读。`tests/test_weather_frame.cpp` 是参考比较/trace/边界测试；`hls/tb_weather_frame.cpp` 是独立的 Golden testbench，不链接参考核。

接口和验收约束见 [v2 合同](../../docs/weather_frame_v2_contract.md)，优化预算见 [性能说明](../../docs/performance_optimization.md)。

## 复现主机验证

以下命令从 `C:/Users/wzh16/Desktop/competing` 执行。每次 output 使用新的目录名，脚本不会覆盖旧运行。

```powershell
$weatherPython = 'D:/Dev/Miniconda3/python.exe'
$weatherCxx = 'D:/vivado/2025.2/tps/mingw/8.3.0/win64.o/nt/bin/g++.exe'
& $weatherPython weather_fpga_integration/experiments/onchip_frame/scripts/verify_host.py `
  --cxx $weatherCxx `
  --delivery 'weather A/weather_A_C8_delivery/weather_restore_lab/a_compute' `
  --output weather_fpga_integration/work/onchip_host_new --full-frame
& $weatherPython weather_fpga_integration/deployment/tests/verify_driver.py `
  --cxx $weatherCxx --output weather_fpga_integration/work/driver_host_new
```

无需 NumPy。脚本记录源文件、Golden、可执行程序和日志哈希。主机 HLS TB 同时用 `__SYNTHESIS__` 路径编译，覆盖两任务 96×96 和 8×8。这依然是普通 g++ 运行，不能写成 Vitis CSim 或 RTL co-sim。

## 准备或运行 HLS

```powershell
& $weatherPython weather_fpga_integration/tools/run_windows_desktop.py -- `
  $weatherPython weather_fpga_integration/experiments/onchip_frame/scripts/run_hls.py `
  --delivery 'weather A/weather_A_C8_delivery/weather_restore_lab/a_compute' `
  --host-report weather_fpga_integration/work/onchip_host_new/verification.json `
  --output weather_fpga_integration/work/onchip_hls_new `
  --vitis-bin 'D:/vivado/2025.2/Vitis/bin' `
  --settings 'D:/vivado/2025.2/Vitis/settings64.bat' --through preflight
```

`--through prepare` 仅准备源码、manifest 校验过的 96×96/8×8 fixtures 和 10 ns/K26 配置，不要求 Vitis。输出路径须全英文 ASCII、无空格；脚本将数据复制到该目录，避免原交付路径中的空格影响工具。

`--through` 依次可选 `preflight/csim/synth/cosim/package`，会执行截至目标阶段的全部步骤。要完整运行，使用新 output 及 `--through package`。每阶段日志及资源/IP 文件保存在该 run；不支持原地覆盖或跳过失败步骤。通过 `--task` 可选一个任务，默认两任务；两份构建源相同、均包含两模型，只是 Golden 参数不同。

开始前要求 passing host report 与当前全部实验源码/脚本哈希一致，改过源码须重跑主机验证。工具返回 0 不足以通过：版本阶段需真实非空 banner；CSim/RTL 需 PASS 与实际输出字节；综合需正确 top 的资源 XML；导出需含 `component.xml` 的 ZIP。

本机首次 `--version` 为空的故障已定位并修复：从 Codex 继承的 Windows 包身份使 Vitis 未按普通桌面方式搜索 PATH 中的 DLL。上面的启动器只为新工具进程树使用桌面启动策略。`work/frame04/run.json` 已实际执行并通过 `package` 全阶段，版本为 2025.2；原失败报告仍保留。详见 [启动诊断及修复](../../docs/vitis_windows_startup.md) 和 [系统集成记录](../../docs/system_integration_20261020.md)。
