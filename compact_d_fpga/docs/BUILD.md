# 本地重建

工具版本为 Vivado/Vitis HLS 2025.2，器件 `xck26-sfvc784-2LV-c`。构建目录使用无空格的英文绝对路径；源码目录可以包含空格。以下命令在本项目根目录执行，所有输出目录需尚不存在。

## 参数和 Golden

参数来自 A 的 `feat/software@9ef5faf`，不重新训练或调整尺度。从 A 仓库根目录、使用其依赖环境运行：

```powershell
python -m models.compact_d.fixed.export --out D:/d_build/package
python -m models.compact_d.fixed.suite --package D:/d_build/package --out D:/d_build/golden
```

上板目录中的 `model_int16/` 也可直接作为 `--package`。`hls_build.py` 的逐节点测试需要完整节点 Golden；上板目录内仅供板端比较的输入、最终输出不等同于完整 suite。

## HLS 与 RTL

```powershell
python tools/hls_build.py --stage native --out D:/d_build/host --package D:/d_build/package --golden D:/d_build/golden
python tools/hls_build.py --stage csim --out D:/d_build/csim --package D:/d_build/package --golden D:/d_build/golden
python tools/hls_build.py --stage cosim --out D:/d_build/hls_cosim --package D:/d_build/package --golden D:/d_build/golden
```

`cosim` 阶段包含综合、IP 导出和 RTL 比较，不需要额外重复执行一次 `synth`。脚本提供 `--vitis`、`--compiler` 以调整本机工具位置，默认对应本次构建机器。默认测试为 12 帧及 3 次非法调用，包含冷暖、33×47、极小/奇数尺寸。

## Vivado

```powershell
python tools/system_build.py --stage create --out D:/d_build/system --hls D:/d_build/hls_cosim --ps-config system/k26_ps_config.tcl
python tools/system_build.py --stage synth --out D:/d_build/system
python tools/system_build.py --stage impl --out D:/d_build/system
python tools/system_build.py --stage export --out D:/d_build/system
```

`system/k26_ps_config.tcl` 为本次实际使用的旧 K26 PS 配置副本。构建 Tcl 在此基础上设置独立 D 的 200 MHz 时钟、HP0/HP3、复位和地址。无需依赖旧工程在原机器上的绝对路径。`system_build.py` 提供 `--vivado`。

本机实际实现使用 `--runtime D:/weather_builds/compact_d_vendor_runtime01`。该选项用当前工具安装中的同版 EXE/DLL 建立本地运行目录，未改变杀毒配置或原安装；其他机器正常启动工具时无需该参数。实际命令、源码/IP 哈希、日志和阶段结果保存在构建目录。

本机 Vivado 在完成命令后出现过退出清理异常。实现阶段的异常返回码保留；使用 `--stage verify_impl` 独立重开 routed DCP 并复核时序、路由后继续导出。验证/导出若仅在 PASS 标记和 Exiting 日志之后发生相同退出异常，记录 `clean_exit=false`，不冒充进程正常退出；交付文件仍需独立字节核验。

本次最终导出使用独立工作目录 `--work-dir D:/weather_builds/compact_d_export01`，最终产物仍写入系统构建目录。导出脚本以 XSA 内嵌 bit 为规范文件，直接提取为外部 bit，再由同版 bootgen 转换 BIN，避免重复生成 bit 的头部时间戳差异。

## 整理与核验

```powershell
python tools/collect_board.py --out board/k26_compact_d_20261025 --verify-only
```

这条命令只核对已交付文件。重新收集时，需通过 `--build`、`--hls`、`--numeric` 指向本次对应输出，并为 `--out` 指定新目录。当前收集脚本还会读取本机 Host/CSim 和最大宽度证据目录，因此用于本次本地整理；下游重新构建可以直接使用导出的 bit/XSA，自行保存新的验证记录。

若源码或参数变化，须重新生成 HLS IP 和系统 bit/XSA，不能沿用本次 SHA 或验证结果。
