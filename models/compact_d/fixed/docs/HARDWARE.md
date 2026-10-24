# D 的硬件分析与独立卷积优化证据

日期：2026-10-25。对应选定 D 检查点 SHA-256：
`0d2678ba533a83c797d5b7a2a922461440fa47f93043525a9165f0a1f9fc28fc`。

本轮没有修改 B 的硬件工程、寄存器、AXI、DDR 布局或镜像。以下代码是独立数值与综合原型，
不是正式 D 加速器。发布交接明确 D 尚无 HLS、RTL、布局布线及真板基线；
仓库 `fpga/hls/README.md` 也只是占位。旧 Grid、C8 和低照度工程的结果不能作为 D 基线。

## 1. 真实计算规模与瓶颈

D 的 8 层卷积均为 stride1、padding1 的 3×3：stem 3→8、三个 8→8→8 残差块、head 8→3。
全部特征保持 H×W，没有下采样、BN、concat 或反卷积。三处块残差之外，还有原图旁路。

| 卷积 | 参数权重数 | 每像素 MAC | 720p MAC | 720p INT16 输入/输出大小 |
|---|---:|---:|---:|---|
| stem 3→8 | 216 | 216 | 199,065,600 | 5,529,600 / 14,745,600 B |
| 每个隐藏 8→8，共 6 层 | 576 | 576 | 530,841,600 | 14,745,600 / 14,745,600 B |
| head 8→3 | 216 | 216 | 199,065,600 | 14,745,600 / 5,529,600 B |
| 合计 | 3,888 | 3,888 | **3,583,180,800** | 逐层物化卷积特征读写 217,497,600 B |

另有 59 个 bias，总参数数为 3,947。INT16 权重仅 7,776 B，INT64 bias 472 B，
原始数据合计 8,248 B；参数包还有 64 B 对齐填充，以其 manifest 为准。
全部权重常驻片上值得优先评估。一个 720p C8 特征图却有 14.06 MiB，完整特征图搬运和
隐藏卷积计算才是主要压力；实际哪一个占主导须由 B 的周期计数和 AXI 计数确认。

上述 MAC 按包括零填充位置的稠密卷积计数，1 MAC 表示一次乘加，不折算成 2 FLOP。
六个隐藏卷积占总 MAC 的 88.89%。主机测时、HLS、RTL、routed 和真板是不同的证据层级。

## 2. 数据搬运与缓存的可核对账目

在“每层输入完整读一次、输出完整写一次，ReLU 与卷积/加法合并”的假设下，
8 层卷积共 217,497,600 B/720p；额外读取三个 C8 残差源与 C3 原图源为 49,766,400 B，
合计 **267,264,000 B/720p**。这个简化模型没有计入逐元素独立输出写入、AXI 效率、
参数搬运、DMA staging、缓存污染或重复读取，不能称为测得的 DDR 带宽。

若全部算子能合法融合，INT16 输入与最终输出的边界数据仅 11,059,200 B；这只是理想边界量，
不是已实现的 DDR 节省，也不是完整系统流量。RGB8 上传/显示接口还可能有额外搬运。

| 缓冲对象 | 1280 宽时的数据容量 | 限制 |
|---|---:|---|
| 一个 C8 卷积的 2 行延迟 | 40,960 B | 还需当前窗口、FIFO、bank/端口开销 |
| 一个 C8 卷积的 3 行循环缓存 | 61,440 B | 本原型采用此方法；只合成了宽 8 的版本 |
| stem C3 的 2 / 3 行 | 15,360 / 23,040 B | 通道与实际访问顺序必须一致 |
| 8 个独立卷积引擎的 2 行数据合计 | 302,080 B | sum(Cin)=59；仅行数据的推算下界 |

302,080 B **不包括** 三个残差分支延迟、原图旁路、通道重排、权重、输出缓冲、
bank 容量取整以及上游停顿的 FIFO 深度。不能据此宣布“整网能放进 BRAM”。
残差旁路要等待两层卷积，原图要等待八层；精确深度必须根据选定数据流和 backpressure
仿真确定。尤其要验证 DATAFLOW 在任意奇数尺寸和停顿下不会死锁。

## 3. 已实现的可复现优化

入口：`../hardware/run_proof.py`。内核：`../hardware/conv_micro.cpp`。
固定 N=1、C=8、H=W=8，OIHW 权重，NCHW 输入输出，INT16 输入/权重、INT64 bias/累加，
每输出通道独立正右移（1..62）、最近舍入且恰好中点远离零，然后饱和到 INT16。
不在 MAC 内部舍入或饱和，不改变卷积边界。没有 ReLU、残差、AXI 或正式系统 ABI。
只接受认证安全累加范围；不接受 INT64_MIN 或任意可能溢出的 bias。

- `d_conv_direct`：输出通道串行，直接读输入及权重，MAC 循环 pipeline。
- `d_conv_row_oc8`：三行循环缓存，每个真实输入值只加载一次；缓存权重并按输出通道分 bank；
  八个输出通道同时累加。仍在每个卷积边界执行完全相同的重定标。

这把行复用、权重缓存与 OC8 并行打包在一个候选中，测到的是组合变化，不能拆成三个独立收益。
8×8 的 direct 内部输入读取请求有 30,976 次非零填充访问，row 仅加载 512 个输入值；
这是源码访问账目，不是实测 DDR transaction。两者稠密 MAC 都是 36,864 次。

### HLS 实测综合估算

工具 Vitis HLS 2025.2，目标 `xck26-sfvc784-2LV-c`，周期 10 ns，uncertainty 2.70 ns。
器件与时钟借用本地历史实验的可用配置，仅用于受控对照，最终 D 目标需 B 确认。
表内都是 HLS C synthesis estimates；没有执行 Vivado 布局布线。

| 项目 | direct | row + OC8 | 解释 |
|---|---:|---:|---|
| 顶层延迟 cycles | 36,877 | 7,781 | 包含候选权重/行加载和控制开销 |
| 顶层启动间隔 cycles | 36,874 | 7,782 | 整次 8×8 卷积，不能当作像素 II |
| MAC 循环 achieved II | 1 | 1 | direct 展平 36,864 次；row 每个像素 72 次 |
| 目标周期 ns | 10.000 | 10.000 | 相同约束 |
| 估算周期 ns | 5.992 | 5.922 | 不是真实可运行时钟保证 |
| DSP | 1 | 8 | 16×16 乘法并行数变化 |
| LUT | 2,452 | 4,029 | +1,577 |
| FF | 1,516 | 2,316 | +800 |
| BRAM_18K | 0 | 9 | 片上行/权重缓存与分 bank 有代价 |
| URAM | 0 | 0 | 小图原型结果 |

相同微基准延迟比为 36,877/7,781 = **4.739×**，减少 29,096 cycles（78.90%）。
这不是 D 整网或真板提速。OC8 内部 MAC II=1，但其外层像素迭代未 pipeline，
报告为 103 cycles/迭代，叠加行加载等开销；不能声称“1 pixel/cycle”或“整网 8 倍”。
小数组的 RAM bank 映射也不能线性外推到 1280 宽所需 BRAM。

原始顶层报告和 row 的 ROW_MAC 子模块报告随源码保存于 `../hardware/evidence/`；
`evidence.json` 记录 SHA-256、源代码身份、参数 bundle ID、实际层向量身份和测试结果。
完整工具日志及 HLS 工程留在 ignored `outputs/compact_d_hardware/`。

### 数值验证与范围

独立 C++ oracle 用有符号除法和余数实现 RHAZ，避免与内核的无符号绝对值移位复用同一实现。
12 组压力测试覆盖零、全 INT16 正负极值、正负中点、饱和及确定性随机值，每组 512 个输出。
两个候选均与 oracle 逐元素一致；两次 Vitis CSim 都报告 0 errors。

另外从正式 bundle 的 `random_8x8` 逐层 Golden 直接提取六个隐藏卷积的输入、权重、bias、
shift 和输出，不重新量化；每个候选都与这六层 Golden 和独立 oracle 完全一致。
该项为 g++ Host C++ 验证；Vitis CSim 的 12 组测试是合成随机/边界测试。
没有把完整 D 的 Python/C++ 整网验证算成本微内核的 RTL 验证。

最终包身份为 `2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`。
v3 修正了图中的输入 dtype/范围元数据，没有改变参数、scale 或 Golden 数值字节。
本轮已使用最终 `package_v3` 与 `golden_v3/random_8x8` 重新执行上述六层 Host 检查；
证据审计再次核对最终 bundle、六个实际向量及三份内核源码。
HLS 综合报告对应的内核源码与最终检查源码 SHA 完全一致，因此无需重复综合。

本原型没有覆盖 stem/head 的不同通道数、奇数宽、小于 3 的尺寸、720p 硬件调度或 AXI。
这些必须由 B 的正式实现用 A 的全尺寸 Golden 验证，不能只靠这里的 8×8 测试。

## 4. 给 B 的优化优先级与语义约束

1. **先保存真实 D 基线。** 对当前正式实现记录参数身份、尺寸、总周期和输入/计算/输出分项，
   再增加 AXI 读写量及停顿计数。没有 D 基线时不要与旧 Grid 板测相除宣称提速。
2. **隐藏卷积输出通道并行与权重分 bank。** 本原型已证实一个具体 OC8 候选的 C 数值一致和
   HLS 变化。再比较 Co=1/2/4/8、Ci=1/2/4/8 的正式调度与存储端口限制。
   若每 cycle 只有一个输入样本，8 输出并行需 8 个权重端口，单纯 UNROLL 不会自动保证吞吐。
3. **权重常驻 + 行复用。** 权重很小，优先减少重复加载和外部特征读取。正式接口可保留现有
   参数 blob，在内部缓存/重排；如要修改外部排列，必须与 A、软件侧重新版本化合同。
4. **融合 Conv→饱和→ReLU，以及 Add→饱和→ReLU。** 可以取消中间完整特征图，
   但必须保留已冻结的舍入、重定标和饱和次序。不能先 ReLU 再省略带符号 head 或残差饱和。
   把相邻两卷积直接做成一个高精度算子、推迟第一次量化，会改变 Golden。
5. **三层块内复用，再决定全网流式。** 可以先验证单块双卷积行缓存和残差 FIFO，
   利用 A 的逐层 Golden 做 RTL 检查，再扩展到多块，降低全网 FIFO/存储调度的不确定性。
6. **认证窄累加器。** 正式参数证明的全局 signed 累加位宽为 37 位（含任意 signed INT16 源）。
   本原型仍用 INT64。B 可评估 per-layer `ap_int` 与 DSP48 累加器，但 RHAZ 加半步、求绝对值、
   add 的尺度对齐和最终饱和还需要单独保证位宽；不得把中间结果截断到 INT32。
   该候选未在本轮综合测量，不能声称已节省资源。

若只做足宽乘加的分块、重排求和、缓存、bank、并行或流式重排，并严格保持每个数值边界，
可以数学上保持 Golden 精确一致；正式实现仍须 RTL 逐层回归。
INT8、权重剪枝、低秩分解、替换卷积、移除残差、融合量化边界或改变 rounding 均可能改变精度，
需要 A/B 共同审定新版本，不能沿用本次 bundle ID。

## 5. 吞吐与资源的理论约束

假设一条 16×16 MAC lane 每 cycle 接受一个乘加，720p 每帧最低计算周期约为
`3,583,180,800 / lanes`；不含边界、访存、填排、调度或带宽效率。
单个共享 OC8 引擎在 100 MHz 的理想计算下限为 4.479 s/frame。
这只是算术下限，不能宣称已经测到此速度。

若要求 720p×30fps，需求是 107.495424 GMAC/s；在 100 MHz 下需要至少约 1,075 条上述 lane，
200 MHz 约 538 条，均尚未考虑利用率。是否能满足器件、散热、时序及系统资源，须 B 确认。
因此仅凭 D 参数少，不能承诺原尺寸 720p 实时。提高空间或通道并行后，还须验证 BRAM 端口、
路由、AXI 与软件/HDMI 的完整链路。不得把缩小推理再放大的显示结果称为 720p 原尺寸推理。

## 6. 复现、已执行与后续验收

在仓库根目录运行；`--golden` 方式只需要标准 Python 和 g++，不依赖 numpy：

```powershell
python models/compact_d/fixed/hardware/run_proof.py --package outputs/compact_d/package_v3 --golden outputs/compact_d/golden_v3/random_8x8 --out outputs/compact_d_hardware/actual_v3
python models/compact_d/fixed/hardware/run_proof.py --hls --out outputs/compact_d_hardware
python models/compact_d/fixed/hardware/freeze_evidence.py --actual-dir outputs/compact_d_hardware/actual_v3
python models/compact_d/fixed/hardware/audit_evidence.py --package outputs/compact_d/package_v3
```

可用 `--vitis-bin`、`--gxx`、`--part`、`--clock-ns` 覆盖本机路径及目标配置。
运行器只写独立 outputs 目录，设置缺失的 `PROCESSOR_ARCHITECTURE=AMD64`；
不会启动板卡、改 B 工程、提交或 Push。工具日志报告采用宿主时区原始日期，勿据此推断客户端时区。

本轮已执行：两个候选 Host 编译和全部精确比较、两个 Vitis CSim、两个 HLS C synthesis，
保留实际参数/Golden 身份和源代码 hash、理论账目与资源/周期对照。
本轮未执行：正式 D 全网 HLS、RTL cosim、AXI 流量实测、Vivado routed、硬件镜像生成或真板操作。
HLS 自动 IP 包装产生的临时文件留在 ignored outputs 内，不构成正式可用 D 镜像。

B 应确认：最终器件/时钟、并行度和缓存策略、输入输出/参数 ABI、残差与原图延迟、
DMA 生命周期、idle/completion 条件、最大尺寸、超时后 AXI 写事务归属。
之后依次完成小图逐层 RTL Golden、720p RTL/系统计数（若预算允许）、routed 资源/时序，
再由持板队友做必要的小图与720p板测，分别报告核心与完整请求耗时。

官方资料用于方法说明，实测数字以上述原始综合报告为准：
[AMD Array Partitioning](https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/Automatic-Array-Partitioning)，
[Xilinx convolution dataflow tutorial](https://github.com/Xilinx/SDAccel-Tutorials/blob/master/docs/convolution-tutorial/dataflow.md)。

## 7. 本轮决策与修正记录

- 先确认 D 无正式硬件基线，选择独立固定尺寸微基准；没有直接复制旧模型性能结论。
- 为隔离访存/并行变化，两个内核保留 INT64 MAC 和相同重定标，暂不把 37 位窄化混进收益。
- Vitis 启动器最初没有输出，定位为宿主环境缺 `PROCESSOR_ARCHITECTURE`；设置后 CSim/综合正常。
- 默认系统 Python 没有 numpy，实际 Golden 提取改为标准库解析既有二进制，避免重新生成参数。
- OC8 只得到 4.739× 的小图综合延迟比，报告显示外层未 pipeline 及加载/控制开销；
  保留该结果，没有用理想 8 倍替代，也未据此扩大到未验证的全网架构。
