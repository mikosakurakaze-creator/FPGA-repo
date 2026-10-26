# 仿真测试台身份说明

## 报告对应版本

`reports/build.json` 记录的 `hls_source_sha256.test_compact_d.cpp` 是：

`8450a700ff31385afb6253cdd8511800fc23dd95512993f6ae6d4a62b7f643c9`

与该记录匹配的实际源码已原样保存为：

`validation/sources/test_compact_d_report_8450a700.cpp`

## 仓库当前版本

`compact_d_fpga/hls/test_compact_d.cpp` 当前 SHA-256 是：

`ce650312c6473622f2418d5281e32122d54e7d9b505f2668b273661926524303`

## 差异

两份文件只有一处文本差异：仓库当前版本在每个 `D_FRAME_PASS` 输出行加入了 `work_cycles` 和 `input_cycles` 两个计数器字段。该差异只影响日志文本，不改变计算路径、比较条件、输出文件或非法调用检查，因此不会改变 RTL 数值结果；但源码身份不同，不能把仓库版 SHA 写成报告实际测试台 SHA。

发布包以 `validation/sources/test_compact_d_report_8450a700.cpp` 作为报告匹配副本。若重新执行仿真并使用仓库版，应在新报告中记录 `ce650312...`。
