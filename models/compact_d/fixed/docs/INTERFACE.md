# D INT16 数值合同：A v1

日期：2026-10-25。依据远程 `feat/software@a19c5f6`。本合同冻结 A 的数值与文件格式；B 的寄存器、AXI、DMA、DDR 实体地址、时钟和镜像身份仍须 wzh/lzm 确认。不能用旧 Grid 驱动直接启动 D。

## 1. 身份与边界

- 模型：D / `compact_residual_trial`，8 通道、3 个残差块、8 层普通卷积、3,947 参数（3,888 权重 + 59 bias）。原检查点 step600，未训练、改写或替换。
- 原始检查点 SHA256：`0d2678ba533a83c797d5b7a2a922461440fa47f93043525a9165f0a1f9fc28fc`。
- 正式 A 数值 bundle：`2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a`，格式 `compact-d-int16-v1`。图中22个节点均明确 `dtype=int16-le, layout=NCHW`；input 的 `range` 是整数范围，`real_range` 是归一化实值范围。
- `package/manifest.json` 固定图、尺度、参数、生产代码的 SHA。更改任一数值语义、参数或生产代码必须重新导出、生成 Golden，并使用新 bundle；不沿用此 ID。
- 整数网络执行不依赖 PyTorch。独立 C++ oracle 只依赖 C++17 标准库。导出与 FP32 评估需要 PyTorch。

## 2. 输入、图与尺寸

输入 RGB8 先 EXIF 转正、转 RGB，等比缩小至 1280×720 内，不裁切、拉伸或放大小图。软件与现有 `predict.py` 一致，Pillow LANCZOS。合同接受 batch1、`1<=H<=720, 1<=W<=1280`；这只是数值支持范围，B 的尺寸支持范围需要单独确认。

正式数值输入：连续 NCHW、little-endian signed INT16，RGB 平面顺序，offset=`((c*H+y)*W+x)*2`。合法范围 `[-16384,16384]`，F14，实值 `q/16384`。

从 RGB8 像素 p 计算 `qin=RHAZ((2*p-255)*16384/255)`。这是对冻结 FP32 归一化的整数近似，不能把 RGB8 直接解释成 INT16 或除以256。图内零填充是**归一化后整数0**，不是黑色 RGB8 对应的 -16384。

所有卷积都是 PyTorch cross-correlation：OIHW、不翻转核、3×3、stride1、padding1、dilation1、groups1、有 bias、输出尺寸不变。没有 BN、attention、concat、deconv。

| 顺序/节点 | 输入 | C | F | INT16 存储 bytes |
|---|---|---:|---:|---:|
| 00 input | RGB 归一化 | 3 | 14 | 6HW |
| 01 stem.conv / 02 stem.relu | input / stem.conv | 8 | 13 | 每节点16HW |
| 03 block0.conv0 / 04 block0.relu0 | stem.relu / conv0 | 8 | 13 | 每节点16HW |
| 05 block0.conv1 / 06 block0.add / 07 block0.relu1 | relu0 / stem.relu+conv1 / add | 8 | 13 | 每节点16HW |
| 08 block1.conv0 / 09 block1.relu0 | block0.relu1 / conv0 | 8 | 13 | 每节点16HW |
| 10 block1.conv1 / 11 block1.add / 12 block1.relu1 | relu0 / block0.relu1+conv1 / add | 8 | 13 | 每节点16HW |
| 13 block2.conv0 / 14 block2.relu0 | block1.relu1 / conv0 | 8 | 13 | 每节点16HW |
| 15 block2.conv1 / 16 block2.add / 17 block2.relu1 | relu0 / block1.relu1+conv1 / add | 8 | 13 | 每节点16HW |
| 18 head.conv | block2.relu1 | 3 | 14 | 6HW |
| 19 input.affine | input | 3 | 14 | 6HW |
| 20 output.add / 21 output.relu | input.affine+head.conv / add | 3 | 14 | 每节点6HW |

720p 单个 C8 图是14,745,600 bytes，单个 C3 图5,529,600 bytes。22个语义节点不要求22份完整DDR分配；ReLU 可原位/融合，具体存活期与银行布局由 B 设计。所有22节点的语义结果都要保持可比对。

## 3. 权重和 bias

`parameters.bin` 共8,280 bytes。权重 INT16-LE，OIHW，地址 `woff+2*(((co*Cin+ci)*3+ky)*3+kx)`；bias INT64-LE，输出通道顺序，地址 `boff+8*co`。各张量起始64-byte对齐，padding字节0。64-byte是文件布局约定，不代表已确认DMA要求。

| 卷积 | weight offset / bytes | bias offset / bytes | Fw（按输出通道） |
|---|---|---|---|
| stem | 0 / 432 | 448 / 64 | 17×8 |
| block0.conv0 | 512 / 1152 | 1664 / 64 | 17,18,17,17,17,17,17,17 |
| block0.conv1 | 1728 / 1152 | 2880 / 64 | 17,17,17,18,17,17,17,17 |
| block1.conv0 | 2944 / 1152 | 4096 / 64 | 17×8 |
| block1.conv1 | 4160 / 1152 | 5312 / 64 | 17×8 |
| block2.conv0 | 5376 / 1152 | 6528 / 64 | 17,17,17,17,17,18,17,17 |
| block2.conv1 | 6592 / 1152 | 7744 / 64 | 17×8 |
| head | 7808 / 432 | 8256 / 24 | 20×3 |

每输出通道选择可不发生权重裁剪的最高二进制 Fw（上限30），`qw=RHAZ(w*2^Fw)`；`qb=RHAZ(b*2^(Fin+Fw))`。使用冻结 FP32 参数转 FP64 后乘2的幂，Fraction独立审计逐值一致。完整 dtype/shape/每张量SHA/F/重定标shift均以 manifest 和 graph 为机器入口，不从本文手抄生成。

## 4. 精确算术次序

RHAZ 为最近数、半数远离零：`RHAZ(-1.5)=-2`。所有中间先宽位运算，signed clamp 到 `[-32768,32767]`。禁止依赖 C++ 负数右移/有符号溢出的未定义行为。

1. 卷积：`acc=qb[co]+sum(qx*qw)`，参考INT64；shift=`Fin+Fw[co]-Fout`；`qconv=sat16(RHAZ(acc/2^shift))`。**先重定标并饱和，才进入ReLU或残差加法。**
2. ReLU：`max(q,0)`，不改变F。允许与卷积/加法融合，但必须保留前一步的数值边界。
3. 加法：各输入先以RHAZ转换至目标F，宽位相加，再sat16。三个block两支都是F13，无额外尺度转换。不能在相加前把分支裁到非负。
4. head：有符号F14，可负，不能加ReLU或提前裁到[0,1]。
5. 原图旁路：`qbase=sat16(RHAZ((qin+16384)/2))`，使用**已经量化的input**，不能改为重新从RGB8归一化，否则会改变1LSB处的Golden。
6. 末端：`qsum=sat16(qbase+qhead)`，再`qout=max(qsum,0)`。F14输出实值允许大于1，不能把16384作为网络饱和上界。
7. 显示：网络完成后裁到[0,16384]，计算`q*255/16384`，最近偶数舍入（ties-to-even），输出 RGB HWC uint8。这里的舍入与RHAZ不同。

## 5. 溢出证明与优化许可

对认证整数参数，每输出通道 `B=32768*sum(abs(qw))+abs(qb)`，覆盖任意signed INT16输入、全部空间位置、零填充及每个部分和。各卷积足够的 signed 位宽依次为35、37、37、36、36、37、36、36；全图统一37位累加可保证与INT64参考一致。最大界38,311,644,308，小于`2^36-1`。**INT32不安全。** 每通道可复算证明和bias在`overflow_proof.json`。

乘积用足够signed位宽，最终加bias和部分和不能截断。bias文件INT64只规定存储，B可在证明条件下安全窄化。此证明不声称所有可能图像永不激活饱和；饱和属于合同。28组实际验证没有发生饱和。

保持精确的候选：重排/平衡无溢出整数求和、37位认证累加、权重常驻、输出通道展开、行缓存、保留量化边界的ReLU融合、保留原分支值及次序的残差FIFO、数据搬运合并。改INT8、少层/少通道、裁范围、删旁路、改舍入或移动饱和边界均会产生新数值版本，必须双方评估再决定。

## 6. Golden 与 B 接入顺序

`golden/<case>/report.json` 包含输入身份、bundle、尺寸、22节点dtype/F/SHA/极值/饱和统计。小图和720p模式图保存所有 `<index>_<node>.i16`；12张真实图保存全部节点SHA和原始最终输出，中间原始张量可复跑生成，不能声称都已打包。`input.i16`是硬件数值输入，`input.png`供查看，`fp32.png/int16.png/difference_x32.png/comparison.png`为效果证据。

先核对 bundle/参数文件SHA，再用 1×1、1×7、7×1、2×3、8×8、33×47 和颜色/极值/随机图验证零填充与符号。22节点全一致后再做720p。纯文件比较命令：

```powershell
python -m models.compact_d.fixed.compare --package package --golden golden/random_8x8 --actual FPGA_output.i16 --nodes FPGA_nodes --bundle-id 2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a --report compare.json
```

若只检查最终输出，省略`--nodes`。比较器不证明文件来自真板，B须另提供镜像SHA、运行来源和计时记录。

## 7. 必须由 B/lzm 确认的硬件合同

待确认：模型ID与硬件ABI版本、寄存器表、最大尺寸与奇数尺寸、NCHW或内部重排、地址位宽/对齐、DMA长度/stride、输入输出/参数/scratch所有权、缓存一致性、结束与idle条件、错误码、超时及reset后未完成AXI写入处理、计数器、时钟/复位、HDMI显示路径。A不分配正式AXI端口、寄存器或DDR物理地址，不覆盖当前可运行镜像。未经上述确认，不把此数值bundle称为已集成硬件ABI。

Vivado布局布线资源、routed时序、DDR实效、核心/端到端延迟及实际FPS必须由B在对应D镜像和真板上验证。旧Grid、C8、低照CNN、Bilinear、Curve结果都不能替代。
