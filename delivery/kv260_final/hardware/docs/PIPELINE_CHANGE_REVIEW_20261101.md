# 流水融合改动审阅

日期：2026-11-01。分支：`feat/software`。本次只修改/新增工作区文件，不暂存、不提交、不推送，不操作队友分支。目标为 1272×720 三路融合与连续帧调用；30 FPS 需要最终真板持续测量。

## 修改内容

| 文件 | 修改原因与关键差异 |
| --- | --- |
| `rtl/joint_fusion.v` | 原逐字读算写替换为128位、最长64拍INCR突发；三个输入FIFO、一个输出FIFO、八路五级计算流水、独立读写引擎；支持4 KiB/帧尾切分、背压、错误事务排空。Q14/Q15、一次RNE、最后裁剪、指针/权重/frame_id快照与AXI-Lite ABI保持。 |
| `tests/tb_joint_fusion.sv`、`scripts/run_checks.py`、`scripts/verify_joint_models.py` | 全部八标量逐元素Golden、读写重叠、突发边界和短尾、长背压、RLAST/响应错误、阻塞AW时排空、全帧周期预算；使用冻结测试源保留每次真实执行身份。 |
| `scripts/fusion_package.tcl`、`build_system.py`、`system_build.tcl` | fusion revision 3；IP哈希锁定；实际fusion→SmartConnect→PS HP3全路径128位审计；重新进行六核联合综合和布局布线。 |
| `runtime/pipeline_controller.py`、`tests/test_pipeline_controller.py` | 每核独立owner，三槽多帧调度；同帧保留prepare、CNN→Bilinear→Curve、D及fusion完成依赖，跨帧允许不同核重叠，输出消费后才能复用槽位。 |
| `runtime/run_pipeline_pynq.py`、`tests/test_pipeline_entry.py` | 可显式在KV260执行的连续帧入口；按物理地址识别同名槽位；记录整批FPS、输出间隔FPS和逐帧哈希，区分批次延迟和稳态间隔。 |
| `scripts/verify_fusion_pipeline.py`、`audit_pipeline_evidence.py`、`run_host_tests.py`、`accept_system.py` | 源码/IP/日志/报告/Golden精确绑定；保留旧失败记录；冻结调度器与测试源，不把主机mock或融合仿真写成真板30 FPS。 |
| `scripts/collect_delivery.py`、`delivery_supplement.py`、`verify_delivery.py` | 新包内包含bit、Bootgen bit.bin、XSA、HWH、91寄存器表、时钟复位、Golden、源码/测试/报告及SHA256；重新打开ZIP验证CRC、哈希、XSA内嵌产物和BIN字节序。 |
| `docs/fusion_contract.md`、`fusion_pipeline_30fps.md`、`loading_order.md`、`README.md` | 写清流水/突发、持续帧调用、真实验证范围及历史串行包不可复用的限制。 |

## 已实际验证

- `fusion_pipeline_20261101/rtl03`：10个有效帧、655,360标量、9类非法配置；背压、读写错误、配置快照、RLAST和AXI排空回归通过。
- `tail01`：65,568标量、多个4 KiB边界与不足64拍帧尾通过。
- `full01`：2,747,520标量逐元素一致；1,383,169拍（99,999,001 Hz下13.831828 ms），251,688次读写同拍。
- `bandwidth03`：读源最多隔拍供数并加入事务/周期暂停；2,585,381拍（25.854068 ms），146,453次读写同拍，逐元素一致。
- `same_image01`：实际锁定CNN/D对同一原图生成的三路输出，与独立融合Golden逐元素一致。
- `package01`：128位、64拍、revision 3封装与IP integrity通过。
- `verify02`：独立重开实际OOC checkpoint并正常退出；融合单核LUT7,043、FF2,446、DSP24，OOC WNS +4.782 ns。不能用它替代联合时序。
- `controller_tests02`：32项主机测试通过，覆盖30帧/三槽/180次核启动、每帧依赖、跨帧重叠、输出消费与复用、异常、物理地址查找和计时口径。
- 新六核联合综合通过：LUT89,272，FF99,113，BRAM72.5 tiles，URAM58，DSP940。这是综合数字，最终以新包内routed报告为准。

保留失败记录：`rtl01`（早期语法）、`ooc01`/`verify01`（厂商进程退出异常）、`bandwidth02`（隔拍源误触连续两拍覆盖断言）。后续修复在新目录重跑，不把原失败收据改为成功。

## 联合实现与最终交付

构建目录：`D:/weather_builds/joint_pipeline01_20261101`。以其不可覆盖的阶段收据、`acceptance.json`、最终包`manifest.json`及独立ZIP核验结果记录实际结论。尚未完成的阶段不能借用旧`joint_system05_20261029`的资源和时序。旧`kv260_joint_delivery_20261101.zip`仍为串行revision 2。

新联合布局布线通过：LUT84,230/117,120（71.92%），FF94,687/234,240（40.42%），BRAM72.5/144 tiles（50.35%），URAM58/64（90.63%），DSP940/1,248（75.32%）。最终WNS +0.078 ns、WHS +0.010 ns、WPWS +1.700 ns；189,323/189,323可布线网络均已完成，routing errors=0。原始no_clock、constant_clock、multiple_clock和未约束内部端点均为0；未发现Critical CDC、DRC Error或Critical Warning。独立覆盖及17项bus-skew全部通过，最差slack +3.675 ns；同图Golden与精确源码/IP身份的最终验收通过，收据为`acceptance.json`。

资源打包仍较紧：CLB落点14,377/14,640（98.20%），URAM占90.63%；LUT总量尚有余量不等于可以直接增加任意新模块。setup余量为0.078 ns，任何IP、时钟或集成变化都须重新布局布线。原始Warning不压制，随报告交付。

新bit/XSA导出通过，位于上述构建的`export/`。交付目录为`D:/weather_builds/kv260_joint_pipeline_delivery_20261101/`，压缩包为同名`.zip`，旁置`.zip.sha256`。包内`SHA256SUMS`核对全部payload与manifest，包外`kv260_joint_pipeline_delivery_20261101_verified.json`记录独立重开ZIP后的最终核验结论；只有其pass为true才视为本包交付完成。旧串行包不覆盖。

## 未验证与审阅边界

未连接目标板，未执行板端fence编译、配置、数值核对、DDR实测或持续FPS测量；未做完整六核RTL仿真。既有模型拓扑、训练权重与冻结CNN/D/Bilinear/Curve/prepare IP未修改。融合仿真预算通过只证明明确内存模型下的融合阶段，不证明共享DDR/PS条件下整机30 FPS。

建议Commit Message：`fpga: pipeline and burst three-way fusion with continuous-frame runtime`

当前工作树保留未暂存的新模块目录；完成后只汇报可审阅结果，等待用户另行明确授权Git操作。
