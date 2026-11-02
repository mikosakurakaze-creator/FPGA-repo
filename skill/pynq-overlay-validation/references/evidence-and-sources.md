# 来源、失败经验与可复用边界

## 从工程经验到通用方法

以下路径是原仓库中的提炼来源，不是运行本 Skill 的依赖；单独复制本包仍可运行工具。原工程记录属于其记载的历史版本与平台，不代表本包已在 PYNQ 执行，也不覆盖团队其他分支后续结果。

| 原工程材料 | 原问题或限制 | 提炼的规则 | 本包验证方式 |
|---|---|---|---|
| `fpga/bringup/kv260_v12/single_frame_evidence.json`、`s1_two_frame_evidence.json` | 单次 idle/done、同输入重复或旧输出不足以证明新计算；历史 KV260 JTAG 数据不能当 PYNQ 测试 | A/B 使用不同输入和区分性 Golden；全部输出原码与两端 guards 校验 | Host demo 正例；旧 word、截断、尾字节、guard 破坏、相同 A/B 反例 |
| `fpga/tools/kv260_v12_linux_perf/native_hotpath/README.md` | 抽样或只填部分 poison 可能漏掉局部漏写；poison 恰好等于 Golden 会失去检测能力 | 标量 poison 先核 Golden 不包含；校验所有字节，锁 Golden SHA | poison 碰撞、错误 SHA、首尾损坏反例 |
| `fpga/ai_collaboration/case_studies/ps_pl_bringup.md` | 配置完成不代表时钟/reset、控制口或算法运行完成；失效的观察链会误导诊断 | 元数据、PL 状态、控制访问、fresh completion、数值验收分别留证 | 工作流分层；工具不输出 BOARD PASS |
| `fpga/tools/kv260_v12_linux_perf/README.md`、`fpga/docs/kv260_v12_linux_backend_review.md` | Host mock 和 JTAG 计时无法证明持续吞吐；未实现的资源层不能宣称真实 DMA/cache 正确 | Host 与板端证据分开；未知 DMA 在途保留 allocation；计时包含真实连续区间 | 输出固定 `board_validated=false`；README 列明未覆盖能力 |

本包是这些经验面向 PYNQ 的新提炼：不复制 KV260 PMU/GPIO95 写值、固定物理地址或私有聊天记录，不捆绑原模型和大数据。失败模式有工程来源，PYNQ 适配正确性仍需目标环境实测。

## 已实际打开核验的 PYNQ 官方资料

核验日期：2026-11-01。`latest` 是滚动文档；提交者还应核安装版本及对应源码。以下为摘要，不是官方内容的完整复制。

| 官方来源 | 核验事项 | 对本包的影响 |
|---|---|---|
| [Overlay 教程，v2.7.0](https://pynq.readthedocs.io/en/v2.7.0/pynq_libraries/overlay.html) | 默认下载；`download=False`；HWH 元数据与 IP 字典 | 明确发现与下载分开，记录版本 |
| [Overlay API](https://pynq.readthedocs.io/en/latest/pynq_package/pynq.overlay.html) | `ip_dict` 字段；下载关联的配置行为；DefaultIP 接口 | 名称/VLNV/窗口快照；不把元数据当实际状态 |
| [allocate](https://pynq.readthedocs.io/en/latest/pynq_libraries/allocate.html) | 分配设备 buffer、`device_address`、两方向 sync/flush/invalidate | 不用普通虚拟地址；写入与读取分别同步 |
| [MMIO API](https://pynq.readthedocs.io/en/latest/pynq_package/pynq.mmio.html) | MMIO 的 base/range 与相对 offset | 合同检查寄存器窗口，不固化基地址 |
| [DMA 教程](https://pynq.readthedocs.io/en/latest/pynq_libraries/dma.html) | stream 与内存搬运、TLAST、示例 transfer/wait | 把 DMA 模式与加速器自己访存分开 |
| [DMA API](https://pynq.readthedocs.io/en/latest/pynq_package/pynq.lib/pynq.lib.dma.html) | send/recv channel 方向及设备 buffer 要求 | 明确一入一出 profile 的边界 |
| [DMA 官方发布源码页](https://pynq.readthedocs.io/en/latest/_modules/pynq/lib/dma.html) | simple channel 的 `wait()` 没有 timeout 参数，接收完成维护 cache；channel 构造可能启动硬件；长度/对齐按配置检查 | 不生成虚构 timeout 调用，不为元数据发现批量实例化驱动；参数取实际版本 |

教程的模式描述与滚动源码支持面可能有差异，尤其 SG；本包只覆盖简单一入一出合同，不据一页教程推断所有版本能力。

## 如何补 PYNQ 真板证据

用自己的简单 copy/算子 Overlay 即可，不依赖本题模型。附上板型、PYNQ 版本、同次构建 bit/hwh/接口说明的 SHA、合同和快照；在相同 buffer 槽执行有区分度的 A/B，保存两个输入、完整输出、独立 Golden、实际 guard dump 与原始运行记录；运行离线比较并独立核新完成/cache/地址归属。再换另一个接口配置或题目复用合同，说明改动项与无需改动项。

如尚未完成这些，提交材料应保持“通用 PYNQ 联调流程与 Host 校验工具；板端待验证”的准确表述。不得将示例字节复制输出、文档中的预期结果或旧 JTAG 数据作为新的 PYNQ 运行证据。
