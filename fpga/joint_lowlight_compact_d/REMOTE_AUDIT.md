# 联合镜像：远端依赖审阅

## 补交更新（2026-10-29）

用户更新后的本地队友基线为 `3c9e41a35fc08d44ba0552ce6916a421f98f94d7`，新增正式 `delivery/lowlight_frozen_ip_20261028.zip`。已按任务 2 冻结清单逐一校验全部 406 个文件，全部匹配；ZIP SHA256=`b5b69f1d3d1e3f69e9f825be5453b086c58b4d863a3a9889693a247101b9c2cf`。因此原缺低照度 IP 阻塞已解除。本轮从该锁定 Git 对象只读取文件，不修改队友分支。新证据见 `evidence/received_dependency_audit.json`。

以下记录保留首次远端审阅时点，表内 `23b56b5` 与缺项结论是更新前的历史事实，不代表补交后的状态。没有将这份旧查询重新标成当前远端查询。

## 首次远端审阅（更新前）

核查日期：2026-10-29（Asia/Shanghai）。仅执行只读 Git/HTTPS 查询；未 fetch、切分支、暂存、提交、推送或合并。

`git ls-remote --heads --tags origin` 已确认远端八个分支的 tip 与现有本地远端跟踪对象一致；因此以下树检查针对的就是本次查询时的远端版本。GitHub REST `releases?per_page=100`、`tags?per_page=100` 均为空；`actions/artifacts?per_page=100` 返回 total_count=0。

| 远端分支 | tip | 与本任务的关系 |
| --- | --- | --- |
| main | a389b52 | V1.2 稳定低照度源码、接口与历史报告；无完整冻结 IP payload |
| codex/curve-fp32-baseline | 23b56b5 | 任务 1–3 源码、合同、验证结果、四核综合报告；无低照度/适配 IP ZIP、联合 checkpoint 或工程输出 |
| feat/software | 9ef5faf | Compact D 数值 A、INT16 Golden 与软件交付；本次修改工作树 |
| weather_fpga_integration | d8880cc | 完整 Compact D IP ZIP、单独 bit/XSA/HWH、driver、Golden 和报告 |
| feat/zero-dce-quantization | 11584ff | V1.1 低照度量化/三模块历史版本，不能替代 V1.2 write-credit |
| feat/v1-model-baseline | 883064d | 原始模型软件基线 |
| feat/v1-model-validation | 2ae9a74 | 原始模型软件验证 |
| feat/v1-project-scaffold | fc019e7 | 项目骨架 |

## 能取回与不能取回

Compact D 可直接按冻结 Git 对象读取，不需要切换或合并队友分支：

`d8880cce7241628f5472a36802b1791e85935e27:compact_d_fpga/board/k26_compact_d_20261025/compact_d_ip.zip`

该 ZIP 的合同 SHA256 是 `7d276942544f3785bde9267484da6d08bbae819cd46b8bb8e7214ea8a5603bc4`。前三项的实现和文本证据也已在远端。

所有远端分支的当前树中均未发现正式 CNN write-credit、Bilinear、Curve、joint_rgb8_prepare、joint_q14_copy 的完整 IP ZIP/RTL payload。`fpga/docs/kv260_v12_large_artifacts.md` 明确记录：低照度大文件及可选冻结 HLS/IP 导出仅保留本地、未上传。清单与哈希不能还原缺少的文件。

当前机器上找到了 `D:/weather_builds/lowlight01/` 的旧候选。后续逐文件核查证明：CNN 有 303 个、Bilinear 有 53 个、Curve 有 31 个文件与冻结清单完全相同，其中全部 HDL/ROM/driver/约束/xgui 均匹配。差异集中于 component.xml、revision、运行/封装文件，CNN 另缺三份封装审计 manifest；因此可以作为后续明确重新封装/验收的源材料，但其包身份不等于任务 1 的冻结身份。没有将这些候选冒充原正式包；机器可读结果见 `evidence/dependency_audit.json`。

## 最小缺项

优先补齐 `E:/HLS/joint_lowlight_compact_d_20261028/ip/{cnn,bilinear,curve}/` 的完整副本，以及 frozen_inputs.json；可直接用任务 2 的 resource_frozen_inputs.json 逐文件验 SHA256。另一个可接受来源是原 `phase4g/ip_primary_05/` 和 `phase4g/integration_01/stable_ip_repo/{bilinear,curve}/`。

适配器有完整源码，可从锁定源码重新综合导出并重新核 ABI；原适配 ZIP 或整个 adapters/ 目录有助于保持既有包身份。正式低照度 base export 的缺失使现有 build_ip.py 的锁定重建入口也无法直接运行。

在这些依赖恢复前，不能宣称完成最终联合综合、布局布线、时序验收或交付新的可上板 bit/XSA/HWH。
