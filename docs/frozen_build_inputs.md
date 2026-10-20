# 冻结构建输入与整数规则

本表记录当前 Weather 功能候选使用的冻结输入。哈希用于识别确切文件；不表示已完成真板、视频或正式画质评测。原 A 交付及旧低照度源码保持只读。

## Weather 固定参数

| 输入 | SHA-256 |
|---|---|
| 天气整帧核源码（`weather_frame.cpp`） | `01ee524a4fc704d2243b1838cf39f126dd996ad619c52de55ffbee11e4ab65d6` |
| 去雨固定参数（`params_derain.h`） | `d980ec138fe9fed6b08e90465199bb381369472fb652c4ec2b85c597b8e578f6` |
| 去雾固定参数（`params_dehaze.h`） | `19841d80f598738954d1b8efaa9288c203a14460312ca51e966a017322d0f186` |
| A 组原始参考核（`weather_kernel_reference.cpp`） | `eb48f45cd25e884ff12e1fc8ec0562814595ac62aa29fc289d2e7c254053b349` |
| 原始模型类型/合同（`weather_kernel.h`） | `a678c4616a189bd8f9d2ccc4dcb4b183be1ca92f98d69eeffef69bb23813a47f` |

- 两套模型均为原 A C8 固定参数，task 0 去雨 / 1 去雾；无运行时权重指针。
- 输入/输出是 signed INT16 Q14，RGB NCHW，raw/16384；输出钳位到 [0,16384]。
- 权重 INT8，偏置与累加 INT32，中间激活 INT16；内部各节点的小数位从原参数读取，不能统一解释为 Q14。
- 重定标使用最近偶数舍入 RNE，保持卷积输出饱和、独立残差缩放、残差相加饱和、ReLU 的原有顺序。
- ROM 顺序加载到片上层参数寄存器、特征 URAM、行缓存和独立 DDR writer 属于硬件调度修改，不改变上述数值规则。
- host 全量逐层/整帧、两任务 HLS，以及任务/尺寸/跨 tile RTL 均通过；所用报告与哈希在 `../evidence/system_lineage_20261020.json`。

## 旧低照度与系统

原 V1.2 BD 的 SHA-256 为 `5d21aebbc75dac5f86a95059a0d240f8469e999b3a6e08b526f8d76265564bfa`。保留其全部 385 个 PS 配置以及旧模块 CSR/DDR 路由。当前新 BD/CSR/RTL 身份以实际 `interface_final_audit.json` 和候选清单为准。

低照度 CNN 重建的 305 项原 payload 中 303 项逐字节一致，差异仅为 component.xml、dfx_runtime.txt。三个 writer 按历史输入/补丁哈希恢复；未修改网络、增强公式或官方预训练权重。原 writer 补丁清单：

| Writer | 当前 SHA-256 |
|---|---|
| `zero_dce_cnn_top_row_axi_writer.v` | `4535bf94f686dc5e71f9a55dda9792c03aa8b57d998b902b1e596979dcb08611` |
| `zero_dce_cnn_top_row_axi_writer_2.v` | `5fb901f88917777169a6327bb27eed4e2171df4e2e17d3b3cb435e17fc4ebf0d` |
| `zero_dce_cnn_top_p_anonymous_namespace_output_writer.v` | `ed13125479a3892cfbfc2df20f5b4c010c6d2198503231afe7fbfca4ef543dc5` |

生成后的 Verilog 和 ROM `.dat` 与两套 RTL 回归输入逐字节核对。Vivado 复制包的元数据校验和刷新记录在 build.json；不把旧 bitstream 或历史板测身份冒充当前构建结果。最终 bit/XSA/DCP/报告的哈希在候选 manifest.json。
