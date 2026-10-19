# 去雨、去雾轻量模型实验

独立软件目录，保留原项目、Zero-DCE++ 与硬件实现，本次发布仅新增此目录。当前提供公开素材、训练评测、轻量模型与整数参考，尚未验收 FPGA 部署；低照度仍由原项目承担，三任务自动策略尚未集成。

## 配对去雨实测

RainTrainL 200 对按 seed42 分为 180 训练 / 20 验证；Rain100L 原始 100 对测试。源 ID 和解码输入/目标像素哈希检查无精确跨集重复，不代表排除所有近重复。素材来自 ANRN 研究者整理包，已记录本地 SHA，未独立证明与原发布包逐字节一致。

两模型均 3000 步、MSE、batch8、crop96，按全图验证 MSE 选择权重。RGB [0,1]、输出 clip、全图无裁边、逐图 PSNR/SSIM 后平均。

| Rain100L 全部100图 | PSNR/dB | SSIM |
|---|---:|---:|
| 输入 | 25.5213 | 0.81396 |
| C8 FP32 | 29.5230 | 0.88971 |
| C8 INT8权重/INT16节点 | 29.5346 | 0.89039 |
| C16 FP32 | 30.1406 | 0.90953 |

对应 outputs/rainlight_c8_test、rainlight_c8_integer_test_margin2、rainlight_c16_test 中的 summary.json 和逐图 CSV。定点略高不代表普遍优势。

清晰图保护：20张验证目标直接输入，C8相对原图 PSNR34.5625、SSIM0.98647；C16为33.3777、0.98002。仍会改变正常图，需要策略旁路。C8优先作为硬件候选，C16保留对照。

## 定点和硬件预算

TinyRestore为3x3 RGB输入卷积、5个深度可分离残差块、1x1 RGB残差输出；雨/雾同结构不同权重。感受野13x13，halo6。720x1272、核心分块128：

| 候选 | 参数 | 整图GMAC/帧 | 含halo GMAC/帧 | 30FPS所需GMAC/s |
|---|---:|---:|---:|---:|
| C8 | 1011 | 0.843 | 0.990 | 29.709 |
| C16 | 2659 | 2.271 | 2.669 | 80.084 |

三张140x140x8 INT16特征平面约0.941MB，仅工作集估算，并非实际BRAM分配。参数少不能证明部署安全，需硬件评估行缓存、通道复用和现有资源。

去雨整数候选位于 outputs/rainlight_c8_integer_margin2：全部180训练图校准、范围2倍余量；逐输出通道INT8权重、INT32 bias、二进制定标INT16节点、最近偶数舍入。含逐层小端二进制、形状/定标/哈希、运算图、逐层Golden与输入输出Q14。

全图验证20图和测试100图饱和均0，INT32保守界限检查通过；测试相对FP32最大绝对差约0.01882。NumPy以int64容器防主机静默溢出并检查目标int32界限，不代表硬件性能。

审计：初版8图无余量校准在测试发现130次饱和，保留旧结果。修订只用训练数据校准，再评测验证/测试。测试已参与开发诊断，因此是工程实测，不能宣称完全未触碰盲测成绩。

## 素材和去雾

来源与SHA见 public_sources.json 和素材旁.source.json。已有RainTrainL/Rain100L、作者Rain12、Set12、AOD-Net官方Caffe权重与3张雾图。O-HAZE官方45对室外人工造雾场景已完成下载、配对和评测，自定义30/5/10场景划分、等比最大边800，不是官方挑战划分。

保留起步实验：合成去雨短训未超过恒等基线，best=step0，明确失败。合成去雾仅2个测试清晰源8种变体，PSNR12.8031→18.5201，定点18.5156，不能代表真实道路。AOD三张无GT图仅作展示。

## 运行与验证

独立.venv已验证torch2.7.1+CUDA12.6在RTX4060 Laptop上实际前向/反向，安装包匹配官方SHA。见 outputs/gpu_environment.json。不要设置旧CPU包的PYTHONPATH。原去雨训练为torch2.14 CPU，GPU复跑不保证位级一致，以各experiment.json为准。

使用 .venv/Scripts/python.exe；所有输出目录必须为新目录：

```powershell
$py = 'D:/FPGA/weather_restore_lab/.venv/Scripts/python.exe'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
& $py -m unittest -v test_pipeline
& $py run.py audit --manifest data/rainlight_manifest.json
& $py run.py profile --output outputs/profile_new.json
& $py run.py train --manifest data/rainlight_manifest.json --output outputs/rain_new --channels 8 --steps 3000 --loss mse --device cuda
& $py run.py evaluate --manifest data/rainlight_manifest.json --checkpoint outputs/rain_new/best.pth --output outputs/rain_new_test --device cuda
& $py integer.py --manifest data/rainlight_manifest.json --checkpoint outputs/rain_new/best.pth --output outputs/rain_new_int --calibration-images 180 --calibration-margin 2 --golden-split val
& $py evaluate_integer.py --manifest data/rainlight_manifest.json --checkpoint outputs/rain_new/best.pth --integer-dir outputs/rain_new_int --split val --output outputs/rain_new_int_val
& $py infer.py --checkpoint outputs/rain_new/best.pth --input path/to/rain.png --output outputs/restored.png --device cuda
& $py infer.py --checkpoint outputs/rain_new/best.pth --input path/to/rain.mp4 --output outputs/restored.mp4 --video --device cuda
```

8项测试覆盖非零网络整图/分块、整数整图/分块位级一致、普通/深度卷积、舍入、溢出拒绝、量化误差、MAC和数据泄漏。3帧64x64视频只作通路测试；视频保留播放FPS并核对交付帧数，不含音频，播放FPS不是处理速度。

## 剩余验收

硬件实现普通/深度卷积、ReLU、重定标/饱和、残差加法，先与逐层Golden对齐，再完成HLS、布局布线、缓存一致性、现有资源和真板延迟吞吐验证。软件还需真实道路视频、检测辅助效果、连续帧闪烁、策略旁路及原低照度通路联调。尚无新模型FPGA帧率或资源验收结论。

## 本轮去雾结果

O-HAZE自定义10测试场景：输入PSNR13.3849/SSIM0.59186，C8 FP32为18.9577/0.66983，整数为18.9423/0.67016；全部测试饱和0、INT32界限检查通过。C8验证PSNR20.2367，C16为19.8246，优先保留C8硬件候选。训练可加 --cache-data 避免重复PNG解码，缓存只影响主机数据载入。

完整实测、正常图保护和剩余问题见 RESULTS.md。可评审的双任务候选包为 hardware_candidates/c8_hardware_candidates_v1.zip；未完成FPGA部署验证。


## GitHub 发布位置

硬件队友先读 [FPGA_START_HERE.md](FPGA_START_HERE.md)，直接下载 [C8 候选包](hardware_candidates/c8_hardware_candidates_v1.zip)。已选实验的原始摘要、逐图 CSV 和训练日志放在 [evidence/](evidence/)。本文 outputs/ 路径表示本机原始实验目录；数据集、虚拟环境和其余运行文件没有上传。
