# 通用 PYNQ Overlay 合同与结果校验 Skill

这是按竞赛 3.3.5.2 整理的 **提示词工作流＋校验脚本＋接口模板＋踩坑清单**。面向 PYNQ 的 Overlay 发现、内存型加速器或 AXI DMA stream 联调；板型、模型、图像尺寸和寄存器地址均不绑定本题。可先在普通电脑复用离线工具，再按自己的 `.bit/.hwh` 与驱动文档执行板端步骤。

**交付状态：Host 工具已测试，PYNQ 真板验证尚未在本包执行。** 能否获得通用 PYNQ 独立加分由评审决定；提交前应补目标 PYNQ 环境的实际使用记录。不能以 Host PASS 或历史 KV260 JTAG 结果代替。

## 适用范围与失效条件

| 范围 | 支持内容 | 不覆盖/失败时的处理 |
|---|---|---|
| 接口合同 | 独立输入/输出；整数 dtype、明确字节序、C 连续布局；32/64 位 pointer；有限超时 | 不适用于 in-place、隐式 stride、浮点容差；应另写合同/比较器 |
| MMIO master | 控制寄存器偏移/窗口自洽、pointer 字不重叠 | 不能假定所有 IP 有 AP_CTRL；缺真实寄存器语义先补资料 |
| AXI DMA stream | 一入一出、长度上限、起始地址对齐要求、TLAST 约定 | 本包不实现 DMA 驱动，不覆盖 SG/cyclic/VDMA；实际参数由 HWH/版本核实 |
| 数据验收 | 全字节 Golden、SHA256、两端 guard 文件、poison 与 Golden 不冲突、A/B 差异 | Golden 不可信、shape/layout 不一致、无法确定新完成、未知 DMA 在途均不得宣称板测 PASS |
| 证据 | Host 合同与文件检查结果、真板证据整理方法 | 无法从文件证明设备实际运行、cache 正确、guard 真正相邻或 FPS |

## 安装和最短使用

本目录本身即可交给其他队伍；若在 Codex 中使用，将完整目录复制到其技能目录，或明确指定本目录的 `SKILL.md`。工具只依赖 Python **3.9+ 标准库**，无需 PYNQ、NumPy 或联网。执行以下命令时当前目录为本 Skill 根目录：

```text
python -B scripts/validate.py check assets/mmio-master.example.json
python -B scripts/validate.py check assets/axi-dma.example.json
python -B scripts/validate.py demo <新的或空的本地目录>
python -B scripts/validate.py compare <演示目录>/contract.json <演示目录>/run.json --require-ab
python -B -m unittest discover -s tests -p test_validate.py
```

`demo` 生成 2 组很小的整数输入、独立 actual/Golden 文件及 guard 文件，再完整比较；其行为只是 Python 字节复制。demo 结果标记 `synthetic_demo=true`，所有命令结果均保留 `board_validated=false`。重复使用非空目录会失败，不覆盖原文件。

正式使用时复制并改写 `assets/` 中相应合同。`board-candidate` 只是用户声明的候选阶段，也不会改变检查器的 `board_validated=false`。字段定义和板端步骤见 [工作流](references/board-workflow.md)；可用实际 `ip_dict` 快照进一步检查名称/VLNV/窗口：

```text
python -B scripts/validate.py check contract.json --inventory inventory.json
```

CLI 成功返回 0，失败返回 1；参数用法错误由 argparse 返回 2。所有脚本均不包含连接板卡、下载 bitstream、MMIO、DMA 或自动 reset/retry 操作。

## 完整输出包格式

先通过 `demo` 得到可直接改用的 `contract.json` 和 `run.json`。`run.json` 的最小结构如下；路径相对于该 JSON 所在目录，不允许逃出目录。每个输出都必须提供实际文件、Golden 独立 SHA256、精确长度的两端 guard，以及一个 dtype scalar 大小的 poison。下例 SHA 字段须填真实值，不能直接拿去当验收记录。

```json
{
  "schema_version": 1,
  "frames": [
    {
      "id": "A",
      "inputs": {"input": "A_input.bin"},
      "outputs": {
        "output": {
          "actual": "A_actual.bin",
          "golden": "A_golden.bin",
          "golden_sha256": "替换为可信Golden的64位小写SHA256",
          "guard_before": "A_before.bin",
          "guard_after": "A_after.bin",
          "guard_byte": 90,
          "poison_hex": "a5a5a5a5"
        }
      }
    }
  ]
}
```

`--require-ab` 要求恰好两帧、不同 frame ID，至少一个完整输入不同，至少一个完整 Golden 输出不同，并校验全部声明输出。若算法对所选 A/B 的输出恰好相同，应另选有区分度的测试对，不能据此断言算法错误。不加该参数可检查单帧文件，但不能声称排除了复用旧输出。

guard 文件必须由真实运行后对同一设备 allocation 两端的保护区导出。单独生成两个正常文件只会测试比较器；脚本不可能证明其物理位置。poison 是否真正预填、cache 同步、fresh done 与各帧来源同样需要运行日志。

文件检查会按 `samefile` 识别物理文件身份：所有帧的 actual 和每一份 guard 必须是独立快照，不能复用同一路径或 hardlink，也不能与任何输入/Golden 文件别名。Golden 可共享可信的只读参考，两个不同输出即使预期内容相同，也必须分别采集 actual 与 guard。

## 提示词模板

> 使用本目录 `SKILL.md` 检查我的 PYNQ Overlay。板型与 PYNQ 版本为【实际值】，`.bit/.hwh` 为【文件与 SHA256】，目标 IP 为【名称/VLNV】。先根据 HWH 和接口说明区分 MMIO master 或 AXI DMA stream，生成合同并执行 Host 检查。已授权的硬件范围为【明确范围/本次仅离线】。对实际运行保存 A/B 输入、完整输出、Golden SHA、guard、cache 同步和新完成证据；把未验证项单列，不把 Host 数字当板测。

## 经验来源与验收记录

本包从工程中的全量 Golden、A/B 防旧数据、poison/guard、配置/控制/算法分层验收经验提炼，并针对 PYNQ 官方接口改写。[来源与踩坑映射](references/evidence-and-sources.md) 记录原问题、修正方法、官方 API 链接和适用边界；[验证记录](references/validation.md) 记录本次真正执行的 Host 测试及未执行的板端事项。

下一队伍可直接复制 Skill、运行 demo/测试并改写合同。真正板测还需要自己的板卡、PYNQ 环境、匹配 `.bit/.hwh`、可信 Golden 和接口说明；本包没有捆绑任何专有 bitstream、数据集或模型权重。
