# KV260 联合硬件包：流水 Prepare + 三路融合

本包由新六核综合、布局布线、时序/CDC/DRC/覆盖验收和同图 Golden 通过后生成。融合 revision 3 使用 128-bit、最长 64 拍突发、三输入/一输出 FIFO、八路五级计算流水及独立读写引擎。

Prepare 使用 128-bit 连续突发、片上分块重排和五任务 DATAFLOW；从一次 RGB 读取中生成原图、D 输入及 CNN 小图。数值合同与软件寄存器偏移不变，详见 `docs/prepare_pipeline.md`。`evidence/prepare_pipeline_acceptance.json` 绑定完整图数值、RTL、综合和实际 128-bit 集成通路证据。

- `joint_system.bit` + 同名 `joint_system.hwh`：PYNQ overlay 输入。
- `joint_system.bit.bin`：Bootgen 2025.2 转换结果，已独立核对 BIT 配置数据字节序。
- `joint_system.xsa`：同次硬件平台；BIT/HWH 与 XSA 中规范产物对应。
- `register_map.md/csv/json`、`address_map.json`：实际 HWH 提取的六核寄存器和地址表。
- `clock_reset.md`、`docs/loading_order.md`：时钟复位、加载调用顺序及异常恢复。
- `runtime/run_pipeline_pynq.py`：三槽连续帧调用入口，记录批次FPS、输出间隔及逐帧哈希；本轮未在板端执行。
- `evidence/fusion_pipeline_acceptance.json`：精确源码/IP 身份、全帧数值与吞吐仿真证据；`reports/` 为本次实现报告。
- `SHA256SUMS` 包含 manifest 和所有 payload 的 SHA256；ZIP 的 SHA256 位于旁边 `.zip.sha256` 文件。

30 FPS 为目标。融合在明确的内存模型下已检查每帧不超过 33.333 ms；这不是整个系统或真板 30 FPS 的实测结论。单帧参考调度仍有 prepare→模型路径→fusion 的完成依赖；持续帧率还取决于其他核、帧间调度、PS 和共享 DDR。上板前先校验哈希，按加载文档确认 LOW DDR/64-byte 对齐及 DMA/cache 所有权，运行后核对 Golden 与真实持续 FPS。

本包采用 2026-11-02 接受的六 FIFO 定向改进版；原约束 setup 0.391 ns、hold 0.100 ns。导出阶段没有重新综合、布局或优化。完整来源、实际 RTL 输入和 132 份 SmartConnect wrapper 分别见 evidence/timing_lineage.json、source/implemented_inputs/ 和 source/generated_smartconnect/。reference_ip/ 是算法版本来源的历史原包，不能代替已修改的实现输入；ip/ 中的 Prepare、融合包继续与实现一致。历史审核失败记录保留，最终独立审核为 evidence/timing_margin_audit.json。
