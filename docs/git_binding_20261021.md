# Git 绑定记录

日期：2026-10-21。用户明确要求将当前文件夹绑定到远端 `weather_fpga_integration` 分支；本轮授权范围为建立本地仓库与跟踪关系，没有暂存、提交或推送。

## 绑定结果

- 目录：`C:/Users/wzh16/Desktop/github clone/weather_fpga_integration`
- origin：`https://github.com/mikosakurakaze-creator/FPGA-repo.git`
- 当前分支：`weather_fpga_integration`
- 上游：`origin/weather_fpga_integration`
- 基线提交：`b4aa1834fd74b483761a5ccdb1224b65c497366f`
- 本地 HEAD 与上游一致，天气代码和文档仍是未提交的修改/新增文件。

远端分支已经存在，没有创建或更新远端分支。只获取该分支；设置本地 `push.default=simple` 和该分支的 `pushRemote=origin`，使后续普通 push 对应同名上游。没有修改其他克隆或成员分支。

## 文件保留与修改

先建立以远端提交为基线的索引，再只恢复本地缺少的 112 个远端文件。与现有天气文件重合的 `.gitignore`、`README.md`、`deployment/README.md` 在恢复时逐文件核对哈希，没有覆盖。原工作内容保留为正常未提交修改。

随后仅整理以下忽略规则和状态说明：

| 文件 | 原因与关键差异 |
|---|---|
| `.gitignore` | 保留远端原有数据、模型、虚拟环境与工具产物规则，追加天气工作目录的 `work/`、`build/`、`data/`、`outputs/` 规则 |
| `README.md` | 将当前复制目录的状态更新为已绑定同名分支，链接本记录 |
| `docs/open_items.md`、`docs/stream_revision_20261020.md` | 区分原独立工作目录、复制时状态和之后的 Git 绑定 |
| 本文 | 记录绑定范围、实际核验和后续提交边界 |

`work/` 内已有 bit/XSA、Vivado 工程、原始 HLS/RTL 输出；普通暂存不会包含这些被忽略的本地文件。基线已经跟踪的文件不会被 `.gitignore` 取消跟踪。

## 验证与未执行项

核验本地分支、origin URL、上游及 HEAD 身份；索引与 HEAD 一致，无已暂存天气改动；远端基线无误删除。检查本地大目录和 bit/XSA 的忽略规则。绑定恢复时三个重合文件哈希均保持，记录在 `.git/binding_verification.json`。

本轮没有修改计算核或运行新的 HLS/RTL/Vivado 流程，也没有连接真板。计算与硬件通过证据仍见 [流水版报告](stream_revision_20261020.md)；PS ELF、板测及持续帧率仍待完成。

建议将天气实现和文档经审核后使用 Commit Message：`feat: pipeline weather frames and verify K26 system implementation`。本轮未执行 `git add`、`git commit` 或 `git push`。
