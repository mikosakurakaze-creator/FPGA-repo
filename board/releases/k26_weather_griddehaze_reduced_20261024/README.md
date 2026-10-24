# K26 五核硬件候选与必要回归

本目录包含旧 CNN、Bilinear、Curve、Weather 和新增 GridDehazeNet。bit/XSA 仍来自原同一次 Vivado 2025.2 实现；本轮修正发布文件一致性并补充必要数值证据，没有重新实现电路。

## 当前完成情况

- 综合、布局布线和 bit/XSA 导出已完成。100 MHz routed timing：WNS +0.729 ns、WHS +0.010 ns、WPWS +3.500 ns；191,089/191,089 nets routed。DRC 无 Error/Critical Warning，但存在普通 Warning。
- 33×47 跨分块冷暖双帧：复核既有实际导出 RTL 仿真，两帧各 320 节点逐元素一致；冷暖原始最终输出再次逐字节核对通过。95 个 RTL/ROM 文件与本次实现所用 IP 相同。见 `evidence/cross_tile_review.json`。
- 旧 Weather 核：本轮实际 routed 五核系统路径的 8×8 连续四帧 task=0、0、1、0，全部 Golden mismatch=0。见 `evidence/legacy_review.json`。CNN/Bilinear/Curve 保持空闲，未逐核重新验证。
- 新 GridDehazeNet 布线后：4×4 代表性节点 1、2、3、4 已完成原始输出比较：两次卷积、ReLU、拼接，共 1,280 个标量，全部与 A 组 Golden 零差异。见 `evidence/new_core_sample.json`。本轮不强制完整布线后整网冷暖帧。
- 同版 A 组 INT16 参数、三种尺寸 layout 和 33×47 核查向量已放入本目录，供软件侧适配。

## 本轮发布修正

原 `griddehaze_system.hwh` 取自 XSA 的 SmartConnect 子设计，现纠正为同一 XSA 内的完整 **`system.hwh`**。bit/XSA 本体没有变化。manifest 精确记录 XSA 成员名，校验工具直接比较外部 bit/HWH 与相应内嵌成员。

发布目录由 `.gitattributes` 的 `-text -whitespace` 保护。新说明/清单使用 UTF-8 无 BOM、LF；冻结 A 组 `scale_config.json` 和原始仿真证据保留原字节及既有哈希。不要自行转换这些冻结文件的换行。

从仓库根目录核验全部发布字节、模型身份和 XSA 对应关系：

```powershell
python -B experiments/griddehaze_frame/tools/verify_board_release.py --release board/releases/k26_weather_griddehaze_reduced_20261024
```

`SHA256SUMS` 覆盖目录中的所有 payload 文件，不包含自身。`--refresh-checksums` 只在明确修改发布内容后使用，普通下载核验不要使用该选项。

## 交给软件侧

- `griddehaze_system.bit`、`griddehaze_system.xsa`、`griddehaze_system.hwh`：同版硬件和完整系统元数据。
- `model_int16/`：原始 `parameters.bin`/manifest/graph/scales，及 33×47、675×1280、720×1280 layout；容量和使用说明见该目录 README。没有另做压缩交付包。
- `frame_interface.md`、`xgriddehaze_frame_top_hw.h`：实际 AXI/DDR 和寄存器合同。新核控制基址 0xA0040000；feature 走 HP3，parameter/layout 走 HP0。
- `validation_33x47/`：新核 RGB/NCHW、小端 signed INT16 输入 F14、预期输出 F13，以及实际导出 RTL 冷暖输出。新核不能套用旧 Weather 的全 Q14 合同。
- `validation_legacy_8x8/`：旧 Weather 四帧 task=0、0、1、0 的输入/预期输出，仅用于旧核。
- `evidence/`：原始日志、实际执行 SV、原始输出与精简数值审核记录；实现报告仍保留在发布根目录。

bit SHA-256：`07f23b4d67f60270d3c35725df32289468438c90bef9c05170e98d538012a2ac`。

XSA SHA-256：`7dc76f78e2c363afd55ee773bdf854cf3eef5bf54d453093a1a281cb4dc61d64`。

模型 bundle：`5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710`。

## 验证边界

原始 33×47 结果是本轮核实后复用的已有实跑，不是本轮重跑，也不是布线后全网验证。旧核日志的 `board_mismatch=171` 对照的是历史错误板端捕获；其本轮 Golden mismatch 为 0。

新核布线后有限样本只覆盖两次卷积、ReLU、拼接；不覆盖完整整网完成、暖帧、反卷积、系数乘法和加法。功能网表仿真没有 SDF，PS/DDR 在仿真边界替代，不能代表真板、DMA/缓存一致性、板端连续内存容量、视频帧率或 HDMI 验收。大图本轮只生成 layout，没有执行对应 FPGA 推理。

Linux 驱动、设备树、上传、HDMI 和真板验收由软件/上板侧负责。现有共享复位、无独立 AXI 中止/排空及错误诊断限制见 `frame_interface.md`。只有正常 DONE、return=0、completed_nodes=320 才能把本次整帧输出视为有效。
