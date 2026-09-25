# 上板前准备

用于模型导出、量化、定点化分析、权重转换和逐层结果校验。

`ptq_cnn_initial.py` 是早期 CNN-only INT8 试验；`zero_dce_integer_ptq.py` 是当前端到端整数软件原型。后者从仓库根目录运行，生成可版本管理的 `configs/zero_dce_pp_integer_rules.json`，并将权重、查表、逐层测试向量和结果放到受 Git 忽略的 `outputs/zero_dce_pp/quantization/integer/`。

候选位宽和舍入规则见 `docs/zero_dce_pp_integer_quantization_report.md`。脚本将 CNN 输出 `A_low` 转成 Q14，按 `configs/zero_dce_pp_a_low_interface.json` 导出小端 NCHW DDR 测试数据。CNN IP 的 DDR 写接口、缓冲地址、控制寄存器和板端可行性尚未验证；不能把软件结果称为硬件验收。
