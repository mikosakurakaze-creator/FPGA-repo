# B 组实际执行、限制与修改记录

本轮用户要求先读取A交付和远端任务，反馈逐节点尺度、INT16权重代价、累加位宽、布局与DDR/DMA/ABI方案，并开始算子验证。所有新增内容位于 `C:/Users/wzh16/Desktop/competing/griddehaze_fpga`，未替换旧工程。

本文件原始执行表对应首次评审。用户随后确认新增独立去雾核，已补齐逐元素HLS原型；后续执行与限制以change_review_20261024_additive.md和evidence/review04为准，review01/02/03保留其原始阶段身份。

范围最终收敛：本轮仅做FPGA加速器、DDR调度和综合实现，交付bit/XSA。后续提到驱动、设备树部署、上传、HDMI或实际DMA分配未执行，是外部系统联调状态说明，不是要求本用户完成这些软件任务。分工与硬件完成条件以responsibility_boundary_20261024.md为准。

## 实际执行

| 层级 | 本轮结果 | 本地原始证据 |
|---|---|---|
| 附件ZIP | SHA匹配；安全检查路径后原样解压；5,884份payload逐项长度/SHA匹配 | 原始附件、A DELIVERY、evidence/handoff_identity |
| 远端任务 | fetch并读取feat/software的doc三份文件，commit a8d1d9a；没有切换原分支 | 远端Git对象 |
| 参数与布局 | 两个bundle、243张量、零padding、graph/blob/code身份、逐通道实际权重累加界独立核对 | work/preflight02 |
| A原单元测试重跑 | 本机实际58项通过，退出0；不是仅转述交付报告 | evidence/a_unit_tests_20261024.json为真实工具输出摘要 |
| 地址计划 | 6个尺寸、全部320节点、64字节对齐、存活相交不重叠；大图CPU实际使用该复用计划 | memory_*.json、对应CPU运行 |
| B独立C++ | random、black、white、channel、impulse、4×4、32×48、34×46各320节点和最终输出一致 | work/cpp05 |
| B独立大图 | foggy001_675x1280及random_720x1280：逐节点原始字节SHA、最终raw一致，输入不变、区间guard通过 | work/cpp_large01、cpp_720p01 |
| 负数数学边界 | 130项RHAZ、正负half tie、INT64极值、左移拒绝与宽加法测试通过 | test_math.json |
| 分块卷积原型 | 8组完整小网络：conv/deconv调用缓存tile源，其余算子仍为独立CPU实现；各320节点一致 | work/tile02 |
| A提供的比较工具 | 对B生成的random实际输出与320节点检查通过，带bundle和input hash | work/tile02/a_comparator_random.json |
| Vitis C仿真 | 48-bit ap_int实际参与：首层、s2、128通道1×1、两级奇数目标deconv，共5个节点全部精确 | work/hls02/csim.log及actual raw |
| HLS综合/IP | 卷积tile核综合通过，导出RTL/IP、真实驱动CSR；资源17,392 LUT/9,796 FF/73 BRAM18K/67 DSP/0 URAM，7.300ns估算 | work/hls02/result.json、csynth报告 |
| 实际导出接口 | read_mem数据64位、write_mem32位，地址64位；AXI-Lite数据32位、地址8位；尚未连接PS | review中的generated_interface.json |

大图CPU计时约232.7/249.5秒，两个任务同时在同一电脑运行且含节点哈希；仅作为复现日志，不是公平性能基准或FPGA速度。使用独立输出驱动完整DAG，未将A的CPU输出复制为候选。所有大图320节点仅保存新SHA与最终raw；没有新增全部大图中间raw。

第一版D盘HLS尝试失败：工具生成make规则包含 `-include /dev/null`，本机已有普通文本文件 `D:/dev/null` 导致missing separator。换到C盘干净输出工作区后，实际C仿真和综合通过。保留原失败；未删改系统文件。另发现Vitis launcher可能在日志报ERROR时仍返回0，脚本同时要求无ERROR/FATAL、真实actual和PASS marker、综合报告，避免误报。

MinGW8.1的filesystem兼容问题导致早期cpp01/02构建失败；改为普通路径文件I/O后通过。后续加SHA/执行源冻结又遇到一次NOMINMAX重复定义，已用条件宏解决，失败目录保留。最终CPU/HLS运行各有执行源快照和哈希，不能以当前源码直接冒充早期执行源码。

## 未执行/未取得

- 没有完整网络的HLS/RTL co-sim，没有算子RTL数值或最终实现网表数值回归；CPU原生tile模式不是48位vendor仿真。
- 没有新系统综合、布局布线、bit/XSA/BIN、设备树、板端驱动适配、板测或HDMI联调。
- 没有最终PL图调度器、整图ABI/version guard、DMA错误/排空硬件。逐元素HLS核随后已完成C仿真和HLS综合，尚未做RTL或系统集成。
- 没有实际CMA分配、coherent DMA驱动源码/DT、DMA mask、SMMU/专用复位运行态。本版没有猜物理DDR地址或假设450MiB连续内存已可分配。
- 未测板端时钟、吞吐、真实图片请求耗时，不援引旧34FPS；HLS动态延迟为undef。
- 用户随后已确定保留旧weather与低照度，新增独立GridDehazeNet核；新的BD和系统实现尚未完成，具体见integration_scope_20261024.md。
- 不重新训练、校准；不把无配对Fog/Rain检测数据当恢复真值；视觉验收待负责人确认。

## 修改/新增及原因

| 文件 | 原因与关键差异 |
|---|---|
| .gitignore | 原始附件/大图运行raw/工具缓存仅本地保存 |
| src/fixed_math.hpp、test_fixed_math.cpp | 独立RHAZ，避免有符号右移和INT64绝对值溢出；负数边界与提前饱和负对照 |
| src/host_graph.cpp | 不依赖A执行器的CPU逐节点整图、DDR相对地址复用、输入/边界检查、逐节点SHA |
| tools/preflight.py | 独立解析二进制、证明真实权重界、生成每节点地址与内存/流量预算 |
| tools/verify_cpp.py | 编译执行、执行源冻结、Golden检查、失败退出；不因生成PNG而判通过 |
| hls/conv_tile_top.*、tb_conv_tile.cpp | 缓存输入/权重后MAC，48位累加，目标尺寸deconv，批量写回原型 |
| tools/hls_trial.py | vendor真实C仿真/综合、固定输入与源hash、错误日志和产物门禁 |
| tools/board_memory_probe.py | 板端只读内存信息；不操作MMIO、不改CMA或SMMU |
| tools/collect_review.py | 仅收集小报告和实际CSR、保护源数据与参数；绑定文件SHA |
| README及docs | 给A/软件侧的反馈、明确的ABI提案和已生成接口、未确认数据与验证边界 |

当前工作目录没有独立Git绑定，继承competing/AGENTS约束。已有仓库 `github clone/weather_fpga_integration` 仍在weather_fpga_integration、e8662ce，工作区干净。本轮仅fetch/read，没有git add/commit/push，也没有切换或新建分支。建议未来审核后的Commit Message：`feat(griddehaze): add exact B operator prototype and DDR interface plan`。
