---
name: pynq-overlay-validation
description: 为 PYNQ Zynq/Zynq UltraScale+ Overlay 制定并检查 IP、MMIO 或 AXI DMA、buffer 与完成信号合同，核对完整 Golden、guard 和不同输入 A/B 输出。用于 PYNQ 上板联调、错误定位及验收材料；随包工具只做离线检查，不自动下载 bitstream 或操作板卡。
---

# PYNQ Overlay 合同与结果校验

目标：把任意题目的 PYNQ 联调拆成可检查的接口合同和可追溯的结果。先读用户已有工程与运行限制；已有授权继续有效，不能因本 Skill 扩大硬件操作范围。

## 入口

1. 确认板型、PYNQ 版本、配对 `.bit/.hwh`、IP 名称/VLNV、当前 PL 是否允许运行/重载。读取 [板端工作流](references/board-workflow.md) 中对应模式。
2. 区分数据路径：AXI-Lite 只是控制/少量寄存器；`mmio-master` 表示加速器自己从 DDR 读写；`axi-stream-dma` 表示 AXI DMA 在 DDR 与 stream 间搬运。不能看到 IP 就假定存在 DMA、AP_CTRL 或固定偏移。
3. 以 [MMIO master 示例](assets/mmio-master.example.json) 或 [DMA 示例](assets/axi-dma.example.json) 建合同。示例是虚构 Host 数据，不是板卡配置。全部替换为本工程证据，填写 shape、整数 dtype/字节序、布局、字节数、对齐、cache 策略、完成信号与 timeout。
4. 在 Host 上先检查：

   ```text
   python scripts/validate.py check assets/mmio-master.example.json
   python scripts/validate.py check contract.json --inventory inventory.json
   ```

   可选 inventory 来自 PYNQ `ip_dict` 的标量快照；见参考文档。`HOST_CONTRACT_PASS` 只表示这些离线字段自洽，不能证明 bit/hwh 配对、实际地址可达、时钟/reset、驱动兼容或板测通过。

5. 在授权且合同完整的板端环境执行一次最小交易：分配设备 buffer → 初始化完整输入与输出 poison/guard → 正确同步 → 提交 → 等待本次新完成 → 同步读取 → 保存所有输出和证据。按接口文档构造启动/清 done 语义，不能把之前的 idle/done 当本次完成。标准 DMA `wait()` 不提供通用 timeout 参数；不要编造 `wait(timeout=...)`。异常/超时后保留未知在途 buffer，不自动 reset、重载或重试。
6. 用完整原码而非截图/抽样验收：

   ```text
   python scripts/validate.py compare contract.json run.json --require-ab
   python -B -m unittest discover -s tests -p test_validate.py
   ```

   `run.json` 格式见 [README](README.md)。A/B 输入及 Golden 至少各有一项不同，所有声明输出都完整校验；可识别漏写、旧输出与保护区破坏。文件 PASS 仍不证明文件来自新板测，需独立附上交易记录与运行身份。

## 交付

输出合同、检查结果、完整输出校验摘要及失败定位；明确列出 Host/PYNQ 真板/性能测试各自已做和未做事项。报告引用 [来源与经验提炼](references/evidence-and-sources.md)，不能把 KV260 JTAG 历史实证改称 PYNQ 实测。性能只使用连续计时窗内的真实输出，不能拼接各 IP 延迟冒称 FPS。

本包支持单一加速器的有限大小整数 buffer、C 连续布局、精确字节 Golden。复杂多 IP 调度、SG/cyclic DMA、VDMA、浮点容差、相机和 XRT 应用需另建合同，不扩展本脚本为万能驱动。
