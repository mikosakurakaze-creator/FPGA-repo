# D A组 INT16、整数 Golden 与硬件优化交付

2026-10-25；远程基线 `feat/software@a19c5f6`。A 数值版本已完成本地验证，源码、数值合同、冻结尺度、复现脚本和小型HLS报告经Master授权发布至`feat/software`；生成参数包、Golden、图片及完整运行输出保留本地。B 的正式硬件接口、RTL、Vivado和真板验收待双方对齐。原始D检查点、FP32结构和历史工程均未修改。

- [B数值接口合同](docs/INTERFACE.md)：真实图、逐节点F、权重布局、精确算术、溢出证明、待确认硬件接口。
- [独立审计](docs/AUDIT.md)：已执行测试、证据、限制。
- [硬件分析与原型对照](docs/HARDWARE.md)：计算/访存/片上存储、HLS原始报告、候选与成本。
- [设计及修正记录](docs/DECISIONS.md)：为何采用当前路线、探索和失败修复。

## 当前数值版本

bundle ID：`2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`。

22语义节点、8普通3×3卷积、3,947参数。input F14，隐藏F13，head/旁路/输出F14；INT16逐输出通道权重、INT64 bias/参考累加，实际认证参数统一37位signed累加足够。权重blob8,280 bytes（含32字节padding）。所有卷积/加法先RHAZ重定标和signed饱和再ReLU；head有符号；显示单独ties-to-even。

复用旧项目的通用整数算术工具，D的图、参数、Golden和硬件验证全部重新建立。旧Grid上板、CNN/Bilinear/Curve性能不属于本D版本。

## 复现环境与命令

从仓库根目录执行，Python3.12，C++17的g++。HLS是单独的可选实验，不是整数复现依赖。

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r models/compact_d/fixed/requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m models.compact_d.fixed.reproduce --out outputs/d_reproduce
```

默认不需要私有图片：冻结尺度双重导出逐文件一致、FP32身份/容差、Fraction参数/标量图、整数边界、合成逐层Golden、720p和独立C++全图回归、交付SHA审计。拒绝覆盖已有目录，每个子命令都有参数、UTC时间、退出码、日志SHA。

要重做12张真实保留图，在`--image-list`传JSON路径列表。文件内容/label/SHA必须与交付的保留集身份记录核对；完整复验可提供原`evaluation_images_identity.json`。没有图片时不能声称重做真实效果评估。校准报告保留在交付证据，正式复现直接使用冻结`scales.json`，不重新选择尺度。

分步执行：

```powershell
python -m models.compact_d.fixed.export --out outputs/d_package
python -m models.compact_d.fixed.suite --package outputs/d_package --out outputs/d_golden --720p --image-list evaluation_images.json
python -m models.compact_d.fixed.check_oracle --package outputs/d_package --out outputs/d_oracle --full-frame
python -m models.compact_d.fixed.verify_delivery --package outputs/d_package --golden outputs/d_golden --oracle outputs/d_oracle --report outputs/d_audit.json
```

不依赖torch的单张整数推理和C++参考：

```powershell
python -m models.compact_d.fixed.infer --package outputs/d_package --input photo.jpg --out outputs/d_single --dump-all
g++ -std=c++17 -O3 models/compact_d/fixed/oracle.cpp -o d_oracle.exe
./d_oracle.exe outputs/d_package outputs/d_single/input.i16 H W outputs/d_cpp
```

H、W填写**真实处理尺寸**。文件比对见接口合同；C++/Python参考测时均是Host时间，不能当FPGA性能。

## 本轮证据与移交

本地证据入口为`outputs/compact_d/`：

- `package_v3/`：冻结manifest、graph、scales、parameters、oracle descriptor、overflow proof。
- `golden_v3/summary.json`：28组输入，12张完整处理尺寸holdout，15组合成小图、1张720p模式图；364份原始节点文件+28份输入，全部SHA。
- `reproduction_final/oracle/report.json`：10组×22节点精确一致（含随机720p）、8,696组算术、6组非法输入。
- `audit_final/audit_fp32_integer.json`：16参数张量精确Fraction重算、5种shape×22独立标量边界、5个身份/语义破坏负测、全部通道溢出界重算。
- `calibration.json`与`scale_study/report.json`：21组校准及12张center128的F12/F13/F14对照。
- `delivery_audit_final.json`及`reproduction_final/`：文件身份审计及干净输出目录完整复现。

28组无激活饱和；相对D FP32，最坏case输出MAE3.6851e-5，最坏单值误差2.3473e-4，RGB8最大差1。真实图仅评价量化是否损伤D，不能据此宣称去雾/去雨相对清晰真值达标。真实图的FP32、INT16及放大差图保留用于查看。

最终本地ZIP及SHA路径见`outputs/compact_d/DELIVERY.json`。该包供用户审核/线下交接，未自动上传任何数据集、生成权重包或运行输出。Git交付包含源码、合同、尺度和小型HLS证据；可用上方命令重建数值包及合成/720p Golden。ZIP保留审核时的文档快照，发布时仅更新Git文档状态，数值源码和bundle不变。不要只复制`parameters.bin`遗漏身份、图和数值合同。
