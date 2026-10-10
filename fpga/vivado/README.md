# Vivado 集成

## V1.2 三模块交付入口

- [V1.2 当前状态](../docs/v1_2_status_for_team.md)
- [V1.2 仓库使用说明](../docs/v1_2_repo_guide_for_lzm.md)
- [V1.2 hardware handoff](../docs/v1_2_hardware_handoff.md)

## 历史 Fixed16 V1 重建说明

此目录跟踪 KV260 Fixed16 V1 的最小设计输入 `fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd`。其余 `.xpr`、IP OOC 文件、`.gen`、`.runs`、DCP、bitstream 和 XSA 都是生成物，不进入 Git。

`fpga/scripts/vivado_fixed16_reconstruct_v1.tcl` 用已保存的 BD 在**空目录**创建 Vivado 2025.2 工程，核对两只 HLS IP，执行 Validate Design、Generate Output Products 并创建 HDL wrapper。默认输出目录为 `E:/HLS/kv260_fixed16_v1_reconstructed`；也可设置 `KV260_RECONSTRUCTION_DIR`。脚本同时建立同级的 `<输出目录>_bd_source`，隔离 BD 工作副本与生成文件；拒绝覆盖已有目录。

重建依赖两个已经打包的外部 IP repository：

- `E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip`
- `E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip`

仓库跟踪对应 HLS 核心源码与配置，但当前重建脚本不会自动运行 HLS IP export。迁移到其他机器时，需先按源码重新打包 IP，并更新重建脚本中的 repository 路径。
