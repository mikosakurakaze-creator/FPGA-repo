# KV260 低照度 + Compact D：续做任务 4–6

日期：2026-10-29。工作树：`feat/software@9ef5faf`。本轮前三项基线固定为用户补交后的 `codex/curve-fp32-baseline@3c9e41a`；D IP 固定为 `weather_fpga_integration@d8880cc`。所有队友分支只读，没有合并其提交。

## 当前交付范围

| 项目 | 真实状态 |
| --- | --- |
| 远端各分支/Release/Tag/Actions 审阅 | 完成；见 [REMOTE_AUDIT.md](REMOTE_AUDIT.md) |
| 任务 4：三路融合 | RTL、数值/AXI 仿真、完整帧 Golden、IP 导出和 ABI 核对；原始执行结果见 `evidence/` |
| 任务 5：系统集成 | 六核 BD、地址/DDR/时钟复位、联合综合和布局布线通过；独立时序/route/CDC/DRC/bus-skew 与同图数值验收通过 |
| 任务 6：可上板包 | **完成硬件包交付**；bitstream/XSA/HWH、地址表、报告、Golden、加载入口和哈希均已生成及校验；状态 HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED |

任务 4 是新增手写 RTL IP `joint.local:rtl:joint_fusion:1.0`，不冒用 HLS driver。输入为三个 signed Q14 图像，权重接收完整 UINT32/Q15；启动锁存权重、指针及 frame_id，检查通过后才访问 DDR。signed64 一次累加、RNE、最后 `[0,16384]` 裁剪。IP 的精确寄存器和错误合同见 [fusion_contract.md](docs/fusion_contract.md)。

最终实现选择 L/D 输出只读别名，不增加两个无必要的 raw-copy 实例。融合使用一个 32-bit、64-bit 地址、单 outstanding AXI master；该方案没有承诺 30 FPS。软件调度须独占硬件，并由真实后端正确实现 DMA/cache/MMIO 所有权。

## 已实际验证

- Icarus Verilog：10 个有效帧 ×65,536 标量，逐元素对照独立 signed-floor Golden，覆盖每路完整 INT16 编码、三个 one-hot、均衡/极端权重、全零/零分支、上下裁剪及正负最近偶数中点。
- 9 个非法调用：零和/超额和/高位非法/无符号溢出权重、cookie、高地址、不对齐及重叠输出；全部零 DDR 事务。另注入读/写错误，检查失败返回。
- 运行中改写三个配置权重、输入指针、frame_id，并再次写 start；当前帧数值和完成 ID 保持启动时的快照。AXI slave 模型对 AR/R/AW/W 注入等待，独立处理 AW/W 并核对 B 响应。
- 完整生产尺寸：2,747,520 标量逐元素一致；4,121,280 次 32-bit 读、1,373,760 次 32-bit 写，覆盖整帧末端及全部线性 NCHW 地址。
- 7 个 host 调度单元测试：两条路径任意先完成、两帧不同 ID、残留 done、错误/超时禁止融合、失败禁止复用、错误完成帧禁止输出交 CPU。

另已增加真正的同图 Golden：在 RGB8 输入边界将锁定 `night_01.jpg` 中心裁剪为 1272×720，两模型均按此输入重新运行。历史 CNN 19,080 标量首先零差异；实际锁定 HLS C/native 模型串起 prepare、CNN、Bilinear、Curve、D 后共比较 13,775,760 标量，全部一致。实际融合 AXI RTL 对此三路输出再比较 2,747,520 标量，全部一致。没有裁剪旧 1280 宽 D 网络输出；这些结果不等于完整六核联合 RTL 或板端验证。26 个 controller/验收门禁单元测试通过，包含 bus-skew 缺项及负 slack 拒绝测试。

融合 IP 已完成 Vivado integrity 与 ZIP CRC、源 RTL/寄存器/指针宽度/固定尺寸核查。OOC 实际生成报告与 checkpoint 后出现 Vivado 退出异常；不能把原失败进程记为 PASS。独立重读同一 checkpoint 的复核结果及实际资源/时序以 `evidence/review.json` 为准；任何单核估算都不是联合布局布线签核。

## 依赖恢复与继续顺序

用户已补交 `delivery/lowlight_frozen_ip_20261028.zip`，SHA256 为 `b5b69f1d3d1e3f69e9f825be5453b086c58b4d863a3a9889693a247101b9c2cf`。CNN 308、Bilinear 60、Curve 38，共 406 个文件全部逐字节匹配旧冻结清单，原缺件阻塞已解除。见 `evidence/received_dependency_audit.json`。原 `dependency_audit.json` 保留初次缺件审计历史，不表示当前仍缺件。

六核设计位于外部 `D:/weather_builds/joint_system05_20261029`。prepare 由锁定源码成功重建并核对导出 ABI；fusion revision 2 取消封装中写死的 FREQ_HZ，以匹配 PS 真实 99,999,001 Hz 元数据，RTL 字节未变。D 保持 199,998,001 Hz，两个时钟域分别同步复位并通过双时钟 SmartConnect 连接。新增 master 的 DDR LOW 映射与 A000–A005 六个 64 KiB 控制地址均已实际检查。

联合综合和布局布线均正常退出。最终 routed 资源为 LUT 78,753（67.24%）、FF 92,793（39.61%）、BRAM 72.5（50.35%）、URAM 58（90.63%）、DSP 922（73.88%）；URAM 为主要容量瓶颈。最终 WNS +0.032ns、WHS +0.010ns、WPWS +1.700ns；183,014/183,014 routable nets 全部布线，routing errors=0，17 项 bus-skew 最差 slack +3.898ns。最终原始 no_clock、constant_clock、multiple_clock、unconstrained_internal_endpoints 均为 0。另对同一 routed DCP 的 8 个未用 PS8 输出逐项证明零负载，未加假时钟或 waiver。验收绑定 checkpoint SHA256=`a189968e406be1ec94bd0355f97bd63758813ef75101b50eb26b7f064ad85b2a`。

综合出现的 8 个 no_clock 已定位为 PS8 未连接 EMIO 外设输出。综合诊断及独立重开同一 routed/export DCP 的审计均证明零 PL 输入负载、零顶层端口；最终 routed/export 原始 no_clock 均为 0。所有原始计数保留，不加虚构时钟、false-path 或 waiver；详见 [clock_coverage.md](docs/clock_coverage.md)。

## 最终本地交付

- 目录：`D:/weather_builds/kv260_joint_delivery_20261029/`。
- ZIP：`D:/weather_builds/kv260_joint_delivery_20261029.zip`，204,274,955 字节。
- ZIP SHA256：`01f0ac7214f1ed8fad6df4adb2b453a31fe751e8ebd38b8462fd91a6ea39a047`。
- Build ID：`ddc052ce9f6385f3ac7d`。111 个 payload 文件，另有 manifest 和 SHA256SUMS，共 113 个文件；112 条校验记录全部通过，ZIP CRC/全部 payload 也已重读校验。
- 根目录 `joint_system.bit` 是 XSA 中唯一内嵌 bit 的逐字节副本；`joint_system.hwh` 是唯一包含六核的 `system.hwh`。其余 5 个 HWH 是 SmartConnect 子模块，不用作顶层 overlay。
- Vivado 独立 bitgen 与 XSA 再次 bitgen 的创建时间头不同，但 design/part 和 7,797,692 字节配置数据完全一致。两个原始文件均在构建目录保留，交付目录采用 XSA 内嵌 bit 为唯一规范版本。证据见包内 `evidence/bitstream_equivalence.json`。
- XSA 导出正常退出并报告可用于 Hardware，同时保留 `WARNING::74 Unsupported FPGA device name xck26-sfvc784-2LV-c`；原始 `evidence/export_console.log` 随包归档。未将此结果描述为 Vitis/BSP/板端编译验证。

加载顺序与环境要求见包内 `docs/loading_order.md`；原始 Golden、22 个 D 节点、实际 HLS C/native 与融合 AXI RTL 日志、真实阶段日志和 Tcl 均随包交付。仍未上板、未完成六核联合 RTL，也没有实测耗时/FPS。

## 重现入口

在本工作树根目录执行，每次 `--out` 使用新的 ASCII 外部目录；不覆盖旧证据：

```powershell
python fpga/joint_lowlight_compact_d/scripts/check_dependencies.py --ip-root D:/weather_builds/joint_received_20261029/ip --out D:/weather_builds/joint_deps_new.json
python fpga/joint_lowlight_compact_d/scripts/run_checks.py --stage rtl --out D:/weather_builds/joint_rtl_new
python fpga/joint_lowlight_compact_d/scripts/run_checks.py --stage full --out D:/weather_builds/joint_full_new
python fpga/joint_lowlight_compact_d/scripts/run_checks.py --stage package --out D:/weather_builds/joint_package_new
python fpga/joint_lowlight_compact_d/scripts/run_checks.py --stage ooc --out D:/weather_builds/joint_ooc_new
python fpga/joint_lowlight_compact_d/scripts/run_checks.py --stage verify --checkpoint D:/weather_builds/joint_ooc_new/ooc/fusion_ooc.dcp --out D:/weather_builds/joint_verify_new
python -m unittest discover -s fpga/joint_lowlight_compact_d/tests -p 'test_*.py' -v
```

同图验证和联合硬件阶段依次运行（示例新目录；先准备锁定 Compact D 数值 bundle）：

```powershell
python fpga/joint_lowlight_compact_d/scripts/make_joint_golden.py --out D:/weather_builds/joint_golden_new
python fpga/joint_lowlight_compact_d/scripts/verify_joint_models.py --stage host --golden D:/weather_builds/joint_golden_new --out D:/weather_builds/joint_host_new
python fpga/joint_lowlight_compact_d/scripts/verify_joint_models.py --stage fusion --golden D:/weather_builds/joint_golden_new --out D:/weather_builds/joint_fusion_image_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage prepare --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage adapter --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage create --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage synth --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage implement --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage coverage --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/accept_system.py --build D:/weather_builds/joint_system_new --host D:/weather_builds/joint_host_new --fusion D:/weather_builds/joint_fusion_image_new --golden D:/weather_builds/joint_golden_new
python fpga/joint_lowlight_compact_d/scripts/build_system.py --stage export --out D:/weather_builds/joint_system_new
python fpga/joint_lowlight_compact_d/scripts/collect_delivery.py --build D:/weather_builds/joint_system_new --host D:/weather_builds/joint_host_new --fusion D:/weather_builds/joint_fusion_image_new --golden D:/weather_builds/joint_golden_new --out D:/weather_builds/kv260_joint_delivery_new
```

Golden 入口需要 numpy/Pillow；本机实际使用 `D:/Dev/Miniconda3/envs/lowlight-fpga/python.exe`。其他入口使用 `D:/Dev/Miniconda3/python.exe`。阶段失败保留原记录，修复后用 `--attempt N` 写新尝试；不把失败 receipt 改为成功。

脚本默认 Vivado 2025.2=`D:/vivado/2025.2/Vivado`、Icarus=`D:/iverilog/install`；可用参数换安装目录。厂商 DLL 只从对应安装复制到新输出目录，未修改安装或系统配置。构建目录含真正命令、退出码、原始日志、源码/工件 SHA。任何缺少成功标记、非零退出或身份不符均保留失败记录。

本轮仅新增本目录内容，未修改官方 Zero-DCE++、模型参数或 Epoch99.pth，未暂存/提交/推送/合并/切分支。完整变更审核与建议 Commit Message 见 [CHANGE_REVIEW.md](CHANGE_REVIEW.md)。

最终报告保留 CDC-15 的 471 项 Warning（均位于 cnn_data_sc/curve_ddr_sc 内 XPM memory FIFO）、冻结 DSP 的 DPIP/DPOP 流水线 Warning 和一项 RTSTAT-10（35 条无可布线负载内部网）。没有 Critical CDC、DRC Error 或 Critical Warning；没有压制原始报告。这些检查不等于完整六核 RTL 或上板验证。
