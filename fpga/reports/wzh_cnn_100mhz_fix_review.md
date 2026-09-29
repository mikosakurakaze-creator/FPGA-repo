# WZH CNN K26 100 MHz 修复增量审计

审计日期：2026-09-28～29。**结论：新版 CNN 在 K26、10.000 ns 配置下的 Vitis HLS C Synthesis 估计时钟为 7.300 ns，HLS 层已达到 100 MHz 目标；`night_01` 的 19,080 个 Q14 `A_low` 与旧 golden 逐位一致。** 这不是 KV260 Vivado implementation/post-route 时序通过的证据。RTL Co-sim、三模块 Block Design 和板上 DDR 事务仍未验证。

## 1. 目标、版本与隔离方式

本次只审计 WZH 最新 push 对旧版 K26 10 ns 失败的修复，复跑原始 `night_01` 数值测试和 K26 C Synthesis，检查 IP/接口并评估 RTL Co-sim。没有修改 WZH core、Master 当前 Bilinear/Curve/Vivado routed/bitstream/XSA baseline；没有 merge、rebase、cherry-pick、commit、push，也没有做 Master BD 综合或生成新的 Master bitstream。

| 项目 | 实际值 |
|---|---|
| OLD | `01580f026a9d14145cad91e8957143c120928a0d` |
| NEW | `72b21138ce87a16eb3d3d6163675936b82ceadbc` |
| NEW 标题、作者、时间 | `Optimize CNN HLS DDR access with tiled on-chip buffers`；`unknown <wwei42933@gmail.com>`；`2026-09-28T21:55:27+08:00` |
| NEW 父提交 | `35f07d86e052ed7bb3ac8256e6dae50383e49bed` |
| OLD→NEW 提交链 | `0d2dbb2`（路径含空格的 HLS flow 修正）、`35f07d8`（定点/接口文档）、`72b2113`（tile/DDR 优化）；`git merge-base --is-ancestor OLD NEW` 退出 0 |
| Master 工作树 | `E:/github/-`，分支 `codex/curve-fp32-baseline`，本次审计时 HEAD `503537cf2e084d22b6e6856b0cb0ffff64f211e0` |
| 独立 detached worktree | `E:/HLS/wzh_cnn_100mhz_review_72b2113`；`git status --short` 为空 |
| 隔离 HLS 审计目录 | `E:/HLS/wzh_cnn_100mhz_audit_72b2113` |
| 工具、器件、时钟 | Vitis HLS 2025.2 Build 6295257；`xck26-sfvc784-2LV-c`；10.000 ns |

主工作树原有未跟踪文档/脚本保持原样，本次仅新增本报告。`git fetch --all --prune` 把 `origin/feat/zero-dce-quantization` 从 `01580f0` 更新到 `72b2113`，没有切换 Master 工作树。`git diff --stat OLD NEW` 显示 **12 files changed, 543 insertions, 240 deletions**；`git diff --name-status OLD NEW` 涉及 `README.md`、`configs/zero_dce_pp_a_low_interface.json`、`configs/zero_dce_pp_hls_interface.json`、`deployment/README.md`、新定点接口文档、`docs/zero_dce_pp_hls_cnn_contract.md`、`docs/zero_dce_pp_integer_quantization_report.md`、`evaluation/test_zero_dce_hls_contract.py`、`fpga/hls/README.md`、`fpga/hls/run_hls.tcl`、`fpga/hls/zero_dce_cnn_top.cpp/.h`。本次未改作者 testbench `fpga/hls/tb_zero_dce_cnn.cpp`。

## 2. WZH 实际改了什么

源码 `fpga/hls/zero_dce_cnn_top.cpp` 的变化不是只调低 target clock。旧版逐元素从单个 `gmem` 读写特征和 skip，`concat_skip` 有读→写/地址长组合路径；新版：

1. 新增 `load_model`，一次调用时把 10,075 个 INT8 权重、486 个 INT32 bias、486 个 fractional-bit 参数和 4,097 个 Q15 LUT 值载入片上数组；MAC 不再逐次从 DDR 取模型。
2. 输出按 **8×16 tile** 扫描，`load_source_tile` 装载带一像素 halo 的局部 source tile，边缘清零；`compute_depth_tile`、`compute_point_tile` 在片上 `source_tile`/`middle_tile`/`output_tile` 中计算；`store_output_tile` 最后写 DDR。skip concat 及其层间 Q 格式转换被移到 tile 装载时。七个 block 仍顺序运行，每个 block 的所有 tile 完成后后续 block 才读取对应 skip。
3. 模型数组及三个 tile 数组显式使用 `BIND_STORAGE ... ram_2p impl=bram`；模型装载、source 读、depth/point MAC、输出存储内循环使用 `PIPELINE II=1`。没有新加 `ARRAY_PARTITION`、`UNROLL` 或 `DATAFLOW`，也没有改变 10 ns 配置以制造达标结果。
4. 七个逻辑指针不变，但从一个共享 `bundle=gmem` 拆为**六个物理 m_axi**：`gmem8`（权重+weight_frac）、`gmem32`（bias）、`gmem_input`、`gmem_lut`、`gmem_output`、`gmem_workspace`。这消除了旧共享总线争用，但给下阶段 Vivado 接线增加六路 master。
5. DDR scratch 从 **2,035,200 × INT16 = 4,070,400 B** 缩为 **1,221,120 × INT16 = 2,442,240 B**，减少 1,628,160 B；现在仅保存六个 32 通道 ReLU skip slot。`.h` 常数、JSON 合同和相应 Python 合同测试一同更新。

`round_shift_even`、`clamp_q16`、14 卷积数值结构、最后 Tanh LUT→Q14 的数值规则未因本次优化修改；本次 CSim 逐位回归也支持此结论，但只覆盖一帧。作者的新 `run_hls.tcl` 支持路径含空格的源目录，会 staging 到无空格目录；它默认针对 PYNQ `xc7z020clg400-1`，本审计另建 **K26/10 ns** 配置，不能以作者 PYNQ 估计替代 K26 结果。

## 3. 输入、Python 合同与 CSim 数值回归

测试使用上一版审计生成并确认的原始 `night_01` integer/HLS package，复制到 detached worktree 的被忽略 `outputs/` 与隔离审计目录；没有重新量化、修改或生成替代 golden。文件包括 `input_q14.bin`、`weights_int8.bin`、`bias_int32.bin`、`weight_frac.bin`、`tanh_lut_q15.bin`、`expected_a_low_q14.bin`。CNN 输入和输出均为 RGB/NCHW `[1,3,60,106]`、signed INT16 Q14、小端、19,080 元素。比对的旧软件向量为 `night_01_a_low_q14_nchw_le.bin`。

首次直接运行两组 pytest 时 **9 passed、2 failed**；失败均因新的隔离 worktree 尚无 `integer_weights.npz`、`night_01_layer_io_manifest.json` 等被忽略测试工件，非数值差异。复制上次原始 `integer` 和 `hls_cnn` 工件后原命令重跑为 **11 passed in 3.34 s**，worktree 跟踪文件未改变。

Vitis HLS 2025.2 使用作者未改的 `zero_dce_cnn_top.cpp/.h` 与原 `tb_zero_dce_cnn.cpp` 实跑 C Simulation：**0 errors**，原 testbench 报 `A_low Q14: 19080 scalars, mismatches=0, max_abs_raw_error=0`。另用隔离目录中的审计专用 dump TB 调同一 HLS core，把实际 CSim 输出保存为 `data/cnn_csim_actual_a_low_q14.bin`；它不是旧文件拷贝，运行前先清除了隔离目录里误随 package 复制的旧 `cnn_csim_actual_a_low_q14.bin`。

| 对比 | 结果 |
|---|---:|
| 输出元素/字节 | 19,080 / 38,160 B |
| NEW CSim vs OLD Q14 golden raw mismatches | **0** |
| max / mean absolute raw error | **0 / 0** |
| max / mean real-value error（raw ÷ 16384） | **0 / 0** |
| NEW CSim / package golden / OLD `night_01` 软件 golden SHA-256 | 三者均为 `31abdd23520d32efe75928ef394017bd2f515b2805144a85735eebc9481dddd1` |

CSim 编译仅见工具安装头文件的 `__GMP_LIBGMP_DLL` 重定义 warning，没有数值错误。此结果不是 CNN RTL 或板端 DDR 数据。

## 4. K26 10 ns C Synthesis：旧版与新版

实际在 `xck26-sfvc784-2LV-c`、`ap_clk=10.00 ns`、Vitis HLS 2025.2 上运行新版 **C Synthesis PASS**，并生成 RTL/IP。时钟不确定度 2.70 ns，HLS estimated clock 7.300 ns，离 10.000 ns 尚有 **2.700 ns 估计余量**；按用户分级属于 **A：HLS 层已满足**。旧版 K26 报告取自上次同器件、同目标时钟的实跑报告 `E:/HLS/wzh_cnn_latest_review/cnn_hls_component_k26/hls/syn/report/zero_dce_cnn_top_csynth.rpt`。

| 指标 | OLD `01580f0` | NEW `72b2113` | 变化 |
|---|---:|---:|---:|
| C Synthesis | PASS，但时钟未达 | **PASS，HLS 估计达标** | 只证明 HLS 级 |
| Target clock | 10.000 ns | 10.000 ns | 0 |
| Estimated clock | **23.073 ns** | **7.300 ns** | **−15.773 ns** |
| HLS 时钟余量（target−estimate） | −13.073 ns | +2.700 ns | +15.773 ns |
| DSP | 11 | 16 | +5 |
| LUT | 16,489 | 16,247 | −242 |
| FF | 6,753 | 9,285 | +2,532 |
| BRAM_18K | 4 | 56 | +52 |
| URAM | 0 | 0 | 0 |
| 顶层 latency min/max（cycles） | 3,276,058 / 6,921,644,165 | **? / ?** | 新版 tile/source 动态界导致工具无法静态确定，不能比较整帧时延 |
| 顶层 interval min/max（cycles） | 3,276,059 / 6,921,644,166 | **? / ?** | 未验证实际逐帧吞吐 |
| 顶层 pipelined | no | no | 七个 block 仍顺序 |
| 主要卷积内循环 II | target 1 / achieved **2** | depth 与 point 内循环 target 1 / achieved **1** | 结构已变，不把两种 loop 的时延直接等同 |

资源变化的主要代价是片上模型/tile BRAM（56/288 BRAM18K，HLS 估计 19%）与六路 AXI 接口；FF 增加、DSP 略增，LUT 略减。**不能由 `II=1` 或 HLS 时钟估计推断板上 FPS**：整帧 latency/interval 为 `?`，DDR 行 tile 载入和七个 block 串行仍可能主导真实吞吐。

新版关键层级与内部报告：

| 层级/loop | II target/achieved | Iteration latency | Trip count | 状态 |
|---|---|---:|---:|---|
| top `block → tile_row → tile_column` | - / - | ? | 7 / 8 / 7 | 非 pipeline，latency `?` |
| `load_source_tile` 内 `VITIS_LOOP_129_3`（halo 清零） | 1 / 1 | 1 | 18 | pipeline |
| `load_source_tile` 内 `VITIS_LOOP_142_4`（DDR source 装载） | 1 / 1 | 4 | 动态，报告 `-` | pipeline；load_source_tile 总 latency `?` |
| `compute_depth_tile` 合并 MAC loop | 1 / 1 | 7 | HLS 报告上界 3,663,360 | pipeline；函数 latency 1,089～3,663,369 cycles |
| `compute_point_tile` 合并 MAC loop | 1 / 1 | 10 | HLS 报告上界 26,050,560 | pipeline；函数 latency 372～26,050,572 cycles |
| `store_output_tile` 合并 store loop | 1 / 1 | 11 | HLS 报告上界 407,040 | pipeline；模块 latency 131～407,051 cycles |

这些上界是 HLS 对复用函数/动态循环的静态范围，**不是本次 `night_01` 实测周期**。

## 5. 旧瓶颈、warning 与新 timing path

| 旧问题 | 新版复查 |
|---|---|
| `concat_skip` 的共享 `gmem` 读→写/地址长组合路径，旧最坏 23.0733 ns | 独立 `concat_skip` 已移除，转换并入 `load_source_tile`；新版 HLS 总估计 7.300 ns。旧路径在新结构中已不存在 |
| 单物理 `gmem` 上多重读写争用，`HLS 200-448` | 六个物理 master，模型和 tile 在片上复用；新版综合日志中没有 `200-448` |
| 旧卷积 target II=1 / achieved II=2 | 新版 depth/point 合并内循环均 target II=1 / achieved II=1；注意 loop 结构已重写 |
| `HLS 200-871` target clock 失败 | 新版综合日志未出现，估计 7.300 ns |
| `HLS 200-880` carried dependence | 新版日志未出现 |
| `HLS 200-887` 无法满足组合路径预算 | 新版日志未出现 |

新版 `zero_dce_cnn_top.verbose.sched.rpt` 的最长 **HLS 调度状态**为 7.300 ns：top `load_model` 的 `gmem8` 模型读请求/控制阻塞路径（`zero_dce_cnn_top.cpp:78→324`）；`load_source_tile` 的 `gmem_input` source 行读请求也有 7.300 ns 控制阻塞状态。与旧版 `concat_skip` 的 DDR 读到写长组合链不同。该 HLS 调度报告给出的是操作 `getelementptr → bus request` 和 blocking control state，**没有 post-route 寄存器 startpoint/endpoint**；起点/终点寄存器、最终布线 delay 必须在 Vivado timing report 中确认，不能伪造为已知。`compute_depth_tile`/`compute_point_tile` 子函数自身分别估计 7.081/6.941 ns，未超过顶层 7.300 ns。

新版综合日志记录 **0 ERROR、80 WARNING**：其中 `SYN 201-103` 匿名命名空间函数名合法化 7 条，`RTGEN 206-101` 73 条（内部未使用的 AXI 读请求输出被接常 0，以及“含 AXI 端口时 reset 固定为同步低有效”）。没有旧 `200-871/448/880/887` 时钟或 II 失败警告；这些新 RTGEN warning 不等于 RTL Co-sim、Vivado DRC 或真实 DDR 验证通过。`csynth.rpt` 的总 LUT 行为 16,253，而顶层详细 `zero_dce_cnn_top_csynth.rpt/.xml` 总计为 **16,247**；本表统一采用后者并保留 6 LUT 的工具汇总差异，不掩盖它。

## 6. 数值/物理接口与 IP 包

**逻辑数值接口未改**：top 仍为 `zero_dce_cnn_top`；输入已经缩小到 `[1,3,60,106]` 的 RGB/NCHW signed INT16 Q14，输出 `a_low_q14` 同形状/顺序，真实值 `signed_raw/16384`、小端无 padding。`night_01` 软件 golden 的 raw bit pattern 与本次 HLS CSim 完全一致。CNN 写 DDR 后由 Bilinear Fixed16 按同一 raw 16-bit Q14 解释，数值层无需 requant、layout reorder 或单独 pack/unpack；没有 AXI Stream，因此无需 AXIS→DDR adapter。固定点下采样器仍在 CNN top 外，PS/上游需提供符合合同的低分辨率输入。

**物理 AXI 拓扑发生变化**：旧版 1 路 32-bit `m_axi_gmem`，新版 6 路 `m_axi_gmem8`（8-bit）、`m_axi_gmem32`（32-bit）、`m_axi_gmem_input`/`lut`/`output`/`workspace`（各 16-bit），全部 64-bit 地址。控制仍为 32-bit `s_axi_control`、`ap_ctrl_hs`，`ap_clk`、同步低有效 `ap_rst_n`、`interrupt/ap_done`。顶层七个 pointer 的 AXI-Lite 基址配置仍存在，scratch 指针深度/所需 DDR 分配大小改为 2,442,240 B。六路接口均需接到可访问 DDR 的互连；当前 Bilinear+Curve V1 只有原有五路 HLS master，不能把新 IP 当成旧单口 CNN IP 直接接入，须在**新的 V1.1 BD** 中增设互连连接并 Validate。SmartConnect 的宽度转换和总线竞争影响尚未实测，不应把逻辑 Q14 兼容误写成现有物理 BD 即插即用。

本次 K26 综合实际生成 `E:/HLS/wzh_cnn_100mhz_audit_72b2113/cnn_synth_k26/hls/impl/ip/component.xml` 与 `xilinx_com_hls_zero_dce_cnn_top_1_0.zip`。`component.xml` VLNV 为 `xilinx.com:hls:zero_dce_cnn_top:1.0`；含 `s_axi_control`、上述六路 `m_axi`、`ap_clk`、`ap_rst_n`、`interrupt`，有 RTL/驱动文件；`zynquplus` family 元数据标记 **Pre-Production**。本次是 HLS IP 打包成功，未在 Master Vivado IP catalog 中注册、未检查 locked IP/BD Validate、未做 Vivado 综合/实现。

文档一致性：`docs/zero_dce_pp_hls_cnn_contract.md` 和 `configs/zero_dce_pp_hls_interface.json` 记录作者 PYNQ `xc7z020clg400-1` 的 8.313 ns HLS 估计（**不是本次 K26 7.300 ns**）；`configs/zero_dce_pp_a_low_interface.json` 的 `implementation_status` 仍写“synthesis ... missed 10 ns target”，与新版 tiled PYNQ 文档及本次 K26 实测不一致，属于未同步的状态文字，不改变源码或本次实测结论。

## 7. RTL Co-sim 与完成度判断

**RTL Co-simulation 未运行/未验证。** 作者分支没有独立 CNN cosim config/小尺寸验证模式；top 尺寸固定 60×106、七个 block/14 卷积，原 testbench 调一整帧。新版 HLS top latency/interval 为 `?`，point MAC 合并 loop 的工具静态上界很大（26,050,560 cycles/次调用）；无法基于报告给整帧 RTL 仿真一个可信、短时的上界，直接在完整 AXI/六路 master 模型上跑可能持续数小时。本次按任务要求没有把 CSim 当作 RTL PASS，也没有假造 transaction cycles、bit-exact RTL 或 FPS。后续如需 RTL Co-sim，应先由 CNN owner 准备可裁剪且保持核心计算一致的验证模式/fixture 或给出可接受的仿真预算，再实际跑并比对 DDR 输出 raw。

| Level | 本次状态 |
|---|---|
| 0 软件模型、1 CNN HLS core | 已有 |
| 2 CSim | **PASS**：原始 `night_01` 19,080 个 raw bit-exact、0 errors |
| 3 C Synthesis | **PASS**：K26 10 ns，估计 7.300 ns；整帧 latency unknown |
| 4 RTL Co-sim | **未验证** |
| 5 物理接口定义 | 已明确六路 m_axi、AXI-Lite/clock/reset 与 Q14 DDR 输出；真实事务未验证 |
| 6 可作为 KV260 IP 接入 | **具备开启隔离 V1.1 集成试验的前提**（K26 IP 已打包、HLS 时钟/CSim PASS、Q14 合同保持），但未完成 Vivado BD Validate、系统资源和 post-route timing，不记为已通过 |
| 7 CNN→DDR→Bilinear 硬件链 | 未验证；先前仅有 CSim 向量→Bilinear CSim 数值链 |

按连续实际验证关口，目前仍是 **Level 3**；另有 Level 5 的接口定义。**建议 Master 可以审核是否在独立 V1.1 工程启动三模块 Vivado 接线与 Validate/实现试验，同时保持已完成 V1 routed/bitstream/XSA 不动。** 当前不能声称“KV260 最终 100 MHz 已修好”：须在六路 CNN master 加入后，实际跑 Vivado implementation/post-route setup/hold/DRC，并验证 RTL 与真实 DDR `A_low` raw。优先的剩余风险不是旧 `concat_skip` 时钟链，而是六路 DDR 互连/带宽、整帧延迟未知以及 RTL/PS 缓存与事务行为。

## 8. 实际命令、证据位置与 Git 状态

下列为实际运行的关键命令；HLS 配置与审计专用 dump TB 在 `E:/HLS/wzh_cnn_100mhz_audit_72b2113/`，均不属于 Master 仓库：

```powershell
git status --short --untracked-files=all
git branch --show-current
git fetch --all --prune
git merge-base --is-ancestor 01580f026a9d14145cad91e8957143c120928a0d origin/feat/zero-dce-quantization
git diff --stat 01580f026a9d14145cad91e8957143c120928a0d origin/feat/zero-dce-quantization
git diff --name-status 01580f026a9d14145cad91e8957143c120928a0d origin/feat/zero-dce-quantization
git worktree add --detach E:\HLS\wzh_cnn_100mhz_review_72b2113 72b21138ce87a16eb3d3d6163675936b82ceadbc
& E:\HLS\bilinear_oracle_venv\Scripts\python.exe -m pytest -q .\evaluation\test_zero_dce_integer_ptq.py .\evaluation\test_zero_dce_hls_contract.py
& E:\HLS\wzh_cnn_100mhz_audit_72b2113\run_csim.cmd
& E:\HLS\wzh_cnn_100mhz_audit_72b2113\run_csim_dump.cmd
& E:\HLS\wzh_cnn_100mhz_audit_72b2113\run_synth_k26.cmd
Get-FileHash -Algorithm SHA256 E:\HLS\wzh_cnn_100mhz_audit_72b2113\data\cnn_csim_actual_a_low_q14.bin
```

这三个 `.cmd` 均先 `call E:\Xilinx\2025.2\data\settings64.bat`；前两者实际调用 `vitis-run.bat --mode hls --csim --config ... --work_dir ...`，综合实际调用 `v++.bat -c --mode hls --config ... --work_dir ...`。新配置明确 `part=xck26-sfvc784-2LV-c`、`clock=10`、原 WZH top/source/testbench，`csim.argv` 指向复制的原 `night_01` package。原 CSim 日志在 `cnn_csim`，dump CSim 日志在 `cnn_csim_dump`；综合报告在 `cnn_synth_k26/hls/syn/report/zero_dce_cnn_top_csynth.rpt`，日志在 `cnn_synth_k26/logs/hls_compile.log`，关键调度路径在 `cnn_synth_k26/hls/.autopilot/db/zero_dce_cnn_top.verbose.sched.rpt`。

**未运行**：RTL Co-sim、Vivado BD Validate/Synthesis/Implementation、post-route timing、bitstream/XSA 更新、PS 软件、实际 DDR 读写、KV260 板测。主工作树原有未跟踪文件没有被 staged/覆盖；新增本报告仍未跟踪。没有 commit 或 push。
