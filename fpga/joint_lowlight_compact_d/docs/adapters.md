# 编码适配 IP 与验证

2026-10-28。实现范围为任务 3，精确数值、缓冲所有权和完整寄存器表见 [接口合同](interface_contract.md)。

## 两个可复用 top

`joint_rgb8_prepare` 接收固定 720×1272 RGB8 HWC，一次调用生成三个独立 DDR 张量：全分辨率 I Q14、全分辨率归一化 D_input Q14、60×106 CNN_input Q14。前两者不缩放或改变颜色空间；CNN 使用冻结的四中心点采样。I 同时供 Curve 和融合只读，确保两条模型路径来自同一原图。D 从 RGB8 直接量化，避免 256 个 RGB8 码值中 128 个产生的二次量化差异。

`joint_q14_copy` 实现固定 2,747,520 个 signed INT16 原码的 DDR 复制。L/D 现有格式已是 RGB/NCHW/Q14，转换不需要数值运算。该 IP 可分别实例化两次；若最终集成允许生命周期安全的只读别名，也可直接让融合读取模型输出而省去复制。所有负值和大于 16384 的值都保持，最终裁剪由融合负责。

两者均使用 AXI-Lite + 自带 AXI4 master、10 ns 目标周期、低有效同步 `ap_rst_n`，无 AXI Stream 或外置 DMA。成功返回 0；cookie 错误返回 -1，先于图像访存。无运行时宽高参数，输入必须恰为合同尺寸。实际导出 driver 的所有指针均为 64 bit，偏移与接口合同一致。

## 实际验证

| 验证 | 实际结果 |
| --- | --- |
| GCC Host | 六张量 13,756,680 个标量，逐元素 0 mismatch |
| Vitis HLS 2025.2 CSim | 两个 top 均 PASS，同样全量 0 mismatch |
| 数值/边界 | 全部 256 RGB8 值、全部 65,536 signed INT16 值；cookie 错误调用和输出末端 guard 通过 |
| HLS synthesis/export | K26、10 ns；两 top 均完成并导出 IP ZIP |
| 实际 AXI-Lite ABI | 生成 header 的 offset/width 逐字段核对 PASS |
| RTL co-simulation / 联合模型 RTL / 上板 | 本次未执行 |

独立 Golden 用 Python `Fraction` 精确有理数计算 RGB8 量化及四点平均，不调用 HLS 算术实现。另使用已有完整低照度 Golden、D 历史原码和 signed 全域图样验证 bit-copy。每个数字验证阶段先清理其六个已知 actual 文件，避免误用上阶段输出；逐元素检查通过后再核对二进制 hash。所有输入、实际输出和日志保存在外部 build 目录。

D 的原有全帧 Golden 宽度为 1280。本测试按通道、按行取其前 1272 列，仅构造具有真实 D 输出原码的 copy 适配测试夹具；该过程不证明 D 网络运行在 1272 宽时的结果，也不证明新的 RGB8 图经过两套模型后的联合全链正确性。低照度旧 Golden 来自 FP32 源，未声称新 RGB8 图重现同一旧 Golden。

## HLS 估算资源

| Top | LUT | FF | DSP | BRAM18 | URAM | 估算周期 |
| --- | ---:| ---:| ---:| ---:| ---:| ---:|
| `joint_rgb8_prepare` | 5,889 | 4,005 | 10 | 2 | 0 | 7.300 ns |
| `joint_q14_copy`，单实例 | 2,296 | 1,766 | 0 | 2 | 0 | 7.300 ns |

这些是 HLS 估算，不是联合 Vivado 系统利用率。若使用两份 copy，需计入两个实例以及新增互连；任务 2 的四核检查不含这些新 IP 和融合 IP。HLS 静态循环延迟不表示真实 DDR 或板端耗时。

## 重建与文件

在仓库根目录执行，`--out` 使用新的纯 ASCII 外部目录，不要覆盖已审阅结果：

```powershell
python fpga/joint_lowlight_compact_d/scripts/validate_adapters.py --out E:/HLS/joint_adapters_new --stage prepare
python fpga/joint_lowlight_compact_d/scripts/validate_adapters.py --out E:/HLS/joint_adapters_new --stage native
python fpga/joint_lowlight_compact_d/scripts/validate_adapters.py --out E:/HLS/joint_adapters_new --stage csim
python fpga/joint_lowlight_compact_d/scripts/validate_adapters.py --out E:/HLS/joint_adapters_new --stage synth
python fpga/joint_lowlight_compact_d/scripts/collect_adapter_evidence.py --build E:/HLS/joint_adapters_new --out E:/HLS/joint_adapters_new/review
```

脚本默认使用本机 Vivado/Vitis 2025.2 和已冻结低照度外部 Golden；可通过 `--vitis/--compiler/--lowlight` 显式指定。D 夹具从锁定 Git commit 读取，不切分支。缺少完整旧 Golden 时失败，不用任意数据替代。

本次 build 为 `E:/HLS/joint_lowlight_compact_d_20261028/adapters/`。两个实际可导入 IP：

- `joint_rgb8_prepare/hls/impl/ip/xilinx_com_hls_joint_rgb8_prepare_1_0.zip`
- `joint_q14_copy/hls/impl/ip/xilinx_com_hls_joint_q14_copy_1_0.zip`

小型审阅证据保存于本目录上级 `evidence/adapter_evidence.json`，包含 ZIP/component/driver/源码 hash；`native_result.json`、`csim_result.json`、`synth_result.json` 记录真实执行结果，`golden_manifest.json` 记录每个夹具的来源和 hash。生成的 ZIP、原码、日志与工具工程不自动进入 Git。
