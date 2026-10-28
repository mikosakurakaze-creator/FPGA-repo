# KV260 低照度 + Compact D 联合接口合同 v1

冻结日期：2026-10-28。目标为同一张 **1272×720** RGB 原图，原图分支 I、低照度分支 L、Compact D 分支 D 的逐元素融合。本目录只承担任务 1–3；融合 IP、最终 AXI/DDR 集成、布局布线与硬件交付包由后续任务完成。本文中的联合地址是保留合同，不表示已实现对应 IP 或已生成联合 bitstream。

## 1. 版本与数值实现冻结

低照度硬件实际交付不在 `feat/software` 或 `origin/weather_fpga_integration` 的 `fpga/` 目录中（两分支此目录仅有占位 README），而在当前 `codex/curve-fp32-baseline` 工作树及已交付外部构建目录中。当前工作树 HEAD 为 `cfa4e3d103c237ebdbd4591d357c343e0a146ed2`；正式硬件交付配方引入提交为 `67c0929a10eac2f4874c84793c5b7d4a6a437b52`。不得因此切换、合并或改写队友分支。

| 核 | 冻结版本 | 实际 IP 源 |
| --- | --- | --- |
| 低照度 CNN | `xilinx.com:hls:zero_dce_cnn_top:1.0`，revision `2114810448`，V1.2 write-credit | `E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/` |
| Bilinear | `xilinx.com:hls:bilinear_fixed16_buffered:1.0`，revision `2114800369` | `E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/stable_ip_repo/bilinear/` |
| Curve | `xilinx.com:hls:curve_image_fixed16:1.0`，revision `2114799122` | 同上 `stable_ip_repo/curve/` |
| Compact D | `xilinx.com:hls:compact_d_top:1.0`，revision `2114844623` | `origin/weather_fpga_integration@8c202508d267151c4ae034975b17947818be7865` 下 `compact_d_fpga/board/k26_compact_d_20261025/` 的已发布 IP |
| Compact D 数值 A | `origin/feat/software@9ef5fafa90ffd3c8ededbf22b3cf8ccb3bf16fce` | A 侧 INT16 Golden 与对应发布的参数；不混用后续其他模型。本地 `feat/software` 仍在旧提交 `f9fd1ea595734076f1e4d06283c44967b2f13ec9` |

SHA256（完整 64 位）：

| 对象 | SHA256 |
| --- | --- |
| CNN `component.xml`，本次现场核验 | `7e046bd557997e8a8b55b466ee9a76b8c3c321f1435df2879a8bf92a45f54ecd` |
| Bilinear `component.xml`，本次现场核验 | `1c7ab9696185d78baad702d28d8c7c8ba1671b79c4dd5665f306a57d591b2597` |
| Curve `component.xml`，本次现场核验 | `72a3f2345b988f321fd3f0f20e4a8a8fc0996fcb00e8c001fc157e3b3e88a518` |
| CNN release identity | `a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9` |
| Compact D `compact_d_ip.zip` | `7d276942544f3785bde9267484da6d08bbae819cd46b8bb8e7214ea8a5603bc4` |
| Compact D 数值 A bundle | `2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a` |
| Compact D 参数 | `b30ccd73ad10a685db4c591d3c4a31286178bc80be8e65ff3801364458706e57` |

CNN write-credit 是正式 HLS export 上仅修改三个 writer 的 RTL 调度层版本。仅重新综合 r4 C++ 不会重建此版本；须使用冻结 package 或 `fpga/ip/cnn_v1_2_writecredit/README.md` 的锁定配方。禁止选择未验收的 30FPS 候选替代。Bilinear/Curve 保持既有数值类型与运算点。Compact D 原始发布包与参数均保留。

## 2. 统一图像格式和坐标

- 固定 `N=1,C=3,H=720,W=1272`，宽高不交换；每帧 915,840 个二维像素、2,747,520 个标量。
- RGB 通道顺序、NCHW 平面存储、C contiguous；每元素小端 signed INT16 二补码；值为 `raw/16384`，零点为 0。字节偏移为 `2*((c*720+y)*1272+x)`。
- 每帧 **5,495,040 字节**，每通道 1,831,680 字节，每行 2,544 字节；无 row/plane padding，无 packet header。
- Q14 存储范围是 `[-32768,32767]`，实数范围 `[-2,2-2^-14]`。**Q14 不等于归一化区间限制**；L 和 D 适配不额外裁剪至 `[0,1]`。
- 新入口原图为 1272×720、RGB、HWC、每通道 UINT8，字节偏移 `3*(y*1272+x)+c`，总计 2,747,520 字节。输入已完成图像解码；不在 IP 中解 JPEG、做 gamma 或颜色空间转换。
- 不隐式接受 1280 宽相机帧，不自动裁剪或缩放。源帧若为其他尺寸，由上游明确生成 1272×720 后再进入本合同。

## 3. 原图到三路入口的转换

记 `RHAZ(n/d)` 为有符号最近舍入，中点远离零；`RNE_shift(s,k)` 为有符号最近偶数舍入 `s/2^k`。

### I：原图融合与 Curve 输入

对原图 UINT8 标量 `p∈[0,255]`，直接计算：

`I_raw = RHAZ(p*16384/255)`。

输出 `[0,16384]` 的全分辨率 RGB NCHW INT16 Q14。分母 255 是奇数，本式和下述 D 输入式均不会恰好落在半整数，因此对这两个 RGB8 公式 RNE 与 RHAZ 结果一致。Curve `model_input` 与融合 I 可以只读别名同一缓冲。

### D：Compact D 模型输入

直接从同一 UINT8 标量计算：

`D_input_raw = RHAZ((2*p-255)*16384/255)`。

输出 `[-16384,16384]`、全分辨率 RGB NCHW INT16 Q14，对应归一化 `2p/255-1`。**不能用已经量化的 `2*I_raw-16384` 代替**：两次量化的次序不同，会出现逐元素差异。D 的输入并不是原图 `[0,1]` 编码。

### 低照度 CNN 输入

先得到上述 full Q14 I，再取每个通道的四个中心采样点：

`CNN_raw[c,y,x] = RNE_shift(sum(I_raw[c,12*y+dy,12*x+dx] for dy,dx in {(5,5),(5,6),(6,5),(6,6)}),2)`。

输出 `[1,3,60,106]`，19,080 个 Q14 标量、38,160 字节。该下采样规则与 `fpga/perf/v1_2_system_tb/prepare_golden.py`、`fpga/docs/kv260_v12_software_handoff.md` 冻结的前级一致；不是 12×12 平均池化，也不是 align-corners 下采样。CNN 核内部不执行这一步。

旧 night_01 Golden 的 full Q14 从实际 FP32 张量按 `floor(x*16384+0.5)` 产生；新 RGB8 入口不能被描述为逐位重建该 FP32 源。任务 3 应分别验证新 RGB8 公式和旧 full-Q14/CNN 下采样合同。

## 4. 现有低照度链路

| 阶段 | 输入 | 输出 | 数值合同 |
| --- | --- | --- | --- |
| CNN | `[1,3,60,106]` signed INT16 Q14 + 冻结模型 | `A_low`，同 shape、Q14 | 逐通道重定标、最终 LUT Q15→Q14 均使用冻结 signed RNE 与 INT16 饱和 |
| Bilinear | `A_low`，`height=60,width=106` | `A_full [1,3,720,1272]` Q14 | 放大 12 倍，align-corners；内部 Q32 坐标及冻结 cast 点；输出类型 `ap_fixed<16,2,AP_RND,AP_SAT>` |
| Curve | 全分辨率 I 和 `A_full`，`count=2747520` | L，统一 shape 与 Q14 | 每元素八轮 `x=x+a*(x*x-x)`；每轮按原 `AP_RND`（中点向 +∞）/INT16 饱和；无额外 `[0,1]` clamp |

L 已为统一编码，适配为 raw bit-copy 或只读缓冲别名；不能经 float 重量化。Bilinear/Curve 内部 `AP_RND` 与 CNN/新融合的 RNE 是不同规则，不因统一接口而改写模型。

低照度模型/临时缓冲：

| Buffer | Bytes | 编码/生命周期 |
| --- | ---:| --- |
| CNN input | 38,160 | INT16 Q14；CNN 完成前不可覆盖 |
| A_low | 38,160 | INT16 Q14；Bilinear 完成前不可复用 |
| A_full | 5,495,040 | INT16 Q14；Curve 完成前不可复用 |
| I / Curve model_input | 5,495,040 | INT16 Q14；Curve 和融合均完成后才能复用 |
| L / enhanced | 5,495,040 | INT16 Q14；融合完成前不可复用 |
| CNN workspace | 2,442,240 | 六个 `[32,60,106]` INT16 skip；每 slot 407,040 字节；F=[14,14,14,12,13,14]，并非统一 Q14 |
| weights_int8 | 10,075 | signed INT8，14 层 OIHW，不能重量化 |
| bias_int32 | 1,944 | 486 个 little-endian INT32；fraction 由原数值协议决定 |
| weight_frac | 486 | 每输出通道一个 signed INT8 fraction |
| tanh_lut_q15 | 8,194 | 4,097 个 INT16 Q15；Q8 index -2048…2048 |

workspace slot byte offsets 为 0、407040、814080、1221120、1628160、2035200。单一 workspace 不可并行服务两个 CNN。模型数据 hash 见 `fpga/docs/kv260_v12_register_map.json`。

## 5. Compact D 输入输出和限制

- `compact_d_top` 使用两个 DDR master `gmem_in/gmem_out`，AXI 数据宽度 32 bit、地址宽度 64 bit；AXI-Lite 为 32 bit data/7 bit address。
- 输入、输出均为 RGB NCHW、little-endian signed INT16、F=14，无 stride/row padding。输入合法范围 `[-16384,16384]`；D 最终 ReLU 输出 `[0,32767]`。输出转统一格式直接 bit-copy/别名，**不把大于 16384 的值提前裁剪**。
- 支持 `1≤H≤720,1≤W≤1280` 的合法 shape，1272×720 在范围内；runtime 配置必须为 `height=720,width=1272`。发布 1280 宽 Golden 的长度与本次不同，不可截取其一段作为 1272 宽网络输出 Golden。
- 1272×720 的每个 input/output 缓冲均为 **5,495,040 字节**；两个缓冲完整区间不得重叠。建议各基址 64-byte 对齐，完整 `[base,base+size)` 必须落在 D 已冻结 DDR LOW `[0,0x80000000)` 可寻址窗口内。
- input 在 D 完成前不可改写，output 在融合完成前不可复用；模型内部片上 URAM 不能与低照度按“分时”假设共享。
- 调用前 idle；`cookie=0x44433031`；禁止 auto_restart。完成需同时检查 `ap_done/ap_idle` 和 `ap_return=0`；`-1` 表示 cookie 不符、`-2` 表示非法 shape。非法调用不产生有效输出。
- timeout 不提供安全 abort/drain 协议；不能直接复用被写缓冲。异常恢复需由后续系统任务定义，完成 reset 与 outstanding 事务静止证明后方可复用。

## 6. AXI-Lite 寄存器合同

所有偏移为 IP 基址相对偏移。64-bit 指针必须分别写完整 low/high word，不能把 CPU 虚拟指针当总线地址。

| 核 | 参数 | Low / high 或 scalar 偏移 |
| --- | --- | --- |
| CNN | input_q14 | `0x10/0x14` |
| CNN | weights_int8 | `0x1C/0x20` |
| CNN | bias_int32 | `0x28/0x2C` |
| CNN | weight_frac | `0x34/0x38` |
| CNN | tanh_lut_q15 | `0x40/0x44` |
| CNN | a_low_q14 | `0x4C/0x50` |
| CNN | workspace_int16 | `0x58/0x5C` |
| Bilinear | parameters_lowres | `0x10/0x14` |
| Bilinear | parameters_fullres | `0x1C/0x20` |
| Bilinear | input_height / input_width | `0x28` / `0x30`，值 60 / 106 |
| Curve | input_r | `0x10/0x14` |
| Curve | parameter_r | `0x1C/0x20` |
| Curve | output_r | `0x28/0x2C` |
| Curve | count | `0x34`，值 2,747,520 |
| D | ap_return | `0x10`，signed INT32 |
| D | input | `0x18/0x1C` |
| D | output | `0x24/0x28` |
| D | height / width | `0x30` / `0x38`，值 720 / 1272 |
| D | cookie | `0x40`，值 `0x44433031` |
| D | work_cycles | `0x48/0x4C`；`0x50` valid，读清 |
| D | input_cycles | `0x58/0x5C`；`0x60` valid，读清 |
| `joint_rgb8_prepare` | ap_return | `0x10`，signed INT32 |
| `joint_rgb8_prepare` | rgb / I | `0x18/0x1C` / `0x24/0x28` |
| `joint_rgb8_prepare` | D_input / CNN_input | `0x30/0x34` / `0x3C/0x40` |
| `joint_rgb8_prepare` | cookie | `0x48`，值 `0x4A503031` |
| `joint_q14_copy` | ap_return | `0x10`，signed INT32 |
| `joint_q14_copy` | src / dst | `0x18/0x1C` / `0x24/0x28` |
| `joint_q14_copy` | cookie | `0x30`，值 `0x4A433031` |

共同 `ap_ctrl_hs`：`0x00` 的 bit0=start（握手清）、bit1=done（读清）、bit2=idle、bit3=ready（读清）、bit7=auto_restart。`0x04` GIE；`0x08` IER done/ready 位；`0x0C` ISR 为 toggle-on-write。当前三低照度核与 D 独立发布设计均未接 PS 中断，使用有界轮询；启动前配置完整参数并完成内存/MMIO排序，单次写 start，不能循环写 start。读取 done 后不得依赖第二次读取仍为 1。

现有低照度 driver header SHA256：CNN `3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362`；Bilinear `8eee503594c8e381c1fd361e2014ddd9314d158dbb96d0e7aea2ab68ebf065a3`；Curve `8c145a90188f440acd751744ee562d1537e609d3f03d82779c9ca721a409660c`。

联合控制窗口均保留 64 KiB：

| 基址 | 用途 | 当前状态 |
| --- | --- | --- |
| `0xA0000000` | Bilinear | 既有合同 |
| `0xA0010000` | Curve | 既有合同 |
| `0xA0020000` | CNN | 既有合同 |
| `0xA0030000` | `joint_rgb8_prepare` | 新保留；固定 720×1272，不提供 runtime 尺寸参数 |
| `0xA0040000` | 三路融合 | 新保留；任务 4 实现 |
| `0xA0050000` | Compact D | 与 D 独立发布原基址一致；联合 BD 须实际分配 |
| `0xA0060000` | `joint_q14_copy`，L 分支 | 新保留，最终可在生命周期允许时选择别名零复制 |
| `0xA0070000` | `joint_q14_copy`，D 分支 | 新保留，最终可在生命周期允许时选择别名零复制 |

两个适配 top 使用同样的 `ap_ctrl_hs` 完成协议与 cookie 校验；成功 `ap_return=0`，cookie 错误返回 `-1` 且不访问图像缓冲。`joint_rgb8_prepare` 的 RGB 源与 I/D_input/CNN_input 四个完整内存范围须互不重叠。低照度/D 的 raw-copy 不做裁剪或重量化；copy 的源与目标不得部分重叠，别名方案应跳过 copy 调用。适配器寄存器以实际导出 driver 再核对；融合偏移须在任务 4 具体导出后补充，不能从其他 HLS 核推测。寄存器 ABI 变更必须更新本合同并重跑验证。

本次两个适配 IP 已实际综合导出，上表所有 offset/bit width 已逐字段通过 driver 核对，四个 prepare 指针及两个 copy 指针均为 64 bit。Prepare driver SHA256=`8d7a7fc50171de1a4ff162e30e367bbc7d49eb580ed210c26dbdf74cdf76b52a`；copy driver SHA256=`7a79800be7c5b66e30ec6fcdb65f538c2b4be36ad44e2561642c422991a2b687`。可复核记录见 `../evidence/adapter_evidence.json`。

## 7. 时钟、复位和 DDR

| 范围 | 已发布时钟 | Reset / 连接 |
| --- | --- | --- |
| 低照度三核 | PS PL0 100MHz，10ns；HWH 99,999,001Hz | `pl_resetn0` 经 `rst_ps_100m`，外部 ACTIVE_LOW；IP `peripheral_aresetn`，SC `interconnect_aresetn`；IP `ap_rst_n` 低有效 |
| D 独立发布设计 | 目标 200MHz；HWH 199,998,001Hz | `ap_rst_n` 低有效，在其时钟域释放；原互连同域 |
| 联合资源检查 | 由独立综合工程报告实际时钟 | 不得把 D 独立 200MHz 结论或低照度单系统 100MHz routed timing 当成联合时序结论 |

现有低照度：HPM0→控制 SC；CNN input/output/workspace→HP0，模型→HP1；Bilinear→HP2，Curve→HP3；11 个 HLS DDR master 数据 32 bit，经 SC 到 PS HP 128 bit。D 独立设计 input→HP0、output→HP3。联合设计须在共享 HP 上增加仲裁连接，不能将两个 master 直接短接。若最终保留不同频率，AXI 控制、DDR 数据、完成状态及 reset 释放均需显式跨域；单次综合试验统一降频不改变既有 IP 数值合同，但会改变性能预期。

统一分配采用 **64-byte 对齐**（满足低照度已验证至少 16-byte 对齐）；每个完整缓冲范围必须证明不重叠且由板端软件分配。不得复用历史 JTAG scratch 或仿真 BFM 物理地址作为最终 DDR 固定地址。模型读缓冲可长期只读共享；I 可供 Curve/融合只读别名，L/D 输出可直接供融合只读，不要求无意义的 DDR copy。Cache flush/invalidate、总线地址转换与内存屏障由最终驱动负责。

## 8. 三路融合数值合同（交接任务 4）

本节是本次冻结的新接口选择；不表示融合 IP 已完成。

- 软件配置 `w_I,w_L,w_D` 为 **unsigned 16-bit 存储、15 位小数的定点原码**，每个原码合法区间 `[0,32768]`，精确实数值为 `w/32768`。值 32768（1.0）必须可表示；不可使用 signed INT16 存权重。
- AXI-Lite 的每个权重配置字段须接收完整 unsigned 32-bit word，先检查高位与范围，再作为上述 16-bit 原码使用；不能在检查前截成 16 bit，使 `0x00018000` 等非法写值被误认为合法权重。
- 用至少 32-bit 无符号加法检查 `w_I+w_L+w_D==32768`，同时检查每个权重不超过 32768；不做隐式归一化，不把非法值截断成合法值。
- 启动时将三个权重锁存为同一帧快照，在任何图像 DDR 访问前完成检查。非法权重返回明确错误状态，**不发出图像读写事务**，输出缓冲保持原内容。
- 对每个相同 `(c,y,x)` 的 signed Q14 输入，用 signed 64-bit 累加：`acc=I_raw*w_I+L_raw*w_L+D_raw*w_D`，不逐项舍入，不提前裁剪分支输出。
- `rounded=RNE_shift(acc,15)`；最终 `F_raw=min(16384,max(0,rounded))`。输出仍为统一 RGB NCHW INT16 Q14。输出到 UINT8/显示设备属于后续边界，不在融合中增加 gamma 或 RGB8 量化。
- 任务 4 必须覆盖：三组 one-hot、零分支、均衡/极端权重、正负中点的最近偶数、INT16 极值、上/下裁剪、非法和溢出权重、不发 DDR/输出未改、参数运行时改写不影响已启动帧。

## 9. 完成同步与缓冲所有权

同一个 frame_id 的 RGB8 源产生 I、D_input、CNN_input 后，允许 `CNN→Bilinear→Curve` 和 D 并行运行。Bilinear 只能在本帧 CNN 完成且 A_low 可见后启动；Curve 只能在本帧 Bilinear 完成且 A_full 可见后启动。

融合只在 **I_ready && L_done && D_done && 同一 frame_id && 全部状态成功** 后启动。不能用启动顺序、固定等待时间或上一帧残留 done 代替完成确认。L_done 需覆盖 Curve 写回完成，D_done 需覆盖 D output 写回完成且 return=0；如有后置 copy，ready 还必须包含 copy 完成。融合完成前禁止重用 I/L/D；软件消费完成前禁止重用融合输出。

单帧最小运行缓冲可别名 I 与 Curve model_input、L 与 enhanced、D 与 Compact D output；其余写缓冲禁止重叠。双缓冲/多帧需为每个生产者和消费者独立跟踪所有权；本次不声明已经验证并行带宽或多帧吞吐。

## 10. Golden、证据与验证边界

低照度旧 Golden 位于 `E:/HLS/kv260_three_module_v1_2_phase4/data/`；以下文件本次重新计算 SHA256，与旧 manifest 一致：

| 文件 | Bytes | SHA256 |
| --- | ---:| --- |
| `input_q14.bin` | 38,160 | `f23dd361f7fbc510df065c88ea39fa108154b3f20b68858eabdd0e7935aa5c25` |
| `model_input_q14.bin` | 5,495,040 | `7dbbd69b59de49b751c4b684a9d4fc7083e20d841a9a1e19897256badb7ffe56` |
| `expected_a_low_q14.bin` | 38,160 | `31abdd23520d32efe75928ef394017bd2f515b2805144a85735eebc9481dddd1` |
| `expected_a_full_q14.bin` | 5,495,040 | `ebfa58eafb70385af39b92b6c9ed2b81c3319ca63662ce002d1219051f8b2067` |
| `expected_enhanced_q14.bin` | 5,495,040 | `869e62a41010e047c3760aa6a614f0ff883566d52c3fbee273cf2a865f7eb951` |

`golden_manifest.json` SHA256=`154d79b6a1921013e86ddd9a8d916d7d88af477d0f6f3ac17515634a62d1edc4`；正式整数参考 `fpga/reference/fixed_point_v1/arithmetic.py` SHA256=`c631c22d1f46a445adfc7559676f9f8d2b4c0385a79b63491771be4ea9a4a751`。历史完整单帧 RTL 和诊断 bit 真板输出均记录全量 raw mismatch=0；本次未重跑模型/板测，见旧软件交接与板测摘要。正式 bit 与诊断 bit 不是同一文件，板测结论不能自动继承给正式或联合镜像。

Compact D 原发布 `validation/pattern_720p/` 是 **720×1280 数值 A 参考**：`input.i16` SHA256=`dd82498b9436f5d9a82594cd388ec541c47231424ba5e4440fe1b31493e79067`；`21_output.relu.i16` SHA256=`9fb174f8e230b1e3bb42779882b6138129566247a2595d52b869c04b3e5b473d`。D 历史 RTL/Cosim 只验证小图、奇数尺寸多次调用，以及 17×1280 活动输出；**完整 720p RTL 尚未完成**。不能把 1280 宽软件 Golden、联合资源综合或适配器逐元素验证写成 1272×720 D 核全链数值 PASS。

任务 3 新适配验证须单列：256 个 RGB8 编码的穷举、RGB/NCHW 布局与边界、完整 1272×720 所有 2,747,520 个标量、signed INT16 raw-copy 极值、旧 CNN 19,080 个下采样点，与独立整数 Golden 逐元素核对并保存输入/输出 hash。HLS CSim/综合、RTL cosim、联合全模型 RTL、最终上板分别记录，不能相互替代。

本次适配器 Native/CSim 已报告六个张量共 **13,756,680** 个标量，raw mismatch=0；另外穷举全部 256 个 RGB8 输入和全部 65,536 个 INT16 raw-copy 编码。旧 D 1280 宽 Golden 按每行抽取前 1272 列，仅可验证 copy 的编码和布局，不代表运行过 1272 宽 D 模型。新适配器详细输入/输出身份、实际命令与最终 gate 以本目录验证结果为准；这里不将 CSim 冒充 RTL 或板测。

## 11. 后续交接与已知限制

任务 2 的结果仅以独立联合工程实际 post-synthesis 报告为准；单核资源相加只能作为预估。K26 容量：117,120 LUT、1,248 DSP、144 BRAM36 等效 tile、64 URAM。既有低照度正式系统 synth 为 LUT40,993 / DSP146 / BRAM65 tile / URAM18；D 独立系统 routed 为 LUT30,168 / DSP758 / BRAM7 tile / URAM40。两个都是整系统且阶段不同，不能直接当成联合利用率；URAM 的粗预估 58/64 提示资源瓶颈需重点实测。

任务 4–6 仍需实现/验证融合核、冻结其 driver ABI、完成 AXI/DDR/跨域/调度、布局布线/时序、联合 bit/XSA/HWH/地址表及哈希包。本次任务不负责板卡加载、真板数值和实际耗时；不将任一旧单系统结果当作新联合包验收。
