# KV260 V1.2 软件联调交接

更新：2026-10-09。先读本文，再读 [公共复现材料](../bringup/kv260_v12/README.md)。本文是已验证接口和后续开发边界，不是本次新增板端操作授权。

## 1. 已验证结果与证据身份

`BOARD_CONTROL_ACCESS=PASS`，`BOARD_BRINGUP_BASE=PASS`，`BOARD_30FPS=NOT_TESTED`。

真板 `night_01` 单帧按 CNN → Bilinear → Curve 串行执行，三模块各启动一次；三份完整输出共 5,514,120 个 INT16 原码逐位一致，60 次 guard 检查通过。此前冷启动恢复也真实完成；不是仅依据 CSim 或 RTL 仿真宣布板测通过。单帧证据 ID：`p7single_frame_1009_01/attempt02`；冷启动证据 ID：`p7cold_resume_1009_01/recovery01`。原始记录由 Master 保管，公共摘要和输入身份见复现目录。

尚未实测：同一 IP 连续重复启动、不同输入连续帧、长批次稳定性、真实 30 FPS、板端精确执行计时、生产 Cache 一致性、Linux 驱动和自动开机加载。历史 RTL 八帧约 30.236 FPS 是仿真结果。单帧 Host 观察的 68/60/80 ms 含 Windows/JTAG 开销，不能当作三个 IP 的计算时间。

上次退出时 D-Cache 最后确认 **OFF**；MMU 状态 **NOT_ASSESSED**；UART/JTAG 和本轮服务器已关闭。这个运行状态可能变化，不能替代下次的新鲜检查。

## 2. 应分发哪个硬件文件

下面的路径是独立交付包中的规范相对路径；文件不随 Git 克隆提供，接收后须核对大小和 SHA256。实际本机源路径另由 Master 的交付清单记录。

| 文件 | 交付包相对路径 | Bytes | SHA256 |
| --- | --- | ---: | --- |
| **本次真板成功的诊断 bit** | `artifacts/diagnostic_v12_independent_clock.bit` | 7,797,826 | `347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86` |
| 对应 routed DCP，离线追溯用 | `artifacts/diagnostic_v12_independent_clock_routed.dcp` | 41,098,381 | `8ead58f3b7641e179693d7fa64fbc7f7ade05d5ec821365e8fcbfc9b0fd532b9` |
| 正式 Phase6 bit，独立保留 | `formal/system_wrapper.bit` | 7,797,826 | `8a6c315b50799fb22cb8bfb6f376e3e6992ac41da0abe9c87a8ffc9ced85c915` |
| 正式 Phase6 XSA | `formal/kv260_three_module_v1_2_writecredit.xsa` | 3,068,574 | `09661c4822f05b8c54b000d2fc13893fac3356a970acb4c70a8ca89fb2693ead` |

诊断 bit 在 V1.2 三模块设计上加入无功能反馈的 EMIO 观察器：PL0 活动、独立 CFGMCLK 活动、EOS、VCC 和两路 canonical reset。它与正式 bit **不是同一个文件**；本次单帧 PASS 只覆盖上述诊断 bit。正式 bit/XSA 没有被它替换，也没有因接口相同自动获得相同的板测结论。正式 XSA 可用于核对三模块 ABI，不能冒充诊断 bit 的已导出 XSA。使用 Vivado 2025.2，器件 `xck26-sfvc784-2LV-c`，设计名义 PL0 100 MHz；活动观察不是板级频率测量。

正式 CNN 是 write-credit RTL 调度版本，VLNV `xilinx.com:hls:zero_dce_cnn_top:1.0`、revision `2114810448`。源码/封装关系见 [release recipe](../ip/cnn_v1_2_writecredit/README.md)；仅重新综合 r4 C++ 不能保证重建这份 post-export writer 调度。

## 3. 冷启动最小恢复顺序

仅复用已真实验证的最小顺序，不运行完整 `psu_init`，不自动 PS reset、clock 修改或断电重启。以下板端 program、PMU/GPIO 写和 PL 读取，都需要当次明确批准。先复用 Master 保管的 Host 独占、设备身份、runtime、CONFIG 和停止门禁；不要从公共库另造无门禁连接入口。

1. 确认进入空闲 U-Boot，核对版本/DDR/LMB/Cache 与启动参数。成功基线为 U-Boot 2023.01（2024-05-10 构建），DDR 4 GiB；这些只是历史身份线索。冷启动后寄存器、配置、reset、Cache、DDR 所有权必须重新检查。
2. 保持 reset request LOW。项目简称“GPIO95”实际是 **EMIO95 / 全局 GPIO173 / bank5 bit31**，不是全局 GPIO95。`DATA5 @0xFF0A0054`、`DIRM5 @0xFF0A0344`、`OEN5 @0xFF0A0348` 的 bit31 若都为 0，获批后仅对 DIRM、OEN 各做一次 RMW OR `0x80000000`，保留其它位，DATA 不写；两次写间及写后核对三个寄存器，合计最多 2 SET/9 GET。若已符合输出 LOW 条件则不重复配置；其它模式差异停止。复用 `gpio95_mode_candidate.tcl`。
3. 加载上表诊断 bit 最多一次，既有成功流程显式使用 `-mpsoc_reset no`。重算文件 SHA，加载后按 CONFIG 字段核对 DONE/EOS 和错误位；历史 `0x12907FFC` 不是应盲目比较的固定通过值。
4. 若输入交付观察已经通过，跳过 PMU 写。否则仅在 `0xFFD80100` bit23 为 1、`0xFFD80110` pending 为 0、`0xFFD80540` bit24 无 error、GPIO 输出 LOW 且 DIRM/OEN bit31 已置 1 的成功前提下，复用 `pmu_pl_recovery_candidate.tcl`：直接向 `0xFFD80118` 写 `0x00800000`，核对 `0xFFD80114` bit23 清零且其它位不变；再向 `0xFFD80120` 写 `0x00800000`。最多 20 次/2 秒名义截止核对 pending bit23 清零及无服务 error。两笔是已验证的 PMU 服务请求；不绕过服务直接操作电源/隔离寄存器。PMU 内部影响可能覆盖整个 PS/PL 边界。
5. `DATA3_RO @0xFF0A006C` 的 mask `0xE2` 应为 `0xE2`：bit7 EOS、bit6 固定 VCC、bit5 独立 clock_seen、bit1 PL0_seen。release 前 bits2/3 两 reset 应 LOW。bit0 PL0 counter 和 bit4 独立 counter 是动态值；不能要求整个字恒定，也不能凭 seen 标志推断频率。
6. 获批后复用 `gpio95_release_candidate.tcl`，仅一次向 `0xFF0A002C` 写 `0x7FFF8000`（masked bank5 MSW，只改 bank bit31 为 HIGH）。核对 DATA5 只增加 bit31、DIRM/OEN 不变，DATA3 mask `0xE2` 保持且 bits2/3 均 HIGH；最多 20 读/2 秒。已 HIGH 且交付/reset 正常时跳过重复 release；异常不自动拉 LOW、reset 或重试。
7. 复用既有 guarded PL transport，仅各读一次 Bilinear/Curve/CNN 的 AP_CTRL，冷恢复无任务时三者应为 `0x00000004`。完整返回、START/AUTO_RESTART 为 0 才恢复控制访问结论。AP_CTRL 读会清 done/ready，属于有副作用的状态读取。首错停止，撤回临时 debugger metadata 并关闭连接。

三份 cold candidate 均位于 `fpga/bringup/kv260_v12/`，只是库，没有自动连接或写板入口。原一次性恢复目录/预算不能重跑。EMIO 用户宽度 8 与工具保留的 reset EMIO95 通道已通过实际 primitive/routed 连接核对，不能把宽度改成 96 作为“修复”。现有证据支持初始化收尾/输入交付不完整；具体隔离位、实际固件漏分支未直接定位。

## 4. AXI-Lite ABI（全部为基址相对偏移）

| IP | 实例 | 基址 | CSR aperture | DDR 通路 |
| --- | --- | --- | --- | --- |
| CNN | `zero_dce_cnn_top_0` | `0xA0020000` | 64 KiB | data/output/workspace→HP0，模型→HP1 |
| Bilinear | `bilinear_fixed16_buffered_0` | `0xA0000000` | 64 KiB | HP2 |
| Curve | `curve_image_fixed16_0` | `0xA0010000` | 64 KiB | HP3 |

共同控制寄存器均是 32-bit word：

| 偏移 | 字段/语义 |
| --- | --- |
| `0x00 AP_CTRL` | bit0 `ap_start` RW/clear-on-handshake；bit1 `ap_done` read/clear-on-read；bit2 `ap_idle` read；bit3 `ap_ready` read/clear-on-read；bit7 `auto_restart` RW；bit9 interrupt read；其它保留 |
| `0x04 GIE` | bit0 全局中断使能 RW |
| `0x08 IER` | bit0 done、bit1 ready 中断使能 RW |
| `0x0C ISR` | bit0 done、bit1 ready 状态；写 1 toggle，对应位不是普通 write-zero-clear |

本次采用轮询，要求 GIE=0、auto_restart=0；未执行中断使能写。已核对 BD 没有三 IP 的 interrupt net，当前不应把中断模式当成可用路径。

下表所有 pointer 都是 **64-bit 总线地址**，先 low 32-bit、再 high 32-bit；scalar 是 unsigned 32-bit。正式 driver/RTL 参数 word 支持读回；HWH 标为 write-only 的差异已核对。不能把 CPU 虚拟指针写入这些字段，也不能因本次 high=0 就省略高 word。

| IP | 参数 | Low / high 或 scalar 偏移 | 指向数据/含义 |
| --- | --- | --- | --- |
| CNN | `input_q14` | `0x10 / 0x14` | 本帧低分辨率输入 |
| CNN | `weights_int8` | `0x1C / 0x20` | 冻结权重 |
| CNN | `bias_int32` | `0x28 / 0x2C` | 冻结偏置 |
| CNN | `weight_frac` | `0x34 / 0x38` | 每输出通道量化小数位 |
| CNN | `tanh_lut_q15` | `0x40 / 0x44` | 冻结 tanh LUT |
| CNN | `a_low_q14` | `0x4C / 0x50` | CNN 输出，Bilinear 输入 |
| CNN | `workspace_int16` | `0x58 / 0x5C` | 六个 skip 张量 |
| Bilinear | `parameters_lowres` | `0x10 / 0x14` | 同一帧 `a_low_q14` |
| Bilinear | `parameters_fullres` | `0x1C / 0x20` | 输出 `A_full` |
| Bilinear | `input_height` | `0x28` | 本次 60 |
| Bilinear | `input_width` | `0x30` | 本次 106 |
| Curve | `input_r` | `0x10 / 0x14` | 本帧全分辨率 model input；C++ 名称 `input` |
| Curve | `parameter_r` | `0x1C / 0x20` | 同一帧 `A_full`；C++ 名称 `parameter` |
| Curve | `output_r` | `0x28 / 0x2C` | enhanced 输出；C++ 名称 `output` |
| Curve | `count` | `0x34` | INT16 元素数，2,747,520；不是字节数或二维像素数 |

启动协议：等前一次完成且 idle、start=0、auto_restart=0；准备并同步本帧所有输入/输出所有权；配置参数；必要的 MMIO/内存排序完成后仅写 AP_CTRL=`1` 一次；有界轮询保留每次完整读值，捕获 done=1 同时要求 idle=1/start=0/auto_restart=0；验证输出后才启动 consumer。实际单帧状态为 `0x1 → 0xE`；读到 `0xE` 后 done/ready sticky 会被该次读清除。不要依赖第二次读取还能得到 done，不使用循环写 start、auto_restart 或 reset 来消除超时。

标准 `ap_ctrl_hs` 完成后可再次提交；正常重启不要求每帧 reset。指针变化就重新写完整参数对，buffer 内容变化就重新移交所有权。同一帧参数可保留的结论来自 RTL，**真板重复启动仍待验证**。单帧库只允许一次运行，不可清除 once 标志冒充已审核多帧工具。

## 5. 数据格式、输入 producer 和长度

所有图像/曲线参数是 RGB NCHW planar、batch=1、C-contiguous、小端 signed INT16 Q14，值=`raw/16384`，无 row padding；offset=`2*((c*H+y)*W+x)`。Bilinear/Curve 的接口类型为 `ap_fixed<16,2,AP_RND,AP_SAT>`，CNN 对外是 `ap_int<16>` 原码；不能复制 float32 或交错 RGB 字节代替。

| Buffer | Shape / 类型 | 元素数 | Bytes |
| --- | --- | ---: | ---: |
| INPUT_Q14 | `[1,3,60,106]` INT16 Q14 | 19,080 | 38,160 |
| A_LOW_Q14 | `[1,3,60,106]` INT16 Q14 | 19,080 | 38,160 |
| A_FULL_Q14 | `[1,3,720,1272]` INT16 Q14 | 2,747,520 | 5,495,040 |
| MODEL_INPUT_Q14 | `[1,3,720,1272]` INT16 Q14 | 2,747,520 | 5,495,040 |
| ENHANCED_Q14 | `[1,3,720,1272]` INT16 Q14 | 2,747,520 | 5,495,040 |
| WORKSPACE_INT16 | 6 × `[32,60,106]` signed INT16，F=[14,14,14,12,13,14] | 1,221,120 | 2,442,240 |
| WEIGHTS_INT8 | signed INT8，14 层顺序、每层 OIHW | 10,075 | 10,075 |
| BIAS_INT32 | 小端 signed INT32，每输出通道一个 | 486 | 1,944 |
| WEIGHT_FRAC | signed INT8，每输出通道一个 | 486 | 486 |
| TANH_LUT_Q15 | 小端 signed INT16 Q15，Q8 index -2048..2048 | 4,097 | 8,194 |

workspace slot 的 byte offsets 是 0、407040、814080、1221120、1628160、2035200；整个 workspace 不是统一 Q14。权重真实值为 `raw/2^F_weight[c]`，bias scale 是 `2^-(F_in+F_weight[c])`；不能重新标成统一 Q14。精确量化/舍入和逐通道字段见 [数值协议](v1_fixed_point_protocol.md) 和 [JSON](v1_fixed_point_protocol.json)，但旧协议中的旧 m_axi topology/4,070,400-byte workspace 由本文替代。

裁剪、RGB/NCHW 转换、Q14 量化、60×106 下采样由 PS/前级完成，CNN 内不做。冻结测试的 full frame 为 720×1272；低分辨率每点从 full Q14 的 `(12y+5/6,12x+5/6)` 四邻居求和并 nearest-even 除以 4，与冻结 INPUT_Q14 一致。不要直接把 720×1280 相机帧输入这些 buffer。Bilinear 固定放大 12 倍、align-corners 数值规则，input_width≤128；非法 height=0/width=0/width>128 会直接返回，done 不证明输出有效。当前集成验证只覆盖 60×106。Curve 对每个 INT16 元素做八次 `x ← x + a*(x*x-x)`，每轮按其 Fixed16 类型舍入/饱和，无额外 `[0,1]` clamp。

## 6. DDR 数据流与帧所有权

控制为 PS HPM0_FPD → axi_control → 三 AXI-Lite slave。CNN input/output/workspace 三 master 经 cnn_data_sc→HP0；weights/frac、bias、LUT 三 master 经 cnn_model_sc→HP1。Bilinear 两 master 经 bilinear_ddr_sc→HP2；Curve 三 master 经 curve_ddr_sc→HP3。没有三模块间 AXI-Stream 通路或独立 DMA IP；这些 HLS master 自己读写 DDR。

最小串行链为：PS 提供同帧 INPUT_Q14、MODEL_INPUT_Q14 和冻结模型 → CNN 写 A_low → Bilinear 读 A_low 写 A_full → Curve 读 MODEL_INPUT 和 A_full 写 ENHANCED → PS 取回结果。模块之间共享同一帧 DDR buffer，不需要 PS 拷贝 A_low/A_full；PS 负责启动顺序、完成同步、buffer 分配/Cache 一致性和输出校验。

INPUT_Q14/模型/workspace 在 CNN 完成前不可被 CPU/其它任务覆盖；A_low 在 Bilinear 完成前不可复用；A_full 和 MODEL_INPUT 在 Curve 完成前不可复用；ENHANCED 在 PS 消费完成前不可复用。单 workspace 不能服务两个并行 CNN。后续双缓冲/流水调度须对 frame_id 和每个 consumer 建立所有权，不能仅通过轮转地址假定上一帧已结束。

## 7. 物理分配与 Cache/MMU

历史实验经 Master 明确允许覆盖 `0x20000000–0x23FFFFFF` 64 MiB，其实际 buffer+guard 使用范围截止 `0x2128D940`；不是最终软件固定地址，也不是“LMB 未保留就可覆盖”的通用证明。历史 LMB 高地址保留区和静态 BFM 地址都不能代替下一次 DDR 所有权证明。公共历史 plan 只用于复现数值和边界；新环境必须由所有者分配、证明不重叠并重新批准。

本次各 data base 为 64 KiB 对齐；既有 RTL 合同采用至少 16-byte base 对齐，INT16 原码/CSR 分别按 2/4-byte 访问。生产驱动还要按 DMA API 的 cache alignment 隔离不同所有者，不能让 guard 或其它数据共享需要同步的 cache line。64-bit CSR 不代表任意地址都在实际 HP/DDR 地址窗口可达；本次仅验证 high word 为 0 的低 DDR 地址。

单帧 U-Boot 采用一次 `dcache off` 并确认 OFF 来消除实验的 CPU cache 别名问题；该全局操作可能 flush dirty cache、关闭 MMU/影响运行环境，实际 MMU 状态没有独立确认。它不是生产方案，也不能自动恢复 ON。

Linux 驱动应使用 OS 分配并映射的 DMA buffer，将返回的 **DMA/bus address** 写 CSR，设置/验证设备 DMA mask、HP 可达范围和必要 IOMMU 映射。可选择平台支持的 coherent allocation（仍须 barrier/顺序约束）；streaming mapping 则在 CPU→PL 前同步到 device、PL→CPU 后同步到 CPU，双向 workspace 按双向所有权同步。三 IP 共享中间数据时必须确保映射的 bus address 对相应 master 可达；不把 CPU 虚拟地址/用户态指针当物理地址。具体接口依据 [Linux DMA API](https://docs.kernel.org/core-api/dma-api.html) 和 [DMA mapping guide](https://docs.kernel.org/core-api/dma-api-howto.html)；这些驱动、映射和同步尚未实现或实测。当前 HP0–3 路径没有 CPU 一致性证明。

## 8. 可复用材料与复现流程

`fpga/bringup/kv260_v12/` 提供已实跑的 `single_frame_candidate.tcl`、`transport.tcl` 和三 cold candidate；它们是复用核心，不是无条件连接板卡的一键程序。原 Host 封装依赖 Windows、Vivado 2025.2/TCF、hw_server、身份/独占门禁、U-Boot UART 与获批 DDR/Cache 范围，由 Master 保管；其中本机身份配置/原始日志不提交 Git。

公共 `prepare_payloads.py --data-root <独立数据包目录> --output <新目录>` 仅 Host 核对输入 SHA 并准备 payload/guard/policy；`verify_outputs.py` 用于 Host 全量比对三输出。先看公共 README 的实际参数，生成不等于写入 DDR。测试范围应从新 plan 审核后交给既有 guarded transport；不能重跑已耗尽预算的单帧执行目录。

例如以下两条均不接触板卡：

```text
python fpga/bringup/kv260_v12/prepare_payloads.py --data-root <artifact-data-dir> --output <new-local-run-dir>
python fpga/bringup/kv260_v12/verify_outputs.py --data-root <artifact-data-dir> --actual-dir <saved-actual-dir>
```

生成的 `core_policy.tcl` 不包含 live transport 的 SET/GET 白名单或独占/身份门禁；这些必须沿用已审核封装。输出比对工具只证明保存的文件相同，不单独证明新板测、guard 或性能结论。

独立数据包共有 9 份 bin：`input_q14.bin`、`weights_int8.bin`、`bias_int32.bin`、`weight_frac.bin`、`tanh_lut_q15.bin`、`model_input_q14.bin`、`expected_a_low_q14.bin`、`expected_a_full_q14.bin`、`expected_enhanced_q14.bin`。小型输入/参数/A_low golden 的 hex 可在 Git 中复原；full frame 和两份 full golden 另行分发，以公共 manifest 的 byte size/SHA 为准。克隆仓库本身不具备完整板测数据。

三个真实输出 SHA：

| 输出 | Bytes | SHA256（与冻结 golden 一致） |
| --- | ---: | --- |
| A_low | 38,160 | `31abdd23520d32efe75928ef394017bd2f515b2805144a85735eebc9481dddd1` |
| A_full | 5,495,040 | `ebfa58eafb70385af39b92b6c9ed2b81c3319ca63662ce002d1219051f8b2067` |
| Enhanced | 5,495,040 | `869e62a41010e047c3760aa6a614f0ff883566d52c3fbee273cf2a865f7eb951` |

## 9. Linux / 正式启动仍需完成的工作

没有已实现的 Linux 驱动、device-tree overlay、自动 bit 加载、自动 PMU/reset 初始化或相机输入流水线。需按目标系统实际固件/FPGA manager 驱动接入加载和电源/reset 生命周期，防止与 U-Boot/JTAG 初始化重复；不能把这些诊断地址写直接复制成开机服务。

软件联调先实现 MMIO 资源占用、DMA buffer、同步/超时、三段串行调用和原码导出；验证同帧输入关系后，再做多帧所有权、板端计时及端到端图像提交/取回路径。改为正式 bit 后需重新验证对应 image，不将本次诊断结论自动迁移。单 IP/串行链/DDR 开销/真实端到端 FPS 应分别计量；Windows/JTAG 下载和回读不能用于证明 PL 30 FPS。

## 10. 异常和停止规则

单帧基线逐 IP 最多 100 次 AP_CTRL 读取、5 秒名义截止；每阶段输出全量 bit-exact、全部 20 个 guard 通过才进入下一阶段。transport 必须检查每笔完整返回、参数逐 word 写后读回、身份/门禁新鲜性；数据不符不能仅凭 done 宣布 PASS。

超时、AXI 无响应/部分返回、unexpected auto_restart、done 时非 idle/start 未清、参数读回失败、输出或 guard 错误，立即停止新增写入/启动，保存最后状态与原始数据；不自动 reset、reprogram、retry 或 rollback。Host 截止不能保证撤销已发出的在途 AXI，板卡可能仍 busy；关闭 Host 连接不代表硬件运算被取消。缓存/输出和 workspace 保持最后状态，后续恢复需要单独审核。

AP_CTRL 没有本项目定义的数值错误/DDR AXI 错误字段；done 是握手完成，不能代替数据和 guard 校验。通用 HLS 控制原则可查 [AMD UG1399](https://docs.amd.com/r/2024.1-English/ug1399-vitis-hls/Controlling-Hardware)，具体行为以这里核对的 2025.2 实际生成 RTL 为准。

来源核对：实际正式三 driver header 与正式 XSA 内 header 逐 byte 相同，CNN/Bilinear/Curve SHA 分别为 `3a5b88eea559abf69c213b8456fee35945db0f21acc9d5cd1ad267638a716362`、`8eee503594c8e381c1fd361e2014ddd9314d158dbb96d0e7aea2ab68ebf065a3`、`8c145a90188f440acd751744ee562d1537e609d3f03d82779c9ca721a409660c`；实际 control RTL、[保存的 BD](../vivado/three_module_integration_v1_2/three_module_integration_v1_2.srcs/sources_1/bd/system/system.bd)、[机器寄存器 map](v1_2_hw_register_map.json)、HLS C++/header 与两份真实证据交叉核对。原 map 的旧状态/本机路径属于其历史元数据，当前状态以本文及三权威报告最新顶部为准。
