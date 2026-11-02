# PYNQ 板端工作流与合同解释

本文件供 Skill 在需要真实 PYNQ 适配时读取。下面是依工程填写的步骤，不是统一可直接执行的板卡驱动。先确认用户的运行范围与现有授权，普通离线检查不需要板卡。

## 1. Overlay 与 IP 发现

记录板型、PYNQ/Python 版本、bit/hwh SHA256 和来自同次构建的依据。Zynq 类 Overlay 通常使用同目录同基名 `.bit/.hwh`。配对名称和各自哈希不等于证明来自同一构建，仍需构建 manifest。PYNQ 默认 `Overlay(path)` 会下载，下载还可能应用 PS/PL 配置；仅做元数据检查时使用 `download=False`。该构造仍要求合适的 PYNQ device/runtime，不能在普通 Host 上当成纯 HWH 解析器。

在合适的 PYNQ 环境，仅导出元数据标量，不要为发现 IP 而实例化全部驱动：

```python
# 供目标 PYNQ 环境人工采用；本包 Host 测试未执行这段代码。
import json
from pathlib import Path
from pynq import Overlay

metadata = Overlay("/absolute/path/design.bit", download=False)
snapshot = {"ip_dict": {
    name: {"type": info.get("type"),
           "addr_range": info.get("addr_range"),
           "phys_addr": info.get("phys_addr")}
    for name, info in metadata.ip_dict.items()
}}
Path("inventory.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
```

检查器只核名称、VLNV、窗口；不把快照视为当前 PL 内容或硬件连接证明。`metadata.ip_dict` 与 `getattr(metadata, ip_name)` 不等价：后者可能实例化 driver，某些 DMA driver 的构造就会启动 channel。`register_map` 的字符串显示也不应被一律当作无副作用元数据读取。

`ip_dict` 只覆盖 PS 可寻址 IP。没有 AXI-Lite 的纯 stream 算子应声明 `ip.addressable=false`、`addr_range=0` 和 `control.kind=free-running`，其名称/VLNV 从 BD/RTL/构建材料确认；DMA 仍须从快照发现。这种情形工具会明确给出 `accelerator_inventory_checked=false`，不把算子缺席误报成丢失 IP。寄存器可寻址 IP 默认 `addressable=true`。

## 2. 选择数据路径

| 合同 `transport.kind` | 必须从设计确认 | 控制约定 |
|---|---|---|
| `mmio-master` | 加速器 AXI master 能访问 allocated buffer；地址宽度；每个输入/输出指针的低/高 word 偏移 | 本包仅收寄存器启动模型；填写真实 start/done offset、mask、清除/握手语义 |
| `axi-stream-dma` | 确有 AXI DMA、所需 send/recv channel 启用；memory-map 数据宽度、DRE、长度上限、stream TLAST/有效字节规则 | stream 算法可 free-running 或寄存器启动；必须记录 DMA 与算法两侧何时算完成 |

AXI-Lite 控制与 DMA 是两回事；不要给只有 m_axi 的 HLS IP 强塞 DMA，也不要给纯 stream IP 写虚构 DDR 指针。脚本中的 DMA profile 只支持一个输入和一个输出，`max_transfer_bytes` 要填实际 driver/HWH 限额，不使用统一的“16 KB”常数。`address_alignment_bytes` 填真实起始地址要求；实际设备地址及可达区间不由 Host 合同检查器证明。

## 3. Buffer 与 cache

合同每个 buffer 写 `name/role/shape/dtype/layout/nbytes/alignment_bytes/guard_bytes/cache_policy`。dtype 仅支持 `u1/i1` 和显式大小端的 2/4/8 字节整数，例如 `<i2`；layout 仅支持 C 连续。NHWC/NCHW/通道顺序等语义写进工程说明，脚本不能从 bytes 推断。固定点还须记录 scale、零点、饱和/回绕与舍入；精确 Golden 必须采用同一协议。

板端通过 `pynq.allocate(shape=..., dtype=...)` 获得设备 buffer，使用其 `device_address`；普通 NumPy 地址、`id()`、CPU 虚拟地址都不是可写入硬件的 DMA 地址。一个可行的 guarded allocation 方案是分配更大的 `u1` buffer，在 payload 前后保留已对齐的 guard，仅把 payload 的 view/设备地址交给消费方；核实际 view 的连续性、offset、dtype 和地址，不能把含 guard 的整段交给 DMA。

guard 与 payload 的边界还应按平台 cache-line/维护粒度对齐，避免共享 cache line 引入干扰；合同 `alignment_bytes` 必须覆盖相应要求，不能假定所有平台都是 64B。input 和 output 的归属及分配生命周期覆盖全部在途操作。

`explicit-sync`：CPU 填输入、输出 poison 和 guards 后，按有效范围同步给设备；设备完成后同步 output 与需要检查的 guards 回 CPU，再读比较。PYNQ buffer 的 `sync_to_device()`/`flush()` 与 `sync_from_device()`/`invalidate()` 分别对应这两个方向。`verified-coherent` 只在实际 buffer/device/通路证据充分时使用；名称或 DT 属性本身不能证明一致性。官方 DMA driver 可能自动执行部分维护，按已安装版本核实，不能遗漏输出预填/guards，也不能在 DMA 正写时触碰其 cache ownership。

## 4. 启动、完成与超时

寄存器布局来自本次生成的驱动头/HWH/IP 文档；AXI-Lite 常见 32 位访问不代表所有 pointer 只有 32 位，也不代表 AP_CTRL 必定在 0。64 位 pointer 写两 word，并核高位和该 device 的地址可达性。

根据实际协议处理旧 done、启动顺序与完成确认，记录这次 invocation 的 start/completion，避免将 clear-on-read done 交给多个 reader。DMA pipeline 的接收侧通常要先准备好再让上游发数据，但启动顺序取决于 backpressure、buffer 深度与算法握手；按工程推导，不能套统一三行脚本。TLAST 与有效字节数以 stream 协议为准。

使用有限 deadline 的轮询/异步监督，并记录错误位。官方同步 DMA `wait()` 没有通用 timeout 参数；异步等待也不意味着取消硬件。Python deadline 只能限制正常返回的调用间等待，无法中断一次挂住的 MMIO/底层访问。失败时停止提交新任务，保留 buffer 与原始证据，明确 DMA 是否仍在途；未知状态下不要释放、覆盖、重用或自动重载 PL。恢复动作依据实际硬件生命周期和当前授权另外确定。

## 5. 全量验证与结果归因

先从可信软件参考生成完整 Golden 并锁 SHA。选择一个 dtype scalar poison，确认它不在这些 Golden 中，再填满 output；两端 guard 用已知 byte 初始化。完成后导出全部 output、guard 和实际输入，建立 README 中的 `run.json`，执行 `compare --require-ab`。A/B 使用同一物理槽时更容易暴露漏写；第二帧必须完整初始化并重新执行硬件。

最终记录至少包括 bit/hwh/driver/runtime 身份、input/Golden SHA、布局/长度、有效设备地址范围、sync 与 start/new completion、错误位、所有输出比较数和 guards。保存连续计时窗的起止与帧数，copy/等待/校验是否包含应写清。文件比较的结果始终是 `HOST_FILES_PASS`；只有独立审核上述真实板端证据，才可在外部验收记录声明 PYNQ BOARD PASS。
