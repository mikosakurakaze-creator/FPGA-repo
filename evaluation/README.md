# 测试、优化与 Base 对比

用于定义 V1 软件参考、量化结果与 FPGA 输出之间的正确性和性能评估方法。

后续记录增强结果、运行日志、延迟、帧率、资源利用率及与 Base 实现的对比。数据集和生成结果不纳入 Git 版本管理。

`test_zero_dce_integer_ptq.py` 检查整数舍入、缩放、Tanh/曲线规则、Q14 `A_low` DDR 字节流重载和 14 层测试向量。使用 `python -m pytest -q evaluation/test_zero_dce_integer_ptq.py` 从仓库根目录运行。当前仅验证 CPU 整数仿真；HLS、板端与性能测试尚未进行。
