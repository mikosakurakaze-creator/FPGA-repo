# 配置

用于保存可版本管理的模型、量化、部署和评估配置。

配置中不得写入本机绝对路径、账号凭据或密钥；本地专用配置应使用忽略文件或示例模板。

`zero_dce_pp_integer_rules.json` 是当前软件整数化候选方案的逐层小数位、权重形状和卷积参数。其含义及验证限制见 `docs/zero_dce_pp_integer_quantization_report.md`。

`zero_dce_pp_a_low_interface.json` 固定 V1 CNN→Bilinear 的 `A_low` 为 `[1,3,60,106]`、RGB 平面 NCHW、有符号 INT16 Q14，并约定可复现 DDR 测试数据的字节顺序和长度。

`zero_dce_pp_hls_interface.json` 定义 `zero_dce_cnn_top` 的 AXI4-Lite 控制、m_axi DDR 输入/权重/工作区/输出、缓冲区大小和缓存所有权规则。物理 DDR 基地址和 Vivado 地址映射仍由系统集成侧分配。
