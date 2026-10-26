# D 模型 K26 上板文件

本目录为独立 D 镜像，使用冻结的 INT16 权重。旧 Weather、GridDehazeNet、低照度核属于各自镜像，当前 bit 不包含它们。

## 上板入口

- `compact_d_system.bit`：Vivado/JTAG 位流。
- `compact_d_system.bit.bin`：同一位流的 bootgen 转换结果，供下游 FPGA manager 集成。
- `compact_d_system.xsa`：包含同版 bit 的硬件平台。
- `compact_d_system.hwh`：完整系统 HWH，与 XSA 内文件一致。
- `INTERFACE.md`、`xcompact_d_top_hw.h`：DDR、寄存器和数值合同。
- `driver/compact_d_top_v1_0/`：随此 HLS IP 导出的裸机寄存器 API 和 Linux UIO 控制 API。
- `model_int16/`：与镜像绑定的 A 参数及清单；运行时无需 DMA 上传权重。
- `validation/`：8×8、33×47、17×1280、720p 输入及整数 Golden，以及最大宽度 RTL 输出证据。
- `validation/sources/`：与 `reports/build.json` 中 SHA 完全匹配的实际仿真测试台源码及身份说明。
- `RELEASE_SUMMARY.md`：bit、bit.bin、XSA、HWH、寄存器、时钟/复位和 SHA-256 的交付摘要。
- `reports/`：实际综合、RTL、布线、时序和构建记录。
- `ps_init/`：XSA 中导出的 PS 初始化文件，由下游按现有启动流程使用。

控制基址 `0xA0050000`，cookie `0x44433031`，PL 时钟 200 MHz。输入、输出分别经 HP0、HP3 访问低 2 GiB DDR。调用侧须提供两个不重叠、物理连续且 cache 一致的缓冲区；720p 共需约 10.55 MiB。详细布局和启动顺序见接口合同。

目录中的驱动是与本版 IP 同源的 HLS 生成驱动，提供 AXI-Lite 控制寄存器 API；Linux 文件使用 UIO 映射控制寄存器。它不分配 DMA 缓冲区，也不负责 cache 一致性、设备树配置或视频应用流程。具体驱动文件哈希见 `SHA256SUMS` 和 `RELEASE_SUMMARY.md`。

## 已有证据

Host 和 CSim 各完成 12 帧、22 节点整数对齐；RTL 小图套件完成 12 帧及 3 次非法调用。两帧 17×1280 的活动输出与 A Golden 一致，大图完整套件未完成。200 MHz 布线后 setup WNS 0.328 ns、hold WHS 0.010 ns，路由完整。

720p 完整 RTL、真板数值、DDR 连续帧及 30 FPS 实测尚未完成。6 phase/像素对应的约 27.65 ms 仅是计算主体预算，不含流水填充、DDR 停顿等开销。

## 文件核验

`SHA256SUMS` 记录落盘字节的 SHA-256。可运行项目中的 `tools/collect_board.py --out 本目录 --verify-only` 核对全部文件、XSA 内外 bit/HWH 及 BIN payload。下游使用本目录内成套文件，不混用旧接口或其他模型参数。

原始 INT16 输出比较示例：`python compare_output.py --expected validation/random_8x8/21_output.relu.i16 --actual board_output.i16 --height 8 --width 8`。要求原始整数零差异，不用显示图代替数值比较。
