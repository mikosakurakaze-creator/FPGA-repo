# 2026-10-24 发布修正与必要回归

## 本轮范围

按用户要求优先完成发布文件一致性、33×47 跨分块冷暖 RTL、布线后代表性新核数值回归和旧 Weather 核回归。复用经过原始证据复核的已执行结果，不为后来新增的元数据字段重新长跑。不重复已有且匹配的 HLS 综合、Vivado 综合、布局布线或 bit/XSA 导出。

发布目录：`board/releases/k26_weather_griddehaze_reduced_20261024`。名称保留以避免下游引用失效，不表示所有测试仍为最初的延期状态。最新范围看其中 README 和 `release_manifest.json`。

## 已修正

1. 发布目录增加 Git `-text -whitespace`，防止 `core.autocrlf` 在 checkout 时改动哈希所覆盖的字节。新写说明/清单使用 UTF-8 无 BOM、LF；A 组冻结参数和原始执行证据保留原字节，按其既有身份单独核验。
2. 原发布 HWH 误取 XSA 中的 SmartConnect 子设计。已改为同一 XSA 内的完整 `system.hwh`；没有修改 bit/XSA。本轮也修正了正式收集脚本，要求且提取准确成员名，避免今后只检查“任意 HWH 存在”。
3. 旧核回归适配器原来缺少 `includes_glbl` 报告字段，导致旧 runner 在启动仿真前抛出 `KeyError`。现按实际生成网表检测 `module glbl`，随后实跑通过。该修正不改变硬件。
4. 同版 A 组四个参数文件、33×47/675×1280/720×1280 的 layout、小型新旧核输入和 Golden 已集中到本地发布目录，便于软件侧继续适配。没有实现驱动、上传或 HDMI。

## 33×47 冷暖帧：已核实通过

复核既有实跑目录 `C:/Users/wzh16/Desktop/competing/griddehaze_fpga/work/frame_rtl_33x47_02`，不是把本轮中止的重复实验改写成通过。

- 原始仿真正常退出，日志有两帧完成和 `GDN_RTL_SEQUENCE_PASS frames=2 scope=all_320_nodes bad_model=1`。
- 实际执行的 testbench 在两帧都逐元素比较全部 320 节点；暖帧不清 scratch，并先污染输出，防止把旧输出误当成功。
- 重新读取 320 个冷帧节点 raw，长度和 SHA 均与 A 组同版 Golden 一致；冷暖最终输出各 9,306 字节，也分别逐字节一致。
- 95 个已执行 RTL/ROM 文件同时匹配原实验、当前 HLS 导出和本次 Vivado 构建所用新核 IP。
- 两帧每帧 257,001,499 个仿真周期。这不是板端实测耗时或 FPS。
- 最终输出 SHA：`fa1620c8e2421b09c8181dd08e9231f0a79271162cd04a9eccb15a53679fa7be`。

发布证据：`evidence/cross_tile_review.json`、原始日志、实际执行 SV；下游小向量见 `validation_33x47/`。原 `frame_rtl_33x47_releasefix01` 重复长跑已停止并留有中止说明，不计为通过。

## 旧 Weather 核：本轮实跑通过

`experiments/griddehaze_frame/work/legacy_routed_releasefix02` 使用本次五核系统的实际 routed 网表、父层连线、复位、控制和 HP0/HP3 SmartConnect；PS 由仿真 DDR 刺激替代。8×8 连续四帧 task=0、0、1、0，每帧 192 标量，全部 Golden mismatch=0。已重新对四个原始输出与保存的 Golden 逐字节比较。

日志中 `board_mismatch=171` 是对历史错误板端捕获的比较，不能解释为本轮 Golden 回归失败。此项仅证明旧 Weather 核；CNN、Bilinear、Curve 保持空闲，没有逐核重跑数值回归。

## 新核布线后：必要样本回归

本轮采用真实 routed 系统快照，通过正常控制接口启动 4×4 同版输入，保留复位、控制、SmartConnect 和两路 DDR 边界；Tcl 只推进时间、读取图节点索引和仿真 DDR，**不强制 DUT 内部状态，不替换算术，不用 Golden 注入内部结果**。分别在 scratch 被复用之前采集节点 1、2、3、4，即两次卷积、ReLU 和拼接的真实输出，再由 Python 独立逐字节比较 A 组 Golden。

工具：`tools/routed_sample_trial.py`。本地实跑目录为 `work/frame_routed_sample_releasefix01`；仿真退出码 0，已产生并核对 `sample_result.json`：4 个节点、1,280 个标量全部零差异。原始 capture、Tcl、日志及四个 raw 已复制到发布 `evidence/`，并记录源 routed 网表、实际编译快照和夹具哈希。完整布线后整网冷暖帧不作为本轮必跑项；反卷积、系数乘法和加法没有由这项有限样本覆盖。全图算子的整数证据来自前面的完整导出 RTL 回归，不能混称为完整布线后全图回归。

此前直接实例化 routed 子核的试验在 CSR 响应处失败，因为跨层优化后的复位别名和常量端口不再构成可独立使用的原始 IP 边界；该失败没有被当成通过。当前样本采用保留实际父层的系统路径。

## 硬件与未覆盖项

bit SHA-256：`07f23b4d67f60270d3c35725df32289468438c90bef9c05170e98d538012a2ac`。

XSA SHA-256：`7dc76f78e2c363afd55ee773bdf854cf3eef5bf54d453093a1a281cb4dc61d64`。

完整 HWH SHA-256：`25cd124529ca6af00b9976c041e48994e0a6b428fc6812ea8666dcda8d621edb`。

100 MHz routed timing 仍为 WNS +0.729 ns、WHS +0.010 ns、WPWS +3.500 ns，191,089/191,089 nets routed。DRC 没有 Error/Critical Warning，但有普通 Warning。没有因本轮报告更新重新实现电路。

本地功能仿真没有 SDF，不替代真实 PS 初始化、DMA/缓存一致性、板端内存容量、连续视频、画质和真板验收。大图 layout 的生成也不代表已执行大图 FPGA 推理。共享复位、无独立 AXI 中止/排空和错误诊断等既有硬件限制仍见 `frame_interface.md`。

## Git 与建议提交

本轮仅在现有 `weather_fpga_integration` 分支修改和验证，没有切换分支、暂存、提交或推送。发布文件和同版模型都已经放在本地，庞大的工具工程/缓存仍在被忽略的 `work/` 中。

建议 Commit Message：`fix: preserve release bytes and add verified FPGA regressions`。按仓库协作规范，等待用户审核当前文件和实际验证范围后再进行获批的 Git 操作。

## 文件改动清单

| 文件或目录 | 原因与关键差异 |
|---|---|
| `.gitattributes` | 对本发布目录关闭 Git 文本换行转换，保留发布哈希覆盖的原字节。 |
| 根 `README.md`、`board/README.md` | 增加当前五核候选、同版参数和核查结果入口，旧故障版本继续保留。 |
| `experiments/griddehaze_frame/README.md` | 更新真实已完成项，区分完整导出 RTL 与有限布线后样本。 |
| `experiments/griddehaze_frame/docs/reproduce_frame_system.md` | 完整长流程改列为扩展选项，增加复用编译快照的有限回归入口。 |
| `experiments/griddehaze_frame/docs/release_review_20261024.md` | 新增本报告，说明修改、证据、未执行项和 Git 边界。 |
| `tools/legacy_path_trial.py`（实验目录下） | 从实际输出网表检测 `includes_glbl`，修复启动前 KeyError。 |
| `tools/collect_board_artifacts.py`（实验目录下） | 收集准确的完整 `system.hwh`，不接受“任意 HWH 存在”作为完整系统描述。 |
| `tools/verify_board_release.py`（实验目录下） | 新增字节哈希、Git 转换、XSA 成员、冻结参数/layout 及原始数值证据核验。 |
| `tools/routed_sample_trial.py`（实验目录下） | 新增有限样本复现与独立原始输出比较，明确不声称完整布线后整网通过。 |
| 发布 `griddehaze_system.hwh`、`release_manifest.json`、`SHA256SUMS`、`README.md` | 修正完整系统 HWH、精确成员名、真实回归覆盖范围和全部发布文件哈希。 |
| 发布 `routed_timing.rpt`、`xgriddehaze_frame_top_hw.h` | 仅处理发布换行，时序数值和寄存器定义不变。 |
| 发布 `model_int16/` | 新增原字节参数四文件、三组实际生成的 layout、容量清单和中文使用说明。 |
| 发布 `validation_33x47/`、`validation_legacy_8x8/`、`evidence/` | 新增小型输入、Golden、实际输出、原始执行日志/SV/Tcl及精简审核 JSON；不加入庞大的仿真缓存或工程。 |

实际执行：原始 33×47 320 节点与冷暖输出重新核对；本轮旧 Weather routed 四帧仿真；本轮新核 routed 四节点数值仿真；全部发布字节/冻结模型/layout 与 XSA 校验；修改过的 Python 工具语法检查与 `git diff --check`。

未执行：重新综合/实现/导出 bit/XSA，完整新核布线后整网冷暖帧，CNN/Bilinear/Curve 逐核数值重跑，真板/驱动/HDMI/连续视频验证。现有 bit/XSA 字节身份保持不变，未将这些未执行项写成通过。
