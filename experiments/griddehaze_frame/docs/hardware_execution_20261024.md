# 新去雾核硬件实施记录

本轮目标：保留旧weather与低照度链路，补齐GridDehazeNet整网PL调度、DDR控制，完成能够实际验证的综合实现并导出同版bit/XSA。不开发上传、Linux驱动或HDMI。

最新来源纠正：第一次 `grid_system01` 误选历史 tile 系统，已由 signed-DSP 检查阻止实现。当前正确来源为 `stream_system01`，重建在 `D:/weather_builds/grid_system02`；详见 `system_seed_correction_20261024.md`。此前“与 seed 一致”的 BD 结论不等于与当前流水版一致。

## 实施顺序

1. 将冻结的320节点和尺度/参数布局生成硬件常量，新增整图HLS顶层；PL遍历节点及tile，软件仅提供输入、权重和已验证的相对DDR布局。
2. 对整图顶层进行原生及Vitis整数仿真，验证完整Golden、错误描述符与DDR复用边界；完成HLS综合并核对实际接口。
3. 在独立构建目录保留原模块，接入新核，重新综合、布局布线、审计时序与实现电路。
4. 只有实际构建与验证通过后才导出bit/XSA及校验说明；错误与未完成部分如实保留。

开始状态：已有卷积/反卷积及逐元素HLS算子与Golden验证；尚无整网PL调度、最终系统BD或新版整网bit/XSA。原仓库和旧发布物只读参考，不提交或推送。

2026-10-24 安全事件和后续实际运行记录见 `security_interruption_20261024.md`。保留失败启动历史，后续用户授权正常本地执行，不修改安全软件设置。

## 完整图执行进展

- 已新增 `griddehaze_frame_top`，由 PL 遍历全部 320 节点并调用缓存卷积及逐元素算子。
- 原生恢复运行：8 组各 320 节点、最终输出、首组冷暖两次以及 11 项错误描述符测试通过；2,560 份实际节点文件重新核验 SHA 与长度一致。
- Vitis 48 位 C 仿真：同样 8 组全节点一致，11 项错误描述符通过。
- HLS 综合估计：LUT 23,908、FF 12,806、BRAM18K 99、DSP 44、URAM 0，估计时钟 7.300 ns。延迟/II 未确定，存在未满足的循环调度约束，不能据此报告帧率。
- HLS 实际导出两个 32 位数据、64 位地址 AXI master：`feature_mem` 和 `parameter_mem`；AXI-Lite 为 32 位数据、8 位地址。
- 加强后的独立导出 RTL 已通过 4×4 和新增 5×7 奇数尺寸冷暖运行：每帧全部 320 节点一致，均有错误 model 和错误 Golden 检出证据，核心 DONE 前延迟写响应已排空。当前结果分别见 `work/frame_rtl05`、`work/frame_rtl_odd02`；原结果保留。A 原始比较器再次复核这四份最终原始输出，均零差异。
- 正确来源的新 BD 已建立并通过结构审查，保留四个旧核和全部 PS 参数；新核 base=0xA0040000，feature→HP3、parameter→HP0。当前系统工作区为 `D:/weather_builds/grid_system02`，不得交付旧 `grid_system01`。
- 新核 Vivado OOC 综合已完成：LUT 10,971、FF 11,071、BRAM tile 44（33 RAMB36+22 RAMB18）、DSP 48、URAM 0。
- 正确五核系统整机综合通过；实际综合资源为 LUT 92,602/117,120（79.07%）、FF 96,134/234,240（41.04%）、BRAM tile 116/144（80.56%）、DSP 1,009/1,248（80.85%）、URAM 47/64（73.44%）。这是综合统计，不是布线后结论。
- 五核实际生成的全部 524 份 Verilog/ROM 与冻结输入逐文件一致，综合完成及 ROM 加载核查通过；已启动 implementation。
- 尚无该新核的 Vivado 布线、最终 bit/XSA 或板端证据。当前候选的复位、错误与地址边界限制见 `frame_interface.md`。
