# 上板前准备

用于模型导出、量化、定点化分析、权重转换和逐层结果校验。

`ptq_cnn_initial.py` 是早期 CNN-only INT8 试验；`zero_dce_integer_ptq.py` 是当前端到端整数软件原型。后者从仓库根目录运行，生成可版本管理的 `configs/zero_dce_pp_integer_rules.json`，并将权重、查表、逐层测试向量和结果放到受 Git 忽略的 `outputs/zero_dce_pp/quantization/integer/`。

候选位宽和舍入规则见 `docs/zero_dce_pp_integer_quantization_report.md`。脚本将 CNN 输出 `A_low` 转成 Q14，按 `configs/zero_dce_pp_a_low_interface.json` 导出小端 NCHW DDR 测试数据。

`export_hls_cnn_package.py` 将量化权重、偏置、逐通道小数位和 Tanh LUT 打成 HLS top 使用的无头小端数组。HLS CNN top 的指针、工作区、控制和缓存所有权见 `configs/zero_dce_pp_hls_interface.json`；实际物理 DDR 基地址由 Vivado/PS 集成分配。HLS 仿真、综合和板端验收仍未执行。
