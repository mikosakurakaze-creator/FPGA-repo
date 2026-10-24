# 同版 INT16 参数与 layout

本目录是当前 bit/XSA 对应的 A 组 outdoor GridDehazeNet 参数。`parameters.bin`、`manifest.json`、`graph.json`、`scale_config.json` 都按原始字节复制，未重新量化或导出。

- Bundle：`5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710`。
- manifest SHA-256：`7a45b152864fbb692f966a276806022ed88ef446c95c54a4444c546aedbb26c2`。
- parameters：1,933,120 字节；SHA-256 `5f49d702fedb6745a44fba401ae48438780abd6a65b5e2985ae3a70c16c16cac`。
- 原始 `scale_config.json` 使用 CRLF，且它的哈希已冻结在 A 组 manifest 中，必须保留；发布目录采用 Git `-text` 防止 checkout 改字节。其他新写的发布说明/清单采用 UTF-8 无 BOM、LF。原始仿真日志和实际执行的 SV 同样保留原字节。

## 交给软件侧的约定

输入/输出为 batch=1、RGB、NCHW、小端 signed INT16；输入 F14，输出 F13，中间逐节点尺度。不要把整个网络都当作 Q14。卷积权重 OIHW，反卷积 IOHW，bias INT64，硬件累加器为 48 位。逐通道 shift、图结构已经固化在硬件，不额外拼接到权重 blob。

`layout_33x47.bin`、`layout_675x1280.bin`、`layout_720x1280.bin` 都用本版 `tools/emit_model.py` 从同一冻结图实际生成；每个文件 1,344 字节。它们包含尺寸、bundle 身份及相对 scratch 偏移，**不包含板端物理地址**。精确容量和哈希见 `layout_sizes.json`：

| 尺寸 | 输入/输出各字节数 | scratch 字节数 |
|---|---:|---:|
| 33×47 | 9,306 | 794,240 |
| 675×1280 | 5,184,000 | 442,368,000 |
| 720×1280 | 5,529,600 | 471,859,200 |

这只是图内存规划，不代表板端已成功分配对应连续 DMA 内存。更换尺寸必须重新生成对应 layout，不能只改寄存器 H/W。运行前软件侧应核对参数哈希，独立分配 input/output/scratch/parameters/layout，保持 64 字节分配对齐和低 2 GiB 地址范围；具体寄存器、轮询 DONE、返回码和共享复位限制见发布根目录 `frame_interface.md`。

`../validation_33x47/` 提供可直接用于本版新核核查的输入、预期输出和导出 RTL 冷暖输出。它们不是板端实测结果。675p/720p 本轮只生成了 layout，没有执行对应尺寸的 FPGA 推理或性能测试。
