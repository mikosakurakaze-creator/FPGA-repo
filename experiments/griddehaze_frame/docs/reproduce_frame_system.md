# 整网与五核系统复现

本页对应 2026-10-24 的 GridDehazeNet INT16 候选。A 原始材料、旧系统和所有历史失败均保留。每次使用新输出目录，禁止把历史 tile 版 `system02` 当作当前流水基线。

## 当前已验证入口

- `work/frame_native04/recovered_result.json`：8 组每组 320 节点的原生执行及重新哈希证据。
- `work/frame_csim01/result.json`：相同源码的实际 Vitis 48 位整网 C 仿真。
- `work/frame_synth01/result.json`：整网 HLS 综合和 IP，尚非整机布线结果。
- `work/frame_rtl05/result.json`：导出 RTL 4×4 冷暖全节点、延迟 B、字节 lane、错误 model、错误 Golden。
- `work/frame_rtl06/result.json`：最新周期预算测试台，同样全节点通过，并实际检查错误 model 不产生 DDR 流量。
- `work/frame_rtl_odd02/result.json`：加强后的同版 5×7 奇数尺寸全节点回归。
- `work/a_compare_nodes_4x4_warm01/comparison.json`、`work/a_compare_nodes_5x7_warm01/comparison.json`：A 原始比较器对实际暖态全部 320 份节点捕获的独立复核。
- `work/grid_system_audit02.json`：当前 seed 的 PS/旧接口保留、新控制/DDR 连接。
- `work/grid_sources_generated02.json`：实际生成的五核 524 份 Verilog/ROM 与冻结 IP 比对。

这些路径表示各自范围的证据；有界网表探针、preimpl XSA、历史系统的时序不能代替本版完整数值回归或最终 bit/XSA。

## 显式构建

本机普通 Python 为 `D:/Dev/Miniconda3/python.exe`，Vivado 为 `D:/vivado/2025.2/Vivado`。Vitis/Vivado 从打包宿主启动时，通过只影响子进程 DLL 查找的现有 `run_windows_desktop.py` 正常启动；不修改安全软件、不提升权限。

```powershell
$python = 'D:/Dev/Miniconda3/python.exe'
$launcher = 'C:/Users/wzh16/Desktop/github clone/weather_fpga_integration/tools/run_windows_desktop.py'
$project = 'C:/Users/wzh16/Desktop/competing/griddehaze_fpga'
$build = 'D:/weather_builds/grid_system_new'

Set-Location $project
& $python -B $launcher -- $python -B tools/build_grid_system.py --stage create --out $build
& $python -B tools/audit_grid_system.py --build $build --out work/grid_system_audit_new.json
& $python -B $launcher -- $python -B tools/build_grid_system.py --stage synth --out $build
```

默认 seed 是 `stream_system01`，构建前必须与旧 signed-fix 的实际回归身份匹配。安装目录不需要改动，A 原始源码、数值格式和参数也不需要重新训练或导出。

## 完整扩展验证（本轮不强制重跑）

在同一新构建目录中，只启动一次下面的串行工作流。若综合已经在运行，可加 `--wait-for-synth`；不重复启动综合。

```powershell
& $python -B $launcher -- $python -B tools/continue_grid_system.py `
  --build $build --wait-for-synth `
  --routed-out "$project/work/grid_routed_new" `
  --legacy-out "$project/work/legacy_routed_new" `
  --artifacts "$project/artifacts/griddehaze_k26_candidate_new"
```

流程依次核对实际综合读入的五核源码/ROM，执行带 signed-DSP 保护的布局布线，再执行当前系统的新去雾核冷暖功能回归及旧 weather 四帧回归。最后经过数值/身份/时序门禁生成并收集相同 bit/XSA。只要任何阶段失败，就保存错误并停止，不会跳过检查或自动上传。

状态见构建目录 `workflow.json` 和 `build.json`；Vivado 细节见 `synth_console.log`、`impl_console.log`，仿真见各新输出目录 `simulation.log`。`pass_result=false` 且没有结束错误可能表示仍在执行；不能仅按文件存在宣称通过。

门级整网仿真可能耗时数小时，默认单次允许 24 小时。它不改变 FPGA 频率或代表板端处理速度。`--probe-cycles` 只做有限周期总线诊断，报告明确不是数值 PASS，不能用于交付门禁。

较大的导出 RTL 用例可显式设置 watchdog，例如：

```powershell
& $python -B $launcher -- $python -B tools/frame_rtl_trial.py `
  --synth work/frame_synth01 --case random `
  --max-frame-cycles 500000000 --out work/frame_rtl_33x47_new
```

该上限仅用于避免仿真挂死；默认单帧 200,000,000 周期，总预算为两帧加 1,000,000 周期。报告中的 `frame_cycle_budget`、`total_cycle_budget` 不代表已执行或测得相应周期。

## 板端边界

B 交付本地 FPGA 候选及接口文档，不执行 Git、板端配置、Linux 驱动、设备树部署或 HDMI。上板后仍需软件侧按实际接口申请互不重叠的低 DDR，校验冻结参数并完成一致性处理。当前共享复位、无独立 AXI 中止/排空、无 AXI 错误诊断等限制见 `frame_interface.md`，不得报告为已实现独立故障恢复。

## 本轮必要回归的快速入口

本轮按用户要求复用已核实的 33×47 导出 RTL 双帧和已有综合/实现结果。发布文件校验从仓库根运行 `experiments/griddehaze_frame/tools/verify_board_release.py --release board/releases/k26_weather_griddehaze_reduced_20261024`。

新核布线后有限数值样本可复用已编译的真实全系统快照，无需重新 xelab。下面命令从仓库根运行，`--out` 必须选择新的目录；这不是完整整网回归，也不生成 bit/XSA：

```powershell
python -B tools/run_windows_desktop.py -- python -B experiments/griddehaze_frame/tools/routed_sample_trial.py `
  --prepared experiments/griddehaze_frame/work/frame_routed_releasefix01 `
  --netlist D:/weather_builds/grid_system02/system_routed_funcsim.v `
  --golden experiments/griddehaze_frame/a_candidate/golden/size_4x4 `
  --out experiments/griddehaze_frame/work/frame_routed_sample_new
```

工具保留实际 routed 逻辑和父层连接，只读图索引和仿真 DDR，采集节点 1..4 与 Golden 比较。成功必须有 `sample_result.json` 中 `status=pass`；仅有总线活动日志不算数值通过。完整整网 gate-level 冷暖帧仍可另行执行，但不作为本轮快速交付的隐含前提。实际范围详见 `release_review_20261024.md`。
