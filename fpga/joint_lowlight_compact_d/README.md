# KV260 低照度 + Compact D：任务 1–3 审阅入口

日期：2026-10-28。本次负责接口冻结、四核联合资源检查和编码适配；融合核/最终系统集成/可上板硬件包对应任务 4–6，交给后续负责人。板端加载、数值与实测耗时不在本轮范围。

## 文件与修改原因

| 文件 / 目录 | 新增内容与原因 |
| --- | --- |
| [接口合同](docs/interface_contract.md) | 锁定正式低照度 write-credit 与 Compact D 版本、编码、缓冲、Golden、时钟/复位、寄存器，以及三路融合数值和完成同步规则，避免误用旧候选 |
| [适配实现](hls/joint_adapters.cpp)、[声明](hls/joint_adapters.hpp) | RGB8→I/D/CNN 输入；L/D→统一 Q14 原码复制，保证同帧来源和正确量化顺序 |
| [适配 testbench](hls/test_adapters.cpp) | 完整帧逐元素 Golden、非法 cookie 和输出 guard 检查 |
| [适配验证说明](docs/adapters.md)、`evidence/` | 实际执行范围、结果、导出 ABI 和输入/输出/包哈希，区分 CSim 与 RTL/板测 |
| `scripts/validate_adapters.py`、`scripts/collect_adapter_evidence.py` | 独立有理数 Golden、Host/CSim、HLS 综合导出及实际 driver 校验，支持外部目录重建 |
| `scripts/resource_{prepare.py,build.tcl,run.ps1,collect.py}`、`reports/resource_*` | 复制冻结 IP/工程到隔离目录，真实连接四核并综合，收集实际资源、时钟和保留实例证据 |

本次仅新增本目录文件，未修改旧模型/IP/权重、队友分支或既有运行输出。

## 关键差异

- 原图入口明确定为固定 1272×720 RGB8 HWC，生成 RGB/NCHW/INT16 Q14；上游解码/其他尺寸变换须在入口前完成。
- D 输入直接算 `RHAZ((2*p-255)*16384/255)`，I 独立算 `RHAZ(p*16384/255)`，不能使用有二次量化偏差的 `2*I-16384`。
- CNN 输入遵循既有 full-Q14 四中心点平均、RNE；L/D 保留全部 Q14 原码，包括大于 1 的值。
- 融合权重采用无符号 16 位存储、15 位小数，各在 `[0,32768]` 且总和 32768；一次 signed64 累加后 RNE，再裁剪至 `[0,16384]`。本轮冻结合同，不实现任务 4。
- 联合资源检查采用正式 CNN write-credit RTL；保留低照度 100MHz 和 D 200MHz，通过跨域 SmartConnect 共享 DDR；检查范围为四核及其互连。

## 已执行与未执行

适配 Host 和 Vitis HLS CSim 均对六个张量、每轮 13,756,680 个原码逐元素比较，零差异。全部 256 个 RGB8 值与 65,536 个 signed INT16 值均覆盖。两个适配 top 的 HLS 综合/IP 导出通过，实际 driver offset/width 校验通过；证据见 [adapter_evidence.json](evidence/adapter_evidence.json)。

四核完整联合网表实际综合资源：LUT **72,262/117,120（61.70%）**、DSP **904/1,248（72.44%）**、BRAM **72/144 tiles（50.00%）**、URAM **58/64（90.63%）**、FF **83,644/234,240（35.71%）**。最紧资源为 URAM，仅余 6 块；该结果不含适配/融合。完整结果以 [资源报告](docs/resources.md) 和 [resource_summary.json](reports/resource_summary.json) 为准。

四核均保留且资源非零，blackbox=0。综合 setup WNS 为 +0.672 ns，但 hold WHS 为 -0.093 ns，另有 8 个 no_clock 检查项，**尚未时序收敛**；后续系统集成和布局布线须处理。本轮资源检查完成不表示可上板硬件包已完成。

未执行新适配 RTL cosim、新的 1272 宽 D 全模型 Golden/联合 RTL、任务 4 融合、最终任务 5 集成、布局布线、新 bitstream/XSA/HWH 或任何板端操作。旧 1280 宽 D Golden 的按行重排只用于 raw-copy 测试，不冒充新 D 推理结果。四核综合结果不包含适配/融合及其新增互连，不能作为最终系统资源或时序验收。

外部 build 根目录为 `E:/HLS/joint_lowlight_compact_d_20261028/`，其中保存真实工程、报告、综合 checkpoint、适配 ZIP 和完整原码/日志。重建入口见 [适配说明](docs/adapters.md) 与资源报告；大文件不自动加入 Git。

## Git 审核记录

本轮开始及修改后的分支为 `codex/curve-fp32-baseline`，HEAD=`cfa4e3d103c237ebdbd4591d357c343e0a146ed2`。保留原有未跟踪工作；本轮新增文件均在 `fpga/joint_lowlight_compact_d/`，未暂存，未执行 add/commit/push、切分支、合并或 PR 操作。已有 tracked/staged 文件未被本轮改动。

建议 Commit Message：`feat(fpga): freeze joint lowlight Compact D interfaces and add Q14 adapters`

本目录完成后供用户审核；提交、推送及后续 Git 操作需获得当前这批改动的明确授权。
