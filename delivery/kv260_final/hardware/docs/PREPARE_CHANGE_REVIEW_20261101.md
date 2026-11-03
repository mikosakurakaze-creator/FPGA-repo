# Prepare 改动审阅

用户要求修复 prepare 的逐项 DDR 写入，并复查其余核的 burst。分支仍为 `feat/software`，未暂存、提交、推送或切换分支。

| 文件 | 原因与关键差异 |
| --- | --- |
| `hls/joint_adapters.cpp`、`.hpp` | 128-bit DDR 字、384 像素分块、片上 HWC→NCHW 重排、五任务 DATAFLOW、独立原图/D 写回；CNN 小图在同次读取中完成，保持冻结数值与寄存器合同 |
| `tests/tb_prepare.cpp`、`scripts/check_prepare.py` | 对照 Git 锁定旧源码逐元素比较；完整帧 native 和厂商 AXI RTL 联仿，非法 cookie 不写入；失败尝试保留 |
| `scripts/build_system.py`、`system_build.tcl` | 在新目录使用新 prepare；审计四条 master 到 PS HP 的实际 128-bit 路径；允许源匹配的综合先进入联合构建，最终导出仍强制 RTL 验收 |
| `scripts/verify_prepare_pipeline.py`、`accept_system.py` | 新 prepare 源码、IP、三输出 Golden、RTL、综合与实际集成证据加入最终验收 |
| `scripts/collect_delivery.py`、`delivery_supplement.py`、`verify_delivery.py` | 新 ZIP 包含 prepare 源码、验证报告和哈希；从实际 HWH 复查 128-bit 接口 |
| `scripts/finish_prepare_delivery.py` | 依次完成联合实现、覆盖检查、验收、导出、打包和独立 ZIP 核验；任一失败即停止 |
| `docs/prepare_pipeline.md`、`README.md` | 记录结构、编码、验证边界及其余核 burst 复查结论 |

已执行：`native01` 三张完整图、16,542,360 标量零差异；`cosim04` 一张完整图、三路输出逐元素通过及非法配置不写入，合法帧 1,726,832 拍，按实际时钟约 17.2685 ms；`controller_tests03` 32 项主机测试通过。新 HLS 推断四条接口的 128-bit burst；关键读、转换、写循环 II=1，综合估算约 19.0326 ms。`prepare_pipeline_acceptance.json` 已通过，实际集成宽度 14 项审计全部为 128 bit。

CNN 行读写、D 行读写、Curve 连续读写及 Bilinear 主要行读/输出均已形成 burst。Bilinear 首次两行填充仍有 636 个标量单次读，属于启动流量。未发现第二个承担整帧大流量却逐项写 DDR 的同类问题。

联合实现已通过：LUT 86,385/117,120，FF 97,379/234,240，BRAM 100/144 tiles，URAM 58/64，DSP 948/1,248。194,373 条需布线网络全部完成，路由错误为零；setup/hold 失败端点均为零，WNS 0.000 ns、WHS +0.002 ns。WNS 按报告精度显示为零，余量很紧，不代表宽裕。实际 checkpoint 的 setup/hold 负路径查询均为空。最紧 setup 路径位于 D 核卷积窗口更新使能，数据延迟 4.711 ns 中逻辑 0.485 ns、布线 4.226 ns；本次联合布局拥塞不能误归因为 prepare 自身未流水。

原始记录在 `D:/weather_builds/joint_prepare_pipeline01_20261101`。本次使用旧 routed checkpoint 加速增量实现，验收针对新设计的实际 checkpoint；没有降频、添加时序例外或改动冻结模型。最终导出的重复时序、时钟覆盖、总线偏斜和文件身份检查以包内 `manifest.json` 及 `reports/` 为准。包外 `_verified.json` 记录独立 ZIP 核验，ZIP 内 `SHA256SUMS` 覆盖交付文件。未上板，未验证整机持续 30 FPS。

建议 Commit Message：`fpga: burst and pipeline RGB prepare with shared resize pass`
