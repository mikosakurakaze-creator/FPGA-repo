# FPGA 队友从这里开始

分支：`feat/software`。本目录发布去雨、去雾的 C8 计算候选，未完成 FPGA 验收。原有低照度模块仍需保留、联调。

## 先下载

- [C8 硬件候选 ZIP](hardware_candidates/c8_hardware_candidates_v1.zip)
- [ZIP SHA-256 和文件清单](hardware_candidates/c8_hardware_candidates_v1.manifest.json)
- [实测结果与限制](RESULTS.md)
- [原始评测摘要和训练日志](evidence/)

在 GitHub 的 ZIP 文件页面点击 **Download raw file**。无需切换你们自己的 FPGA 开发分支，也无需安装训练环境。

ZIP 解压后，`derain/` 和 `dehaze/` 使用相同网络结构、不同权重及定标，不能只更换权重而沿用另一任务定标：

| 文件 | 用途 |
|---|---|
| `integer_spec.json` | 运算图、层配置、节点与逐输出通道定标、舍入等规则 |
| `layers/*.bin` | INT8 权重和小端 INT32 bias |
| `weight_binaries.json` | 权重形状、布局、字节数和 SHA-256 |
| `input_q14_nchw_le.bin` | Golden 输入，RGB / NCHW / 小端 INT16 Q14 |
| `output_q14_nchw_le.bin` | 对应 Golden 输出，同布局和格式 |
| `golden_manifest.json` | 输入输出形状和哈希 |
| `golden_layers/*.bin`、`golden_layers.json` | 逐节点 Golden、形状、定标和采样位置 |
| `reference/integer.py` | ZIP 根目录下的整数数值参考；不是 HLS 源码 |

注意：`reference/` 位于 ZIP 根目录。Golden 节点的卷积/加法张量在重定标、饱和之后、ReLU 之前，具体以 JSON 的 stage 为准。先逐层定位差异，不只比较最终图片。

## 队友 A：计算和数值对齐

1. 实现普通 3×3、深度 3×3、1×1 卷积、ReLU、残差加法、重定标和饱和。
2. 严格按 spec 实现最近偶数舍入、零填充、通道布局与定标；权重 INT8、节点 INT16、目标累加 INT32。
3. 首层 → 单残差块 → 整网逐层对齐；去雨、去雾各跑一遍 Golden。
4. 提交每层 PASS/FAIL、首个差异坐标和值、HLS 资源与周期报告。当前没有要求你们重新训练模型。

## 队友 B：数据通路和真板

1. 核对现有设计资源余量，确定缓存和计算单元复用方案。
2. 接入输入输出、DDR/DMA、权重及定标加载、控制状态和缓存一致性。
3. 先支持手动旁路 / 低照度 / 去雨 / 去雾；正常帧需要旁路，自动策略由软件继续补齐。
4. 参考核心分块 128×128、halo=6，检查全帧和边界块；改变分块时重新对照整数参考。
5. 完成布局布线、时序和真板测时：分别记录计算、搬运、端到端延迟及连续帧吞吐，检查丢帧和花屏。

## 今天和后续

- 今天先反馈接口能否接上、资源风险、首层对齐预计完成时间；A 跑首层，B 跑旁路输入输出。
- 随后两天完成整网数值对齐及板端数据通路，再安排三种增强模式联调。
- 每天同步：已跑通内容、数值差异、资源/耗时、阻塞点。

C8：1011 参数；720×1272、128 核心分块含 halo 约 0.990 GMAC/帧。30 FPS 约需 29.7 GMAC/s，仅算力预算，不能代替真板结论。C16 计算量约为 2.7 倍，当前优先接入 C8。
