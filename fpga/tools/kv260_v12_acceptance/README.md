# KV260 V1.2 验收离线准备

`prepare_repeat_plan.py` 默认读取仓库公开的 `fpga/bringup/kv260_v12/single_frame_plan.json`、`manifest.json`，复用公开 payload 校验工具，验证九个输入/golden 的 SHA、长度、guard、30 个无重叠 region、27 个准确参数及操作预算。生成的两帧审批计划包含每帧所有region的payload身份、第二帧poison SHA、54参数和6start明细。没有 UART、JTAG、MMIO、Cache 或 IP 操作入口。

```text
python fpga/tools/kv260_v12_acceptance/prepare_repeat_plan.py --data-root <九份资产所在目录> --output <新的外部证据目录>/repeat_2frame_plan.json
```

六份小资产可由仓库hex还原；三份完整大资产按 [共享说明](../../bringup/kv260_v12/README.md) 单独获取，不必拿本机私有JSON。`--single-frame-plan` 可显式传历史冻结 plan；路径字段不参与语义身份，数据仍从 `--data-root` 和公开hex读取。工具锁定实际成功范围的规范SHA，范围或参数变化时拒绝生成，先独立审核新计划。输出文件不得覆盖，审批计划仍为 `NOT_AUTHORIZED_NOT_EXECUTED`。本目录 `repeat_2frame_plan.json` 是实际校验后冻结的审批候选，不是板测结果。

```text
python -m unittest discover -s fpga/tools/kv260_v12_acceptance -p test_prepare_repeat_plan.py
```

离线测试检查公开计划与历史成功语义一致，正确候选预算通过，模拟超额第三帧、额外start、删参数和输入范围篡改均拒绝。这些是计划审核测试，不代表未来执行器已经实现运行时预算保护。

此工具不提供板端多帧 runner。真实执行前必须新建带帧号标签、全局 starts/写入预算和一次锁的有界适配器，复用已验证 transport/Host 门禁，完成 mock/独立审核，绑定用户明确授权。不能把已消耗预算的 `execute_once.py` 重跑或套循环。范围和性能方法见 [验收方案](../../docs/kv260_v12_acceptance_plan.md)。
