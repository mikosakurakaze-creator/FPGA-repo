# Master 审核入口与最终交付清单

日期：2026-10-25。最新远程与独立工作区基线均为 `a19c5f6d379675a8b6b512694dae99b364a85533`。
最终 bundle：`2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`。

## 1. 本轮完成内容

D为8层3×3平面残差网络：stem3→8、3个8→8→8残差块、head8→3，再加原图旁路并ReLU。3,947参数，720p稠密卷积3.5831808GMAC。复用lzm的严格原始检查点、结构、预测预处理、FP32图和参考小图；复用旧A交付的通用整数算术函数，不复用旧Grid参数/硬件/板测结论。

A数值工作完成：INT16格式、确定性参数与bias导出、逐层图/尺度/布局、37位充分累加界、独立整数参考、逐层及最终Golden、真实图量化误差、接口合同、复现脚本和独立审计。最终schema已明确22节点INT16/NCHW。参数、源码、Golden和证据均通过SHA核验。

28组实际推理（15小图、720p模式图、12完整处理尺寸真实holdout）全部零饱和；相对原D FP32，最坏case输出MAE3.6850703e-5，单值最大2.3472309e-4，显示RGB8最大差1。12真实图为雾8/雨4，仅比较定点是否损伤原D，未证明独立去雨效果或清晰恢复真值质量。

## 2. 修改文件、原因和关键差异

已存在文件仅修改两个入口，原结构、权重与FP32程序均未修改：

| 文件 | 原因及差异 |
|---|---|
| `doc/README.md` | 增加D A组本地交付入口；区分已完成数值与未完成正式硬件 |
| `models/compact_d/README.md` | 更新本地INT16/Golden状态及链接，保留未集成/未上板边界 |

新增目录 `models/compact_d/fixed/`：

| 文件 | 原因及关键行为 |
|---|---|
| `__init__.py` | D专属数值包命名空间 |
| `.gitattributes` | 发布时保护冻结尺度和原始报告的字节SHA，固定Python/C++源码LF，避免Windows换行转换破坏身份 |
| `numeric.py` | Torch-free 22节点整数执行；严格包/源码/图身份；有符号head/原图旁路；显示ties-to-even |
| `export.py` | 确定性OIHW INT16/INT64导出、64B文件对齐、逐通道尺度、图dtype与溢出证书 |
| `calibrate.py`、`scales.json` | 记录校准范围并冻结F13隐藏/F14输入输出，残差同尺度 |
| `study_scales.py` | F12/F13/F14同12保留图center128裁块对照，明确范围余量与误差权衡 |
| `suite.py` | 合成/完整处理尺寸真实图/720p Golden、22节点身份、FP32误差与可视化 |
| `infer.py` | 无torch单图整数参考，支持逐层原始输出 |
| `oracle.cpp`、`check_oracle.py` | 标准C++17独立整数图、算术边界与非法输入测试、全720p交叉核对 |
| `audit_fp32.py` | 独立函数图、Fraction参数量化、Python大整数标量图、schema/破坏包负测、文件审计 |
| `test_numeric.py` | 所有RGB8码、全部INT16显示码、舍入/溢出边界独立算术测试 |
| `compare.py` | 带bundle检查的硬件/RTL原始文件比较；不声称证明数据来源 |
| `reproduce.py` | 一条命令双导出、Golden/720p/独立参考/审计；保存命令、UTC、退出与日志SHA |
| `verify_delivery.py` | 只读核对源、权重、包、Golden、输入、显示、统计及独立参考证据 |
| `requirements-lock.txt` | 实际验证直接依赖版本，HLS非数值复现依赖 |
| `hardware/conv_micro.cpp`、`conv_micro.hpp`、`conv_micro_tb.cpp` | direct与3行缓存+OC8的隔离卷积、独立oracle和压力测试，不含正式AXI或B模块 |
| `hardware/run_proof.py`、`freeze_evidence.py`、`audit_evidence.py` | 可配置工具/目标的Host+HLS运行、冻结报告与身份审计 |
| `hardware/evidence/` | 6份实际综合rpt/xml及evidence.json，绑定最终参数/源码/逐层向量 |
| `README.md` | 安装、复现、整数运行和交付入口 |
| `docs/INTERFACE.md` | 图、dtype/F、参数偏移、数值次序、位宽、Golden与B待确认接口 |
| `docs/AUDIT.md` | 独立审计与实际原始证据 |
| `docs/HARDWARE.md` | 性能瓶颈、定量账目、优化前后和硬件验收边界 |
| `docs/DECISIONS.md` | 设计选择、失败/修正及身份演进 |
| `docs/REVIEW.md` | 本审核清单 |

`outputs/compact_d/`、`outputs/compact_d_hardware/`都是忽略的本地证据；参数blob、Golden、私有处理后测试图和ZIP不会自动进入Git。完整文件SHA清单在本地ZIP的`DELIVERY_MANIFEST.json`，压缩包身份见包外`DELIVERY.json`和`.zip.sha256`。

## 3. 已执行的验证

- 原检查点SHA/16张量/3,947参数/15,788B FP32 blob及44个旧参考节点；跨torch版本最大差2.3841858e-7，当前独立函数图精确一致。
- 6个预处理用例，包括EXIF手工像素方向、小图不放大和比例限制。
- 21个校准样本；12个holdout完整图评估；12个center128精度策略对照；校准/holdout SHA核对。
- 15组合成小图NumPy/SciPy直接卷积所有节点精确一致，完整720p模式图逐层保存。
- 独立C++10组×22节点=220精确一致，含720p随机；8,696算术边界/溢出、6非法输入拒绝。
- Fraction从原FP32逐值重算全部INT16/INT64参数；5尺寸110独立Python标量边界；全部通道溢出证明重算；5个重新hash的破坏包负测。
- 最终28输入+364节点文件以及显示图、输入转换、统计和最终身份审核。v2→v3全部616节点哈希相同，仅图类型/范围元数据修正。
- 两次Vitis CSim、两次8×8卷积HLS综合；六个实际隐藏卷积Golden用两个原型与独立oracle核对。
- 最终冻结源码双导出逐字节一致，完整7阶段从新输出目录复现通过；源码快照检查通过。
- 源码语法编译、`git diff --check`；只修改2个既有README入口，数值及硬件新内容隔离。
- 最终ZIP另进行解压SHA全检查、使用解压源码重新构建参数/720p/独立C++/审计、单图整数及全节点比较；实际结果以`DELIVERY.json`为准。

## 4. 优化前后和实际限制

六个隐藏卷积占88.89% MAC。单张720p C8图14.06MiB，全部原始参数仅8,248B；优先评估隐藏卷积并行、权重常驻及行复用。简化逐层特征和旁路读取账目267,264,000B/720p，非DDR测量。

相同Vitis2025.2、10ns、独立8×8 C8卷积：direct→3行缓存+OC8，延迟36,877→7,781 cycles（局部比4.739倍），LUT2452→4029、FF1516→2316、BRAM18K0→9、DSP1→8。两者内部MAC循环II1，外部像素循环不是1pixel/cycle。全部数值一致。目标器件借用可用本地配置，正式D目标需B确认。

本轮未执行：D正式全网HLS/RTL cosim、AXI/DDR真实测量、Vivado routed、镜像生成、实体板端或端到端FPS。没有B当前D实际基线，因此不声明整网/真板提速百分比。

## 5. B组需要继续的工作

收到本包即可按图/参数/Golden开始普通卷积与残差实现。先共同确认模型ID/ABI、地址/对齐/尺寸/布局、寄存器、DMA生命周期、idle/超时、时钟/复位，再决定共享引擎或多层流式。A给出37位窄化、行缓存、OC并行与保留边界融合候选；新增INT8/结构调整/移除量化边界需双方重评精度并新建数值版本。

wzh须提供小图逐层RTL、720p相关计数、Vivado实际资源/时序、镜像SHA和持板队友的必要板测。lzm再适配上传/驱动/HDMI。没有模型/权重缺失阻塞；正式硬件合同及物理性能是后续协作依赖。

## 6. 审核时状态与授权发布

- 审核时工作区：`C:/Users/lenovo/.codex/worktrees/compact-d-a-delivery/-`，detached HEAD `a19c5f6`；目标协作分支仍是`feat/software`，未创建新的软件功能分支。
- 修改：2个既有README；新增`models/compact_d/fixed/`。数值包及运行输出留在忽略目录。
- 原工作区、现有`feat/software`工作区、旧CNN/Bilinear/Curve/C8/Grid工程、原检查点、队友分支与main未修改。
- 审核前未执行`git add/commit/push`。Master随后明确授权直接Push，本次只提交上述源码、合同、冻结尺度及小型HLS证据并发布至`feat/software`；不上传参数包、Golden、图片、完整运行输出或本地ZIP。
- 本次不合并main、不重写历史、不清理分支，不移动已有工作区。审核ZIP保留原快照，发布文档状态更新不改变已验证数值源码和bundle。
- Commit Message：`feat(compact-d): deliver audited INT16 Golden and isolated HLS proof`
