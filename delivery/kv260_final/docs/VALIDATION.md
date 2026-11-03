# 验证范围与原始证据

## 硬件身份与实现

Build ID `c6496c6dc89aa54c4500`，Vivado 2025.2，K26 `xck26-sfvc784-2LV-c`。原始 manifest：LUT 90753 / 117120（77.49%），FF 90929 / 234240（38.82%），BRAM 112 / 144（77.78%），URAM 58 / 64（90.63%），DSP 945 / 1248（75.72%）；WNS 0.391 ns，WHS 0.100 ns，路由错误0。主通路100 MHz，去雨雾200 MHz。以上数值只属于随包镜像，不能用于新实现结果。

## 功能正确性

- `hardware/evidence/same_image_hls_host.json`：冻结 HLS C 模型与独立同图整数 Golden。
- `hardware/evidence/fusion_pipeline_acceptance.json`、`prepare_pipeline_acceptance.json`：融合/Prepare 独立数值、RTL及集成通路证据；不宣称完整六核系统 RTL 联合仿真。
- `validation/fifo_hardware/result.json`：最终镜像43项、1800帧。140帧完整逐元素 Golden、1410帧 RGB CRC；600帧长测只有首尾执行完整 Golden，不能写成1800帧全部完整 Golden。
- `validation/board/fast_driver_validation.json`：六个不同输入、三分支以及1/3/6/2/6尾批长度与历史输出逐字节一致。
- `validation/board/fast_ui_validation.json`、`fast_output_validation.json`、`dynamic_gallery_validation.json`：视频处理输出、播放暂停/继续与检测框联动。
- `validation/host/host_tests.log`：本次打包后32项调度、缓冲所有权、超时及结果统计主机回归通过，不启动PL。
- 本次整理脚本产生的三分支逐字节实测文件位于 `validation/package_board`，以各 JSON 的 `pass_all` 和输出 SHA256 为准。

## 性能口径

`validation/fifo_hardware/result.json` 中600帧 `hw_prepare_long` 的批次吞吐为28.36976帧/s，完整调用吞吐为28.32405帧/s；三个120帧PS准备测试为27.16997、27.19686、27.20966帧/s（batch口径）。这些是本包能绑定的原始记录，不能直接替换为作品草稿中的31.37或30.324。

以上 benchmark 使用已解码同图输入，不包含压缩视频解码、显示、文件保存和目标检测。GUI完整无检测视频测试约3.79帧/s，见独立软件记录。功耗仅覆盖VCC_SOM，功耗与帧率必须引用同组采样；不混用其他版本统计推算能耗。

本次整理不重新训练、不重新量化、不改变 bitstream，也未重新运行 Vivado 综合/布局布线。可移植硬件脚本已验证文件准备与FIFO源码恢复，实际新实现须重新执行全部硬件验收。FIFO内部最大占用/满周期等计数未暴露，不作为已测指标。

板端系统时钟存在偏差，历史记录中的设备时间不用于推断真实实验日期；整理日期采用会话日期2026-11-03。
