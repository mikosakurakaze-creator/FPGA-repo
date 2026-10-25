# D 模型 FPGA 加速器（B 侧）

目标：KV260/K26、1280×720、30 FPS。已完成 HLS、RTL 小图验证、系统综合和 200 MHz 布局布线，bit、bit.bin、XSA、HWH 已生成并通过一致性核验。实际板端数值与帧率由持板同学验收。

## 入口

- `hls/`：八卷积引擎、行缓存、残差/RGB FIFO 和 DDR top。
- [接口合同](docs/INTERFACE.md)：数值、布局、寄存器、DDR 和复位边界。
- [构建说明](docs/BUILD.md)：参数、Golden、HLS、Vivado 重建。
- [验证记录](docs/status_20261025.md)：实际证据及未完成范围。
- `board/k26_compact_d_20261025/`：bit、bit.bin、XSA、HWH、同版参数、测试向量与报告。

## 实现

D 为 3→8 stem、三个双卷积残差块、8→3 head，共八层 3×3 卷积。八个引擎并行流水，隐藏卷积六 phase/像素，phase 循环 II=1。中间特征不写 DDR，权重固定在 bit 中。

RGB、NCHW、小端 signed INT16；输入 F14、隐藏 F13、输出 F14；37 位累加，保留 A 的 RHAZ、饱和及激活次序。720p 两份图像缓冲约 10.55 MiB，无中间全图 scratch。

这是独立 D 镜像，包含 PS、D 和必要互连。旧 Weather、GridDehazeNet、低照度工程及镜像完整保留。控制地址 `0xA0050000`，输入经 HP0、输出经 HP3。

## 实际结果

| 项目 | 结果 |
|---|---|
| Host / CSim | 各 12 帧、22 节点逐元素对齐 |
| RTL co-sim | 12 帧及 3 次非法调用通过，最终输出零差异 |
| 最大宽度 | 两帧 17×1280 活动输出零差异；完整大图 suite 未完成 |
| 布局布线 | 200 MHz，setup +0.328 ns，hold +0.010 ns |
| 路由 | 84,463/84,463 nets，0 routing errors |
| 布线后资源 | LUT 25.76%，FF 14.35%，BRAM 4.86%，DSP 60.74%，URAM 62.50% |

六 phase/像素对应 720p 计算主体约 27.65 ms，仅为结构预算，未计流水填充和 DDR 停顿。尚无完整 720p RTL 或真板 30 FPS 结论。RTL co-sim 不是布线后数值仿真。

## 版本

A 来源：`C:/Users/wzh16/Desktop/github clone/feat-software` 的 `feat/software@9ef5faf`，未修改其源码、结构、尺度或参数。

- bundle：`2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`
- 参数 SHA-256：`b30ccd73ad10a685db4c591d3c4a31286178bc80be8e65ff3801364458706e57`

本轮只做加速器、DDR 调度和综合实现；驱动、上传、HDMI 及真板验收由下游完成。本目录纳入远端 weather_fpga_integration 分支管理；实际提交与推送状态以 Git 记录为准。Commit Message：`feat(fpga): add compact D streaming accelerator`。
