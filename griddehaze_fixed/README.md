# GridDehazeNet A 组整数参考交付

本轮 A 为当前用户/Codex，B 负责人为 **wzh**；lzm 提供原分工与软件侧背景。此交付是可重放的候选数值版本，B 的寄存器/DMA/scratch 合同和视觉效果仍须确认。旧系统 34 FPS 不属于本版本验证结果。

- [技术计划](docs/PLAN.md)：目标来源、设计选择、验证依赖。
- [B 组接口合同](docs/INTERFACE.md)：逐算子整数语义、布局、尺度、缓存与待确认事项。
- [实际审计报告](docs/AUDIT.md)：结果、证据、失败探索与交接限制。

## 模型及数值版本

官方源码固定 `481399129614c3e7c8e892b5d52d60173131dda0`；outdoor 权重 SHA256 `80a8f3aad5fd0ed744f39bd60bda802087fbb48b2fa2ce86261ac443a4dba396`，958051 参数。严格去除官方 DataParallel `module.` 命名空间后加载，不修改网络或权重。

交付候选采用 INT16 激活、逐节点二进制尺度、逐输出通道 INT16 权重、Q14 learned coefficient、INT64 bias/累加。所有尺度都在 graph/manifest，禁止用全图默认 F 解释中间值。逐通道累加保守界来自实际量化权重，不假设 INT32 安全。RHAZ（半数远离零）、饱和及尺度对齐边界见接口合同。

同版 INT8 权重作为资源权衡候选，单独提供，不能与 INT16 参数/Golden 混用。INT16 在 15 个验证裁剪上的 FP32 误差较低，但硬件资源及显示效果尚未验收。

## 环境

从仓库根目录执行。实际环境是 Windows x64、Python 3.12、CPU PyTorch 2.8.0+cpu、NumPy 2.2.6、SciPy 1.15.3、Pillow 11.3.0，无需 torchvision、HLS 或 Vivado。实际完整锁定依赖见 `requirements-lock.txt`，原始 pip freeze 也保存在命令记录。

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r griddehaze_fixed/requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

官方源树未提供明确许可证，仅有论文引用要求；原始源码、权重保存在忽略的本地输出目录，未自动上传。分发范围须由项目负责人确认，不能自行标注 MIT/BSD。本文不授予上游授权。

## 完整复现

发布包中的冻结尺度位于 `package/scale_config.json`；工作区为 `outputs/griddehaze/run_003/w16cal/scale_config.json`。冻结尺度、代码字节和原始权重共同决定版本身份。修改任一数值代码/配置必须重导出并生成新 Golden；校准本身的 FP32 范围可能受平台影响，新校准属于新版本。

```powershell
# 以冻结配置重新下载官方文件、导出两种权重、生成并比较 Golden。
./griddehaze_fixed/reproduce.ps1 -Python .venv/Scripts/python -Scales package/scale_config.json -Out outputs/replay01

# 从主人提供的原始 ZIP 重新划分、校准，并生成大尺寸 Golden。
./griddehaze_fixed/reproduce.ps1 -Python .venv/Scripts/python -FogZip C:/path/Fog.zip -RainZip C:/path/Rain.zip -Out outputs/replay02 -FullSize
```

复现会拒绝覆盖已有目录；每条子命令保存实际参数、UTC 起止时间、退出状态和原始输出。`archive.zip` 是摄像头/热成像数据，不是模型交接包，本轮仅保留身份及清单，未解压使用。Fog/Rain XML/TXT 是检测标注，不是去雾清晰真值。

完整命令也可分步执行：

```powershell
python -m griddehaze_fixed.fetch outputs/source
python -m griddehaze_fixed.export outputs/source outputs/new_package --weight-bits 16 --scales package/scale_config.json
python -m griddehaze_fixed.check_export outputs/source outputs/new_package --report outputs/parameter_check.json
python -m griddehaze_fixed.cli run --package package --source outputs/source --image golden/random/input.png --out outputs/replay_random
python -m griddehaze_fixed.cli compare golden/random outputs/replay_random --report outputs/replay_compare.json
python -m griddehaze_fixed.verify_delivery .
```

## B 组最小集成顺序

1. 校验 DELIVERY、package manifest 和 bundle ID，确认输入 NCHW RGB、signed INT16、`[-1,1]` 归一化；不得沿用旧 task=1 或 `[0,1]` 输入。
2. 普通卷积、反卷积、系数、加法、拼接逐项对齐，尤其负数、舍入、各节点 F 和奇数目标尺寸。小尺寸 Golden 保存全部 320 节点原始文件，`report.json.nodes` 是执行顺序。
3. 用完整图片及 720p 向量检查全图和边界，再共同冻结 DDR、DMA、寄存器及错误/超时语义。
4. 最终 FPGA dump 必须零差异。工具只比较文件，不证明数据来自板卡：

```powershell
python -m griddehaze_fixed.compare_fpga --golden-dir golden/random --actual-output FPGA_output.raw --actual-nodes FPGA_nodes --package package --bundle-id 5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710 --report outputs/fpga_compare.json
```

小向量 `FPGA_nodes` 使用 Golden 相同文件名，无需 B 生成 Python 运行报告。只核对最终输出可省略 `--actual-nodes`；仅核对部分节点必须显式 `--allow-partial-nodes`，工具会标明范围。完整大图保存全部节点 SHA/统计及原始最终输出；大图中间原始张量可通过增加 observer 按需转储，不能宣称已保存全部大图中间原始文件。

## 本机结果目录

- `outputs/griddehaze/run_003/`：最终候选导出、逐节点 Golden、双后端及确定性结果。
- `outputs/griddehaze/validation15/`：15 张真实验证图的中心 64×64 裁剪，非全分辨率质量基准。
- `outputs/griddehaze/final_foggy001/`、`final_720p/`：实际原尺寸整数推理及官方 FP32 最终对比。
- `outputs/griddehaze/commands/`：包括失败探索与修复后新运行的命令和日志。
- `outputs/griddehaze/userdata/splits.json`：原图身份、划分与重复情况；435 张保留集未执行，不宣称场景独立。

原 `run_001` 的统一 Q10/Q12 因大量饱和被放弃；`run_002` 是未加入合成边界校准的探索版。它们保留在本机，不能与最终包互换。所有上板、RTL/HLS、资源、时序、驱动和性能工作均未执行。
