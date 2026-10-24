# D：选定的极简图片增强模型

状态：2026-10-25 用户确认选用；FP32 软件试训权重已固定。**尚未量化或部署 FPGA。**

队友从 [D 模型交接与分工](../../doc/2.1.0_D模型交接与分工.md) 开始阅读。

## 文件入口

- `model.py`：独立结构、严格权重校验和逐节点 FP32 trace，不依赖本机实验目录。
- `weights/d_best_fp32.pth`：选定的原始检查点，1200步训练中的第600步，未经重新训练或改写。
- `predict.py`：单张图片 FP32 软件推理。
- `export_reference.py`：导出 FP32 权重、22节点语义图与两组小图参考。
- `reference_fp32/`：已实际生成的导出，不是整数 Golden。
- `training_report.json`、`split_manifest.json`：训练记录和图片文件名/SHA划分，不包含图片或本机路径。
- `provenance.json`：模型来源、配置、哈希和验证边界。

```bash
python -m pip install -r models/compact_d/requirements.txt
python models/compact_d/predict.py --input photo.jpg --output result.png --device cpu
python models/compact_d/export_reference.py --out d_reference_new
```

验证环境：PyTorch 2.7.1+cu126。requirements是最低依赖说明，不是已在所有版本验证的锁定环境。

## 冻结的结构

输入 `[1,3,H,W]`，RGB，FP32，范围 `[-1,1]`。所有卷积 stride=1、padding=1、
3×3、groups=1、零填充并带 bias，空间尺寸不变。

```text
RGB_u8 / 255 -> *2 - 1 = x
y = ReLU(Conv3x3(3->8)(x))
重复3次：y = ReLU(y + Conv3x3(8->8)(ReLU(Conv3x3(8->8)(y))))
correction = Conv3x3(8->3)(y)
output = ReLU((x+1)*0.5 + correction)
```

8层卷积，3947参数，720p卷积估算3.5831808 GMAC。
网络末端只有下界ReLU；显示时才 clamp 到 `[0,1]` 并用 `np.rint(y*255)` 转 RGB8。
不要提前将中间特征裁到 `[0,1]`，不要漏掉输入旁路。

CPU/GPU FP32 内核可能有微小数值差异；正式验收应由 A 定义整数语义及整数 Golden。
D 的结构和参数不能直接替换旧 Grid 的320节点ROM、bundle或scratch布局。

## 能力与限制

D 是模仿 GridDehazeNet outdoor 的去雾/增强学生模型，不是已经验收的独立除雨模型。
训练使用144张图片，验证12张、保留12张，教师目标不是清晰配对真值。
保留集相对教师的 MAE 为0.049989、PSNR为24.52146dB；这不是对清晰真值的画质指标。
具体训练配置及数据边界见交接文档。

不包含用户数据集、80MB效果图库、训练缓存、旧模型、bit/XSA或硬件驱动。
