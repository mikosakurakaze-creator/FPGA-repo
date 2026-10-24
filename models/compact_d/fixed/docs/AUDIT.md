# D 数值交付独立审计

日期：2026-10-25。对象：当前 D，非历史完整 GridDehazeNet、C8 或低照度模型。

## 身份与范围

- 原始提交：`a19c5f6`；原始选定检查点为 step 600。
- FP32 检查点 SHA-256：`0d2678ba533a83c797d5b7a2a922461440fa47f93043525a9165f0a1f9fc28fc`。
- 本次整数包 bundle ID：`2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`。
- 8 层 3×3 卷积、3 个残差块、3947 参数、16 个参数张量、22 个语义边界；原图旁路和有符号 head 均保留。
- 整数参数有效载荷 8248 字节；含 64 字节对齐空洞的 blob 为 8280 字节。

审计不修改冻结模型、原始权重、B 的工程或任何旧模型。未运行实体板卡；本文件中的结果均不构成 FPGA FPS、Vivado routed 或系统端到端性能证据。

## 独立实现与实际结果

可复现审计程序为 `../audit_fp32.py`。它直接从检查点张量建立另一份 FP32 函数图，并通过 Python `Fraction` 和任意精度整数实现参数量化、标量卷积、重定标、饱和、残差、旁路。

标量整数路径不调用正式参考的卷积、输入转换、舍入或重定标函数；正式参考只作为被比较对象。

| 检查 | 实际结果 |
|---|---|
| 检查点、16 个 FP32 张量、15788 字节 FP32 blob | 全部 SHA、shape、offset、layout 逐项一致 |
| 两组已发布 FP32 fixtures，8×8、33×47，全部 44 个节点 | 通过；对旧 PyTorch 2.7.1 参考最大绝对差 `2.384185791015625e-7` |
| 当前 `trace` 与独立函数图 | 44 个节点逐元素完全一致；`forward` 最终输出完全一致 |
| 读图预处理 | 6 项通过：小图不放大、宽图、竖图、灰度、RGBA、EXIF 6 |
| EXIF 6 像素方向 | 与原始解码像素手工顺时针旋转 90° 完全一致 |
| INT16 权重、INT64 bias | 16 个张量由精确有理数重新量化后，与 blob 逐字节一致 |
| 独立标量整数图 | 1×1、1×7、7×1、3×5、8×8，合计 110 个节点逐元素一致 |
| 累加界证书 | 8 层全部输出通道独立重算通过；最大绝对界 `38311644308`，37 位有符号累加足够 |
| 损坏包拒绝 | 5 项通过，见下一节 |
| 整数图类型元数据 | 全部 22 节点 `dtype=int16-le, layout=NCHW`；输入整数范围 `[-16384,16384]`、实值范围 `[-1,1]` |

原始 FP32 fixtures 的运行库是 PyTorch `2.7.1+cu126` 的 CPU 路径，本轮为 `2.8.0+cpu`。审计保留旧文件原样，允许 `rtol=2e-5, atol=3e-6` 的跨版本 FP32 内核差异；没有将近似浮点匹配说成整数精确匹配。

正式整数语义为输入/旁路/head/输出 F14、隐藏层 F13、每输出通道 INT16 权重、bias 为 Fin+Fw。运算重定标最近数且中点远离零，显示转换最近偶数；每个卷积/加法/仿射先饱和到 signed INT16，再执行后续 ReLU。不能将两个不同舍入边界任意合并。

## 失败发现与修正

第一次审阅发现初版 loader 只检查图长度/节点顺序，未逐项约束冻结运算字段；同时 producer 哈希被记录但未核对当前源码。若软件或图字段发生变化，旧包存在被误用的可能。

本轮先修正为严格核对原始 D 图、参数 shape/layout/dtype/scale、重定标以及当前 producer 身份，并重新导出 v2。

最终合同复核又发现：复制 FP32 图时，input 的 `dtype=float32` 与 `range=[-1,1]` 没有转换为整数描述，可能误导 B。现已导出 v3，将所有节点明确标记为 `int16-le/NCHW`，并分别声明输入整数范围和实值范围。loader 同步严格核对该类型化冻结图。v3 是唯一正式交接包；v1/v2 仅保留为调查和修正记录。

独立对照证明 v2→v3 的 `parameters.bin`、`scales.json`、`oracle.txt`、`overflow_proof.json` 逐字节相同，图的全部运算/尺度字段相同。28 个测试的输入、全部 616 个节点哈希与全部误差指标相同。变化仅为明确图类型元数据和对应源码/图/包身份；不是重新量化或另换一套 Golden。

独立负面测试在临时副本中修改数据，并重新计算 manifest identity，确保拒绝来自相应语义检查，而非碰巧被旧顶层哈希拦住：

1. 将卷积 stride 改为 2：拒绝 `Wrong D graph`。
2. 将输入旁路 scale 改为 1：拒绝 `Wrong D graph`。
3. 使用陈旧 producer 哈希：拒绝 producer 身份不一致。
4. 将权重布局标记改为 IOHW：拒绝参数 shape/layout。
5. 参数 blob 翻转一位：拒绝文件 SHA 不一致。

临时副本仅在审计输出目录内生成并清理；正式包不被修改。

## 对其余交付证据的交叉审阅

以下证据由其他实现生成，本次审计读取原始结果并检查关联身份；不会将其冒充另一套独立的全尺寸标量推理。

- `outputs/compact_d/golden_v3/summary.json`：28 个测试，15 个小图用 NumPy/SciPy direct 双后端逐节点一致；另有 720×1280 合成图和 12 张真实保留图。
- 所有 28 个输入文件、364 个实际保存的逐节点/最终 Golden 文件：长度与 SHA 核对通过。16 个测试保存全部 22 节点；12 个真实图保存最终整数输出，其他节点保留统计与哈希，不能声称其全部中间文件均已保存。
- 28 测试均零饱和事件。最坏输出 MAE `3.685070293425694e-5`、最坏绝对误差 `0.00023472309112548828`；显示 RGB8 最大差 1 灰阶。
- `outputs/compact_d/reproduction_final/oracle/report.json`：最终 v3 身份的独立 C++17 标量实现 10 个测试、220 个节点全部一致，包括完整 720p 随机图；另有 8696 项算术测试、6 项输入/目录拒绝测试通过。
- 累加界覆盖各层所有 signed INT16 输入及所有部分和。测试中零饱和只说明已执行样本，不证明任意新图片均不会触发饱和。
- 硬件微基准独立审阅：3 份内核源码、6 份原始报告 SHA 一致；以标准 XML 解析直接核对 direct/row+OC8 的延迟 36877/7781 cycles、DSP 1/8、LUT 2452/4029、FF 1516/2316、BRAM18K 0/9。仅为隔离 8×8 卷积 HLS 估算，其他限制见 [HARDWARE.md](HARDWARE.md)。

## 数据与环境

真实图来自本地 Fog/Rain 目录。12 张校准图片从训练集选择，雾/雨各 6 张；12 张评估图严格采用原 `split_manifest.json` 的 holdout，雾 8 张、雨 4 张。文件均按 SHA 查找并核实，未上传图片。校准/评估路径及身份保留在忽略输出目录的 `calibration_images*.json`、`evaluation_images*.json`。

保留集是文件 SHA 与训练/验证集的精确排除，不代表近重复、摄像头或场景独立性已审计。指标是定点 D 相对原始 D FP32 的误差；没有清晰配对真值，不能据此宣称独立去雨能力或真实清晰恢复质量。

实际环境：Windows 11 build 26200；Python 3.12.10；PyTorch 2.8.0+cpu；NumPy 2.2.6；Pillow 11.3.0；审计 CPU 单线程。可用解释器为 `E:\github\griddehazenet-a\outputs\griddehaze\venv\Scripts\python.exe`。这只是复用本地 Python 环境，不是复用旧 Grid 的模型数值或 FPGA 结果。

原私有训练实验的 `compression_models.py` 等源码不在本机可发现交付路径中，`D:\FPGA` 不存在。因此检查点、公开独立模型和已发布 FP32 证据已核对；私有原实验源码的 provenance 哈希仅作为上游声明保留，没有声称重新训练或重新执行原实验。

## 重现与原始证据

在仓库根目录、依赖齐全的 Python 中执行：

```powershell
python models/compact_d/fixed/audit_fp32.py --out outputs/compact_d/audit_final --package outputs/compact_d/package_v3 --golden outputs/compact_d/golden_v3
```

如需独立重复 12 张真实图的 FP32 函数图检查，可追加一个或多个 `--image-root` 指向实际图片所在目录；默认不重复全尺寸画质套件。

原始审计结果：

- `outputs/compact_d/audit_final/audit_fp32.json`：FP32 身份、44 节点、6 项预处理及环境。
- `outputs/compact_d/audit_final/audit_fp32_integer.json`：精确参数量化、110 个整数边界、累加界、5 项损坏包拒绝。
- `outputs/compact_d/audit_final/audit_golden_files.json`：28 个输入、364 个已保存 Golden、28 个显示文件以及 12 个 holdout SHA 的交叉核对。
- `outputs/compact_d/audit_final/v2_v3_metadata_audit.json`：整数图类型明确化以及旧/新参数、尺度、descriptor、证明、全部 Golden 哈希相同。该记录 SHA-256：`ec06b6f715f74107bbbf9279e40ab512d9faaf4e854b03ddc6bdbaf669d53d38`。
- `outputs/compact_d/audit_final/hardware_report_audit.json`：独立 XML 字段及原始报告/源码 SHA 核对。
- `outputs/compact_d/package_v3/`：被审计的正式整数参数、冻结图、scales、身份及累加界。
- `outputs/compact_d/golden_v3/`：样本输入、逐节点或最终 Golden、FP32/INT16/差分图片及 summary。
- `outputs/compact_d/reproduction_final/oracle/`：最终身份的独立 C++ 原始编译输出、各样本及 report。

HLS、RTL、Vivado 和板端验证属于不同证据层级；具体硬件原型结果以硬件报告为准。本审计不将理论 MAC 数、CPU 测时或局部原型转换成全网络板端性能。
