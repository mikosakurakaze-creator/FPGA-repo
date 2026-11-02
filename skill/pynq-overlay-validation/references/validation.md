# 实际验证记录

日期：2026-11-01（Asia/Shanghai）。本文件区分已经执行的 Host 检查与尚未执行的 PYNQ 板端验证。

## 已执行

环境：Windows，Python 3.12.10；本包脚本只使用标准库，未导入/安装 PYNQ 或 NumPy。使用 `-B` 避免生成缓存；测试数据均在系统临时目录创建和清理。

```text
python -B -m unittest discover -s tests -p test_validate.py -v
```

**修复后 14 项行为测试全部通过**，覆盖：

- MMIO master 与 AXI DMA 两种合同，真实结构的元数据快照；区分可寻址 IP 与不出现在 `ip_dict` 的纯 stream 算子。
- shape/dtype/字节长度/连续布局、对齐/guard/cache 策略；32/64 位指针完整性、寄存器越界与地址字别名。
- 有限正 timeout；DMA 长度上限与对齐约束。
- 完整 A/B synthetic 正例；旧 word、截断、最后字节损坏、前后 guard 破坏。
- 错误 Golden SHA、poison 与 Golden 冲突、相同 A/B 输入/预期输出。
- actual 与 Golden 同一文件、目录逃逸、缺失输出、非空 demo 目录拒绝覆盖。
- 全包 actual/guard 与其他 actual/guard/输入/Golden 的物理文件身份去重；重复路径与 hardlink 拒绝。不同输出预期内容相同时，独立 actual/guard 快照仍可正常通过。

另用临时目录执行 **7 个 CLI 冒烟调用**：两个示例合同 check、demo、A/B compare 均成功；损坏 JSON、未知 transport、demo 输出路径已经是文件均返回退出码 1 和简短 JSON，未显示 traceback、未覆盖原文件。调整纯 stream IP 发现语义后再次执行全部初始 12 项测试以及 DMA 示例 CLI，仍全部通过。

## 独立评审暴露的问题与修复

初版 12 项测试通过后，独立检查发现两个可复现的错误通过：将 after guard 的路径误指向正常 before guard，或将第二个输出的 actual 误指向内容恰好相同的第一个输出。初版只做每项 actual/Golden 不同文件检查，未检查整包采集快照的别名；因此可能漏查真实坏 guard 或未写入的第二输出。旧失败工件和回执保留在独立评审的临时档案中，没有覆盖。

修复后按 `samefile` 在整包范围识别重复路径和 hardlink：所有 actual/guards 必须独立，也不能冒用输入/Golden。只读 Golden 可复用；内容相同的两份真实独立输出仍通过。已添加这两类错误的路径/hardlink 负例及独立双输出正例，再次执行 **14 项测试全部通过**。这也只加强文件清单完整性，不证明实际采集或硬件计算来源。

独立评审使用原先未修改的失败数据和清单重新验证：guard 别名和多输出 actual 别名均从误通过转为退出码 1；原合法的大端有符号16位、二维 shape、64位指针配置仍通过；新建同内容但物理独立的双输出快照也通过。失败工件与修复后回执分别保留，没有覆盖历史失败。

主任务另将整个 `skill/` 复制到仓库外新目录，从复制目录执行两合同 check、demo 和独立 compare，四次均通过，且所有结果保持 `board_validated=false`。检查两项技能的22个本地文档链接，均可解析。该检查确认所给 Host 示例不依赖原工程绝对路径。

PYNQ 官方 Overlay、allocate、MMIO、DMA 教程/API 与 DMA 源码页已在本次实际打开核验，链接及影响见 [来源说明](evidence-and-sources.md)。这些核验支持工作流中的 API 用法，不等于本机/板端实际运行。

## 结构检查

本包提供含 `name/description` YAML frontmatter 的 `SKILL.md`、竞赛要求的 README、必要引用、两个 JSON 合同模板、标准库脚本和 Host 测试。主任务已使用未修改的官方 `skill-creator/quick_validate.py` 检查通过（`Skill is valid!`）。系统默认 Python 缺少 PyYAML，因此校验时使用系统临时目录中的隔离 PyYAML 6.0.3，未改变全局环境。本包运行不需要 PyYAML。

## 未执行与结论边界

- 未连接板卡、加载/下载 Overlay、访问 MMIO、启动 DMA/IP、改 clock/reset/cache、运行 HLS/Vivado。
- 未执行 PYNQ runtime 中的元数据导出代码、buffer 分配/同步、fresh completion、TLAST/实际 DMA 设备地址验证。
- 未重新核验原工程历史板端原始交易，也不将其记录转为本包 PYNQ PASS。
- 未测试真实 A/B 硬件输出、持续帧率、相机链或第二板型。
- 未执行 Git add/commit/push 或其他分支操作。

因此当前准确结论为 **Host 合同/文件校验工具可运行，PYNQ 板端工作流和模板待目标环境实测**。所有机器输出保留 `board_validated=false`。复制 Golden 的 Host demo 只验证工具链，不能当模型计算或设备计算。

## 2026-11-02 发布目录复核

按竞赛目录结构放入根目录 `skill/pynq-overlay-validation/`，原 `VALIDATION.md` 移到 `references/validation.md` 并更新链接。脚本、测试和两种合同模板与上一轮审核版逐字节一致，没有改变算法或检查行为。

独立代理将完整技能复制到系统临时目录，重新运行14项行为测试、两种合同检查、demo和A/B比较，全部通过；9个包内相对链接有效，辅助文件名为小写英文，未产生入包缓存或私有输出。原版 Skill 结构校验通过。没有执行新的PYNQ板测或硬件操作。
