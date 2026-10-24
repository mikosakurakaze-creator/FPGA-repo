# GridDehazeNet A→B 数值与文件合同（候选，尚待 wzh 确认）

日期：2026-10-24。A 组承担定点化、权重和整数 Golden；B 组负责人 **wzh** 承担加速器、DDR 调度和系统集成；lzm 协调并承担上传、驱动适配、HDMI 等软件工作。截图中的聊天仅说明分工和进展，不能代替本轮版本的板端验证。

本文件冻结的是交付文件的解释方式。**尚未与 B 组共同冻结寄存器 ABI、DMA 地址、scratch 分配或硬件支持位宽。** 不得据此替换当前运行系统的模型或驱动。用户转述的 34 FPS 属于已有系统进展，本交付未进行实体板卡、HLS、RTL、综合、布局布线或性能验证。

## 1. 版本身份与采用顺序

- 任务依据：`doc/README.md`、`doc/2.0.1_队友A_去雾模型定点与Golden.md`、`doc/2.0.2_队友B_图片加速器与板端集成.md`。
- 上游：[proteus1991/GridDehazeNet](https://github.com/proteus1991/GridDehazeNet)，提交 `481399129614c3e7c8e892b5d52d60173131dda0`。
- 权重：根目录 `outdoor_haze_best_3_6`，3,889,347 字节；SHA-256 `80a8f3aad5fd0ed744f39bd60bda802087fbb48b2fa2ce86261ac443a4dba396`。
- 构造参数：`in_channels=3, depth_rate=16, kernel_size=3, stride=2, height=3, width=6, num_dense_layer=4, growth_rate=16, attention=True`；官方参数总数 958,051。
- 每次交付以该次 `manifest.json` 的格式版本、源文件哈希、量化配置、`graph.json` 哈希和 `parameters.bin` 哈希共同标识。仅权重文件名相同不构成同一交付。
- 本目录不采用 TinyRestore 的权重、Golden、网络残差、Q14 输出钳位、6 像素 halo 或旧 task=1 ABI。旧 `weather_restore_lab/FPGA_START_HERE.md` 属于旧 C8 任务；`board/README.md` 等 PYNQ-Z2/TBD 占位说明不是本轮 KV260 接口事实。

固定上游树未发现 LICENSE、COPYING 或 NOTICE；README 只有论文引用要求，不能推定为 MIT/BSD 或已获再分发授权。下载原始源码与权重用于本轮本地研究，保留原文件和来源；向外部发布源码、权重或衍生参数之前仍须负责人确认许可范围。论文为 Liu et al., *GridDehazeNet: Attention-Based Multi-Scale Network for Image Dehazing*, ICCV 2019。

## 2. 输入和输出

| 项目 | 数值/文件约定 |
|---|---|
| 输入图像 | 解码为 8-bit RGB；灰度/带 alpha 图像通过显式 RGB 转换；不静默缩放、裁剪或 BGR 交换 |
| 浮点输入 | `x=(2*v-255)/255`，`v` 为各通道像素，范围 `[-1,1]` |
| 整数输入 | `q=round_away(x * 2^Finput)`，Finput 取 input 节点的 `activation_frac`（无覆写则取 manifest 默认）；不得沿用旧 `[0,16384]` 输入假设 |
| 布局 | batch=1，NCHW，通道顺序 R/G/B；连续 C-order，无行 padding、无隐式通道补齐 |
| 文件数据类型 | 输入、中间节点、网络输出均 signed INT16、小端二进制；文件本身无头；维度及各节点 F 从 Golden 元数据和 graph 读取 |
| 地址公式 | `offset_bytes=2*(((n*C+c)*H+y)*W+x)`；输入/输出裸文件长度均 `6*H*W` |
| 网络输出 | 最后 `conv_out` 后 ReLU 的整数结果，范围 `[0,32767]`；真实值 `raw/2^Foutput`，可能大于 1 |
| 显示输出 | 独立转换：先夹至 `[0,2^Foutput]`，再对 `255*raw/2^Foutput` 按最近值、半数远离零舍入，得 RGB8；显示图像不代替网络 Golden |

尺寸解释采用 **H×W**。整数参考接受 H、W 均至少为 4 的整数尺寸，实际可执行上限受主机内存约束。整数程序按完整图计算，保留实际尺寸。两次下采样产生 `ceil(H/2),ceil(W/2)` 和 `ceil(H/4),ceil(W/4)`。转置卷积恢复的是 graph 中 `output_like` 指向的目标特征尺寸。33×47、675×1280、720×1280 是任务要求的独立用例；能构图或估算内存不等于已经完整整数执行通过。实际已执行尺寸与失败尺寸必须查本轮原始运行报告。硬件最大 H/W、地址范围、溢出拒绝行为由 B 冻结；不能通过静默拉伸到支持尺寸解决。

## 3. 整数运算语义

实际各节点 F、权重位宽及各输出通道分数位必须从交付清单读取，不能从文档中的示例或旧文件猜测。manifest 的 `quantization.activation_frac` 是输入/默认值，graph 节点可通过 `activation_frac` 覆写；节点真实值恒为 `raw*2^-Fnode`。候选支持按节点激活定标，卷积权重按输出通道选择二进制定标，bias 对齐实际输入节点 F 与各通道权重的乘积尺度；coefficient 为独立定点参数。配置变化必须重新导出全部相关文件并生成新的 Golden。

定义 `R(z,s)` 为 signed INT64 整数 z 按 `2^s` 重定标：s>0 时 `sign(z)*floor((abs(z)+2^(s-1))/2^s)`；s=0 原值；s<0 精确乘 `2^(-s)`，前提是不溢出。即**最近值、半数远离零**；不是算术右移、向零截断，也不是最近偶数。

定义 `S(z)=min(32767,max(-32768,z))`。卷积/乘系数/加法输出先按各自规则重定标，再 S，再由单独的 ReLU 节点取 `max(0,z)`。不能将饱和或舍入移动到相邻节点之外。

| op | 必须遵守的行为 |
|---|---|
| conv | PyTorch cross-correlation，无核翻转；零填充；`A[o,y,x]=bias[o]+Σ qin[i,sy+ky-py,sx+kx-px]*qw[o,i,ky,kx]`；越界输入贡献 0；输出 `S(R(A,Fin+Fw[o]-Fout))` |
| deconv | 原生 IOHW 权重；每个输入位置向 `y=iy*stride_y-padding_y+ky*dilation_y`、x 同理的目标像素散加；每个目标像素 bias 只加一次；目标边界外贡献丢弃；目标 H/W 从 `output_like` 取得；之后同卷积重定标和饱和 |
| relu | 先 `R(int64(x),Fin-Fout)` 对齐输出尺度，再 `max(0,z)`，最后 S；当 F 相同即普通 ReLU |
| cat | 各输入分别 `S(R(int64(xi),Fi-Fout))`，然后严格按 graph.inputs 顺序沿 channel=1 拼接；不得交换通道或交错 |
| add | 各输入先提升 INT64，再分别 `R(xi,Fi-Fout)`；对齐时不先夹至 INT16，两项宽值相加后仅做一次 S；RDB 残差加法后没有隐含 ReLU |
| mulcoef | `S(R(int64(x)*int64(coef[c]),Fin+Fcoef-Fout))`，通道广播；不得使用浮点乘法或以 1 替代 learned coefficient |

上游 `conv_in` 后没有隐含 ReLU；RDB dense 单元为 Conv→ReLU→cat，四次后是 1×1 Conv→残差相加。加权多分支处是两次独立 mulcoef 后再 add；若硬件改为一次宽乘加后仅舍入一次，会改变本合同的整数结果。算子融合只能在证明所有合法输入逐元素等价后采用。

MAC 和 bias 参考语义为 signed INT64。每输出通道保守界为 `32768*Σabs(qw)+abs(qbias)`；不能只看真实图片的峰值就声称 INT32 安全。模型某些 3×3 卷积具有 112 输入通道，仅 INT8 全幅理论界 `112*9*32768*127=4,194,861,056` 已超过 signed INT32，尚未计 bias。B 如采用更窄累加器，必须用该交付逐通道实际权重证明所有部分和及 bias 不溢出；不得采用溢出回绕。signed 扩展、DSP 级联截断、负数舍入均需单独对齐 Golden。

## 4. 参数包

导出目录包含 `manifest.json`、`graph.json`、`parameters.bin`；使用校准定标时还包含完整 `scale_config.json` 及其清单哈希。格式版本为 `griddehaze-fixed-v1`。以下位置为相对导出目录，不绑定用户电脑绝对路径。

- `parameters.bin` 各张量从 **64 字节对齐的文件偏移**开始；padding 为 0；各张量的有效字节数不包含尾部 padding。64 字节是本候选文件包装约定，不是已获 B 确认的 AXI/DMA 对齐要求。
- manifest 的 `parameters` 列表逐张量给出 `name`、`dtype`、`shape`、`layout`、`offset`、`nbytes`、`frac` 和 `sha256`。按 manifest offset 和长度读取，不自行以参数个数猜下一张量地址；dtype 使用 `int8`、`int16` 或 `int64` 字符串，`byte_order=little`。
- 普通卷积原生 OIHW，偏移 `(((o*I+i)*KH+ky)*KW+kx)`；转置卷积原生 IOHW，偏移 `(((i*O+o)*KH+ky)*KW+kx)`；乘每元素字节数后加该张量 offset。不得将转置卷积误当 OIHW。
- 权重按输出通道定标。普通卷积输出轴为 0；转置卷积输出轴为 1。bias 为 signed INT64 小端，长度 O，每通道分数位 `Fin+Fw[o]`，其中 Fin 必须取当前卷积真正的前驱节点 F；graph 的 `requantization_shift[o]=Fin+Fw[o]-Fout` 明确输出重定标。
- learned coefficient 以 signed INT16 小端存储，分数位见 manifest。graph 使用的通道 slice 单独标识；同时保留完整原始 coefficient 的量化导出以追踪未使用条目，不能据此新增原网络没有的计算。
- manifest、graph 和参数二进制是整体。更换源码、权重、F、权重位宽、舍入规则、图拓扑或文件包装必须生成新身份；装载方先校验身份和每个文件的字节数/哈希，再执行。

不规定物理 DDR 起始地址。B 可以转换到硬件专用 lane/block 排列，但必须额外交付映射版本与转换后的 manifest，并通过解码回原始逻辑张量逐元素一致检验。不能只保留新硬件包而丢弃可追踪的标准包。

## 5. 中间张量容量和内存生存期

逻辑张量都为连续 NCHW INT16，容量 `2*N*C*H*W`；不包括硬件行 padding、burst 对齐、双缓冲或累加器空间。上层、中层、下层基本通道数分别为 16、32、64；dense 拼接最大通道数分别为 80、96、128。720p 上层单个 16 通道平面为 29,491,200 字节（28.125 MiB）；上层最大 80 通道拼接为 147,456,000 字节（140.625 MiB）。输入与网络输出各 5,529,600 字节。

执行顺序与依赖以 graph 为准。消费者尚未读完之前，不得覆写输入；`output_like` 依赖只需要形状时可保留元数据。cat 可采用只读分段寻址避免实际复制，前提是卷积逻辑通道顺序不变。ReLU 可原地执行，但如需比较其前驱 Golden，应先保存前驱快照。A 的 Python/NumPy 参考运行内存、无复用逻辑张量总容量和 B 的峰值 DDR scratch 是不同数字。

`python -m griddehaze_fixed.plan --package <导出目录> --height 720 --width 1280 --out <新报告.json>` 可静态生成逐节点 shape、INT16 字节数、birth/last_use、独立 shape_last_use、转置卷积 output_padding 和理想及时释放情况下的峰值。该模型的 720×1280 静态图包含 320 个节点，假定 cat 全部实际物化时，峰值同时存活 INT16 为 353,894,400 字节；所有输出均不释放则共 8,019,763,200 字节。675×1280 的峰值为 331,816,960 字节。原始证据在 `outputs/griddehaze/audit_runs/shape_*.json`，均明确 `inference_executed=false`。这些数字不包括行 padding、地址碎片、双缓冲、INT64 输入提升或后端临时内存；报告单独列出 INT64 输出累加器整图和单行容量，不表示已批准硬件分配。

该版本未冻结硬件缓冲区别名和峰值 DDR 计划。B 应按每节点生产/最后消费时刻提交内存计划，列出每个地址、长度、对齐和可复用范围。空间分块需要完整网络感受野和上/下采样相位分析，并与完整图 Golden 比较所有块边界；不得沿用 TinyRestore halo=6。

## 6. Golden 与故障定位

Golden 裸文件扩展名 `.raw`，每个张量有同名 `.json` 描述形状、dtype、字节数和 SHA-256。整数节点为 `<i2`、C-order NCHW，对应**执行该 op 后**的结果；conv/deconv 为重定标饱和后、独立 ReLU 前；mulcoef 为乘法重定标饱和后；add 为加法饱和后；cat 为完整顺序。节点位于 `nodes/`；最终网络结果为 `output.raw`，独立显示结果 `display_rgb8.raw` 为 `|u1` HWC。FP32 参考单独保存，不能作为整数逐元素通过的替代品。

比较前先核对模型/导出身份、输入哈希、H/W/C、dtype、字节数、分数位和 graph 节点 ID。按 graph 执行顺序比较各节点，报告首个不一致节点、N/C/Y/X、两边 raw 值、最大绝对误差、平均绝对误差、差异元素数，以及两边原始文件 SHA-256。对相同整数语义要求 **每元素精确相等**；浮点与整数的量化误差另外统计，不设未经负责人确认的质量验收阈值。

本地用户数据由 `griddehaze_fixed.data` 安全提取原图字节并生成 `outputs/griddehaze/userdata/splits.json`。来源为用户提供的 Fog.zip（300 图）和 Rain.zip（200 图）；检测标注没有作为恢复真值使用。按 `SHA256(类别+冒号+ZIP成员名)` 排序，分为 Fog30/Rain20 校准（47 个不同 SHA）、Fog10/Rain5 验证（15 个不同 SHA）、Fog260/Rain175 保留未测（420 个不同 SHA）；认可的 `Fog/foggy-001.jpg`（675×1280）只在验证集。16 组完全相同字节的图像保持同一划分，没有跨划分的原始文件 SHA 泄漏；近重复、相机和场景重叠尚未审核，所以 `independent_test` 键只是保留文件列表，**不构成已证明独立的测试集**。校准过程中的裁剪、margin 和分数位选择由该次 `scale_config.json`/校准报告继续记录；小裁剪结果不代表完整图片质量。

`validate_split.py` 已对上述 15 张验证图各取一个明确记录的中心 64×64 裁剪，不拉伸，分别执行 `run_003/w16cal` 和 `run_003/w8cal`。15 次官方 FP32 forward 与显式图最终输出均逐元素一致。16-bit 权重候选的平均逐图 MAE 为 0.00198179165573593，最大逐图 MAE 为 0.0044323884236898，所有输出的最大绝对误差为 0.00914624333381653；8-bit 候选对应为 0.00356314959842873、0.0113474518075236、0.0348135232925415。两候选在全部 320 节点×15 裁剪上均无饱和。以上误差均在网络输出真实值尺度上计算，不是恢复真值指标，也不构成官方质量阈值或完整图片验收。原始报告、每图输入/输出/FP32/display 裸文件及 320 节点的 SHA/分布/饱和统计位于 `outputs/griddehaze/validation15/`，执行记录位于 `outputs/griddehaze/commands/validation15patches/`。验证脚本未改变定标或权重。

建议 B 依次对齐：负数/舍入/饱和算子→首层卷积→dense RDB→奇数尺寸 deconv→系数融合→完整 33×47→真实图→完整 675×1280、720×1280→最终 FPGA 整网。重复生成的同一整数向量应哈希相同。不同身份即使最终图片看起来相近，也不得混用 Golden。

## 7. wzh / lzm 待确认清单

1. wzh 确认可支持的**逐节点**激活 F、8/16-bit 权重候选、bias/累加位宽，以及 learned coefficient 精度。当前逐节点方案改变了早期统一 Q10 候选的尺度传递，cat/add/ReLU 也可能需要重定标，不能只修改卷积 shift；候选数值改变需 A 重导出并重新测量误差。
2. wzh 确认原生 OIHW/IOHW 包能否直接使用；若转换，给出 lane/tiling/对齐转换方案和回读证明。
3. wzh 给出最大 H/W、batch=1 限制、DDR 可用预算、每节点生存期与峰值 scratch、是否分块及 halo/相位验证。
4. wzh 与 lzm 冻结新模型 ID、寄存器 ABI 版本、input/output/weights/scratch 地址和长度、DMA 对齐/可寻址范围、START/DONE/IDLE、错误码和超时后缓冲区 ownership；不得复用旧 task=1 语义制造误识别。
5. 保留现有 coherent DMA、锁及平台边界；SMMU、共享复位和 DT/XSA 的变更属于 B/软件侧联调，不由 A 猜测或改写。
6. 用户/负责人确认认可雾图及浓雾、逆光、夜景边界图上的定点视觉效果；已取得本地 Fog/Rain 原图，但缺少清晰恢复配对真值。真实图片只报告 FP32→整数误差，不将对原图的 PSNR 当作恢复质量。
7. 负责人确认上游源码和权重的使用/再分发许可范围，以及本次交付的传输渠道。此处未联系或向任何队友发送文件。

以上确认完成前，本文件和对应数值包应标为 **A 组候选交付 / 硬件未验证 / 接口未共同签认**。B 可据此开始算子资源评估和逐元素仿真，不据此宣告新版本达到已报告的 34 FPS。
