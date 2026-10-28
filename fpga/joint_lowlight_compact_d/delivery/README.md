# 原正式冻结低照度三核 IP 完整包

2026-10-29 补交。该目录提供真实 IP payload，不是报告替代件，也没有重新 export、save_core 或改变封装身份。

下载本目录的 `lowlight_frozen_ip_20261028.zip` 和同名 `.json`。ZIP 约 1.63 MiB，解压结构为：

```text
ip/
  cnn/       # 308 files, revision 2114810448 (write-credit)
  bilinear/  # 60 files, revision 2114800369
  curve/     # 38 files, revision 2114799122
```

所有 **406 个文件**直接来自 `E:/HLS/joint_lowlight_compact_d_20261028/ip/{cnn,bilinear,curve}/`，逐字节匹配此前已提交的 `../reports/resource_frozen_inputs.json`。包含各 IP 的 `component.xml`、完整 HDL/ROM 数据、drivers、constraints、xgui、doc/misc 等原目录内容；CNN 还完整保留 `source_manifest.json`、`build_manifest.json`、`abi_fileset_audit.json`。原目录中的 VHDL 归档也保留，不修改 component 中实际启用的 fileset。

| IP 的 component.xml | SHA256 |
| --- | --- |
| CNN | `7e046bd557997e8a8b55b466ee9a76b8c3c321f1435df2879a8bf92a45f54ecd` |
| Bilinear | `1c7ab9696185d78baad702d28d8c7c8ba1671b79c4dd5665f306a57d591b2597` |
| Curve | `72a3f2345b988f321fd3f0f20e4a8a8fc0996fcb00e8c001fc157e3b3e88a518` |

JSON 记录 ZIP SHA256/大小及全部文件 SHA256/大小。ZIP 内路径相对 `ip/`，原始文件内容、封装 revision 和审计身份不变；容器时间固定，不表示重新生成 IP 的时间。使用 ZIP 是为完整携带可能被 Git ignore 的 ROM/数据文件并避免换行转换。

## 校验与使用

克隆本分支后，在仓库根目录执行（仅需 Python 标准库）：

```powershell
python fpga/joint_lowlight_compact_d/scripts/frozen_lowlight_bundle.py verify --extract-to E:/HLS/lowlight_frozen_received
```

目标目录必须不存在。脚本先验证 ZIP 与全部 406 个文件，再解压并重核实际落盘文件，成功输出 `FROZEN_LOWLIGHT_PASS files=406`。不依赖原发布者的本地 E 盘目录。

在隔离 Vivado 工程中将三个解压目录分别作为 IP repository：

```tcl
set received_root {E:/HLS/lowlight_frozen_received/ip}
set_property ip_repo_paths [list $received_root/cnn $received_root/bilinear $received_root/curve] [current_project]
update_ip_catalog -rebuild
```

不要同时引入同 VLNV 的旧身份包或再次保存封装；确认版本及 component hash 后使用。该示例只设置三核仓库，联合工程使用 Compact D 时还需保留 D 的正式仓库。

## 本次验证与边界

已执行：对照此前冻结清单精确检查文件集合、逐项 SHA256、ZIP 完整读取、在全新目录解压并对所有实际落盘文件重核，均通过。未重新封装、综合、布局布线或上板；此前联合综合结论保持原边界。

本次新增 ZIP、manifest、本说明及校验/打包脚本，并增加主入口链接；目的仅为补齐接收方缺失的原 IP 完整包。没有修改原 IP，也不包含 Compact D、数据集、模型推理输出、bitstream 或工作区其他未跟踪文件。

提交说明：`fix(fpga): deliver exact frozen lowlight IP payloads`。补交沿用 `codex/curve-fp32-baseline`，不切换分支或修改 main/队友分支；上传范围限于本次补交文件。
