# Vitis 在 Windows 下的启动故障诊断与修复

日期：2026-10-20。范围：从本工作目录启动已安装的 Vitis 2025.2 HLS 命令行工具。本文保留启动修复阶段的证据；后续 HLS/RTL 和系统实现状态见 [当前流水版报告](stream_revision_20261020.md)。

## 已确认的原因

Vitis 安装存在。失败的 `vitis-run.exe --version` 在处理任何项目源码前以 Windows 状态 `0xC0000135` 退出。最初批处理预检日志为空，包装脚本返回零不能证明工具成功启动。

该进程继承了 Windows 包身份 `OpenAI.Codex_26.1013.4894.0_x64__2p2nqsd0c76g0`。仅针对该进程的加载器跟踪记录为：

```text
Packaged DLL search path computed.
Package Dirs: C:\Program Files\WindowsApps\OpenAI.Codex_26.1013.4894.0_x64__2p2nqsd0c76g0;
DllPath: D:\vivado\2025.2\Vitis\bin\unwrapped\win64.o;C:\WINDOWS\SYSTEM32
Unable to load DLL: "xv_xocc_common.dll" ... Status: 0xc0000135
Unable to load DLL: "xv_pic_compiler.dll" ... Status: 0xc0000135
```

这些 DLL 实际存在于 `D:/vivado/2025.2/Vitis/lib/win64.o`，但记录的搜索路径没有包含该 PATH 目录。单独加入 PATH、执行 `settings64.bat` 或移除 `__COMPAT_LAYER`，均未解决该进程树的启动故障。另一项诊断在显式指定 DLL 目录后成功加载主要 Vitis DLL 和已安装的 VC++ 运行库。

证据表明，测试进程树中存在继承的包身份影响 DLL 搜索的问题；它不能证明安装损坏、许可证缺失或 CNN/HLS 源码错误。其他日志下的 Vitis 启动失败可能有不同原因。

## 项目内的桌面启动器

使用 [run_windows_desktop.py](../tools/run_windows_desktop.py) 启动现有 HLS 运行脚本。Windows 下，启动器检测父进程是否带包身份，并对新子进程树设置 `PROC_THREAD_ATTRIBUTE_DESKTOP_APP_POLICY` 和 `PROCESS_CREATION_DESKTOP_APP_BREAKAWAY_ENABLE_PROCESS_TREE`。Windows 仍负责判断调用者是否有权使用该策略。标准输入/输出/错误通过显式可继承句柄列表转发；普通桌面父进程或非 Windows 环境则正常创建子进程。

该操作仅改变新进程树的应用身份，不请求管理员权限，也不修改全局环境变量、注册表、Vitis 安装文件、计算源码或冻结权重。命令执行不隐式经过 shell；需要批处理时应显式调用 `cmd.exe`。

在 `C:/Users/wzh16/Desktop/competing` 执行：

```powershell
$weatherPython = 'D:/Dev/Miniconda3/python.exe'
& $weatherPython weather_fpga_integration/tools/run_windows_desktop.py -- `
  $weatherPython weather_fpga_integration/experiments/onchip_frame/scripts/run_hls.py `
  --delivery 'weather A/weather_A_C8_delivery/weather_restore_lab/a_compute' `
  --host-report weather_fpga_integration/work/onchip_host_20261020_02/verification.json `
  --output weather_fpga_integration/work/onchip_hls_desktop_new `
  --vitis-bin 'D:/vivado/2025.2/Vitis/bin' `
  --settings 'D:/vivado/2025.2/Vitis/settings64.bat' --through preflight
```

每次使用新的输出目录，HLS 运行脚本保留旧运行。继续保留源码/主机报告哈希检查。后续厂商阶段使用同一启动前缀和已有 `--through` 选择器，需分别实际执行和验证。

## 手动替代方法

从 Windows 开始菜单或 Win+R 独立于 Codex 打开 `cmd.exe`，然后执行：

```bat
call "D:\vivado\2025.2\Vitis\settings64.bat"
call "D:\vivado\2025.2\Vitis\bin\vitis-run.bat" --version
```

独立终端方案依据已确认的进程继承问题推导，本轮未单独操作验证；上面的项目内启动器则已实际执行通过。应以版本横幅和通过的预检报告判断工具是否成功启动。

## 实际执行的验证

- 启动器子进程及嵌套 Python 子进程返回 `15700`（`APPMODEL_ERROR_NO_PACKAGE`）。含空格/Unicode 的参数、环境值、工作目录、标准输出和错误输出均保持。
- 使用故意返回 7 的子进程检查退出码传递；重定向标准输入保持，普通桌面子进程再次调用启动器时正常走常规创建路径。
- 经启动器执行 `vitis-run.bat --version` 和 `v++.bat --version` 均返回零，并输出非空 2025.2 厂商版本横幅。
- 原 HLS 运行脚本在源码/fixture 检查不变的条件下，通过实际 Vitis `2025.2` 版本预检，退出码为零，横幅非空。
- 通过报告：[run.json](../work/onchip_hls_20261020_desktop_preflight/run.json)；版本输出：[preflight.log](../work/onchip_hls_20261020_desktop_preflight/preflight.log)。
- 最初失败仍保存在 [首次运行](../work/onchip_hls_20261020_01/run.json)。进程内加载器诊断保留于 `work/vitis_diagnostics_20261020/`，未启用全局加载器跟踪。

在此次启动修复阶段，没有执行厂商 CSim、综合、RTL 联合仿真、IP 导出、Vivado 实现或板测。启动通过不能证明这些阶段通过。计算源码/脚本哈希与已有主机通过报告仍一致，因此本次启动器和文档修改没有重复数值测试。后续已完成的流程以当前报告为准。

当时通过 OpenAI Docs 技能查阅了 [OpenAI 官方 Windows 应用文档](https://developers.openai.com/codex/app/windows)。该文档没有描述此项 Vitis/DLL 故障；上述诊断和成功修复依据本地 Windows 加载器和执行证据。

## 文件与当时的审核状态

新增 `tools/run_windows_desktop.py` 和本文。更新根 `README.md`、`experiments/onchip_frame/README.md`、`docs/open_items.md`、`docs/b_progress_report.md`，记录启动阻塞已解除及可复现命令。诊断脚本/日志和预检输出仍在被忽略的 `work/` 下。

启动修复当时，独立工作目录不是 Git 克隆，没有分支；相邻 `fpga clone` 处于 `main...origin/main`，原有修改/未跟踪文件未动。本修复没有暂存、提交、推送、切换分支或修改安装/全局配置。此段为历史记录，当前复制目录的绑定状态见 [Git 绑定记录](git_binding_20261021.md)。当时建议的提交说明为：

```text
fix(weather): launch Vitis with desktop DLL search from packaged hosts
```
