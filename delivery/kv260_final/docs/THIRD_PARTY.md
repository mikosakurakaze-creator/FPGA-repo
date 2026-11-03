# 第三方来源

- GUI：系统 GTK3、PyGObject、Cairo；图像/数组：Pillow、NumPy。使用 Ubuntu 22.04 系统包，许可证由系统发行包保留。
- 检测：ONNX Runtime 1.23.2 ARM64 wheel（MIT），SSD-MobileNetV1 ONNX Model Zoo 模型（模型仓库 Apache-2.0）。来源：https://github.com/onnx/models/tree/main/validated/vision/object_detection_segmentation/ssd-mobilenetv1 。wheel 内附发行许可证。
- 视频：FFmpeg 7.0.2 ARM64 static 发行包，来源 https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz 。包内保留 GPLv3.txt 与发行 readme；源码获取与构建说明见该发行方网站 https://johnvansickle.com/ffmpeg/ ，重新分发应保留对应许可证与源码获取信息。
- Vivado/Vitis、器件库、SmartConnect/XPM 等由 AMD 工具链提供，需自行安装与使用相应许可；包内保留实现所用生成文件及来源记录。

本说明不改变任何上游文件许可证。runtime_assets 的逐文件身份由本包 SHA256SUMS 固定。
