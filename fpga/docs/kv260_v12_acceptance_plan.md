# KV260 V1.2 连续运行与性能验收方案

更新：2026-10-09。状态：`BOARD_BRINGUP_BASE=PASS`、`BOARD_MULTI_FRAME=NOT_TESTED`、`BOARD_30FPS=NOT_TESTED`。本文件及配套工具只做 Host-only 准备；没有新增板端访问或操作。

真实基线：已在 diagnostic bit `347f49477fcbed2ebd1d8418e599a213fc56c3b99d43d6b8e022b0e199c96d86` 下完成 night_01 的 CNN→Bilinear→Curve，每模块一次启动，三个完整输出 bit-exact，60 次阶段 guard 比较通过。原件证据 ID 为 `p7single_frame_1009_01/attempt02`，文件名为 `actual_evidence.json`、`actual_scope_audit.json` 与 `run/`；共享 [单帧摘要](../bringup/kv260_v12/single_frame_evidence.json) 保存输出 SHA 和门禁结果，完整本机目录由 Master 的外部 inventory 定位。本板的多帧和 FPS 均未测量。

最后确认 D-cache OFF，MMU `NOT_ASSESSED`，本轮 UART/JTAG/owned hw_server 已关闭。这些是上次实验的末次观察，不能代替下次执行前的必要门禁，也不能假定上电、image 或运行环境已改变。冷启动恢复和接口定义见 [软件交接](kv260_v12_software_handoff.md)。

## 1. 已核对的重复调用语义

核对对象是正式 package 的三个 `*_control_s_axi.v`、HLS 源码及 [寄存器映射](v1_2_hw_register_map.json)，不是根据不同版本 HLS 的通用示例猜测偏移。

| AP_CTRL bit | 实际行为 | 软件操作 |
| --- | --- | --- |
| 0 ap_start | 写 1 置位；ap_ready 握手时回落到 auto_restart 值 | 每次调用只写一次 `0x00000001`；写 0 不能取消已经接受的调用 |
| 1 ap_done | task_done 锁存；读取 AP_CTRL 清除 | 唯一轮询者保存第一次含 done 的读值；新调用前消费旧 done，不能把旧完成当作新帧完成 |
| 2 ap_idle | 核 idle 的寄存观察 | start 前必须 idle=1/start=0/auto_restart=0 |
| 3 ap_ready | task_ready 锁存；读取 AP_CTRL 清除 | ready 不能独立代替本次 done 或下游数据就绪 |
| 7 auto_restart | 可读写，控制握手后再次启动 | 本阶段始终为 0；发现为 1 则停止，不擅自清除或追加启动 |

GIE 应为 0；计划不改 GIE/IER/ISR。AP_CTRL 不是完全无副作用的只读寄存器：读会消费 done/ready，因此必须单一控制者，禁止监视工具同时轮询。轮询捕获 done 后还要核对 idle=1、start=0，完整输出和 guard 通过才能释放 buffer。完成后的下一次 AP_CTRL 读应回到 idle-only `0x4`（忽略保留位不能忽略意外 interrupt/auto_restart）；不能写成“每次完成一定永久保持 0xE”。

CNN HLS 顶层每次调用均执行 `load_model(...)` 和 `bank_point_weights(...)`，model 数组是本次 invocation 的本地 BRAM，没有 `weights_loaded` 跨帧捷径；模型 DDR 不变并不省去每次核内加载。Bilinear 每个通道进入时重置 row-cache 的 `valid=false`；Curve 每次从本帧 input 重新读取。没有要求正常重复调用前 reset 的接口协议；若出现异常，不把 reset 当作自动重试。

正式 CNN 的 write-credit 修正在 package RTL 中，不仅是重综合 HLS 源文件即可重现。参考 [CNN package 说明](../ip/cnn_v1_2_writecredit/README.md)；本次不改这些字节。

AMD [UG1399 控制协议](https://docs.amd.com/r/en-US/ug1399-vitis-hls/Block-Level-Control-Protocols) 说明 hs 信号用于调用握手；本工程三个独立 DDR IP 没有硬连线 downstream backpressure，帧间依赖必须由 PS 调度落实。

## 2. 分级测试及停止边界

| 批次 | 输入和 starts | 检验内容 | 进入条件 |
| --- | --- | --- | --- |
| S1：2 帧串行复用 | night_01→night_01；每 IP 恰好 2 starts | 正常再次启动、old done 消费、不同 poison 覆盖、6 次完整输出和 120 次阶段 guard | Master 新批准；新两帧适配器通过 Host mock 与独立范围审核 |
| S2：3 帧不同输入 | A→B→A；每 IP 恰好 3 starts | 各帧三个输出使用各自 golden，证明 B 不是上帧残留、回到 A 可重现 | S1 PASS；B 的完整来源、预处理、量化、3 份 golden 和 SHA 完成离线核对；独立新批准 |
| S3：16 帧串行 | 预定 A/B 交替，帧号不可跳过 | 重复正确性、guard、计数 conservation、无 reset/重试 | S2 PASS；精确新预算及新批准 |
| S4：长批次 | 先 100 帧，再明确次数/时间的 soak | 完整正确性、guard、错误数、日志有界、热稳定性 | 前序 PASS；板端 runner、Cache/DDR 所有权方案及新批准 |
| P：跨帧流水及 FPS | 双槽 A_low/A_full/input/output，单 workspace，PS 异步调度 | RAW/WAR/WAW、实际 overlap、持续吞吐、端到端交付 | 串行稳定；所有权调度先离线核对，再批准真实实验 |

S1 不用于 30 FPS。先顺序运行 CNN→检查→Bilinear→检查→Curve→检查，再处理下一帧；第一帧任一阶段失败，不开始第二帧。每帧开始前所有 IP idle，上一帧所有 Host 输出校验已完成，然后同一组 buffer 才可覆盖。模型区保持只读于 PL；Host 本次方案为简洁对账可重新写入同一冻结模型，写预算必须包含它。

S1 两帧均完整重写单帧原有 30 个 region（10 data+20 guard）；第 0 帧输出/workspace poison `0xA5`，第 1 帧为 `0x5A`。数据和 guard 逐块读回，确认 staging 后才 start。每帧固定 27 个参数字写入及读回，再各 IP 一次 start；采用更保守的完整 staging，避免首批引入“参数只配一次”的新假设。CPU 不在某个 IP still-running 或旧 consumer 尚未释放时覆盖它持有的 region。

### S1 精确申请范围

再次明确指定 `0x20000000–0x23FFFFFF` 64 MiB 为本次诊断专用并允许覆盖既有内容；实际只碰冻结 plan 的 30 个 region，最高 end-exclusive=`0x2128D940`，不清零整个 64 MiB。LMB 未保留不是所有权证明；这个诊断物理地址不写入生产软件 ABI。可审阅的 [两帧冻结JSON](../tools/kv260_v12_acceptance/repeat_2frame_plan.json) 包含每帧30region payload/SHA、27参数和三次start；它尚未授权或执行。

| 项目 | 总上限 |
| --- | --- |
| 新连接 | 1 次有身份/Host 独占门禁的 UART+JTAG 调试 session |
| UART | 仅一次 `dcache` 无参数查询；必须 OFF，不执行 `dcache off/on`、裸 CR 或其他命令 |
| DDR SET | 38,051,318 bytes，632 个≤64 KiB 的 staging chunk；仅上述 region |
| 参数 SET | 54 个 32-bit word；固定基址 CNN A0020000 / Bilinear A0000000 / Curve A0010000，偏移沿用已核对 plan |
| AP_START | CNN=2、Bilinear=2、Curve=2；每次写 `0x1`，共 6 次 |
| CSR SET | 240 bytes、共 60 次（54 args+6 starts）；合计全部 SET=692 次 |
| core GET | 保守 cap 1,768 次，已冻结 DDR/CSR 标签和范围，含 staging/args/outputs/guards/polls；不能作为任意 MMIO 通行证 |
| PS GET / CONFIG | 保守 cap 354 / 16，严格复用已审核只读地址与身份/CONFIG/reset/signature/PL0门禁 |
| 每 IP 每次完成轮询 | ≤100 次且≤5,000 ms，任何超时停止 |
| 预 staging guard读回 / 阶段guard比较 | 40 / 120；所有 6 份输出完整 bit-exact |
| 全局 retry / reset / reprogram / GPIO / PMU / Cache / MMU / clock / isolation / 存储写 | 均为 0 |

这些 GET cap 来自原单帧有界策略的两倍，真实开始前适配器必须把它们细化为 frame/stage/address/tag 的白名单，不能只增加一个数字而取消 gate。1800 秒原单帧 Host 上限不会自动变为硬杀正在执行的事务；两帧总 Host 观察 nominal cap 3600 秒。超时不再派发新调用，保留事务原件，结束可关闭的 Host 客户端；无法证明事务返回则记录 active/unknown，不宣称 idle或安全复位。

新 session 的少量前置只读门禁必须与之前成功环境一致：精确板卡/physical PSU/bit 身份、U-Boot idle（利用被动记录）、Cache OFF、AP idle/GIE0、合法 scratch 覆盖批准。MMU 未独立确认；当前使用原成功 transport 的物理 PSU mode=24、不 force，并限定当前成功 U-Boot 场景。出现 Cache ON/未知、新的 OS/image/已复位/无法证明 idle/所有权，直接停止并报告；本次审批不自动包含恢复 Cache、PMU、GPIO 或重新 program。

审批后仍要先完成 **Host-only 有界适配器**：复用原 transport 和 Host 管理，不重新开发整套；新增不可重复审批锁、frame标签、全局写/starts预算、old done/new done mock、第二帧 poison与失败阻断测试，独立核对。已用过的 `execute_once.py`/connection lock 不可重新运行或外套循环。

可直接批准的文案：

> 批准 S1：将 0x20000000–0x23FFFFFF 再次专用于本次诊断且允许覆盖；在 Host 离线适配器和独立范围审核通过后，以现有已验证 diagnostic bit 和 U-Boot 环境运行 night_01 的 2 帧串行 CNN→Bilinear→Curve，每 IP 最多 2 starts，54 参数写，DDR 写最多 38,051,318 bytes / CSR 240 bytes，每次完成≤100 polls/5秒；6 份完整输出和 120 次阶段 guard 全通过才 PASS。只查询一次 Cache，必须 OFF；不修改 Cache/MMU、GPIO/PMU/clock/isolation、不 reset/psu_init/program、无存储写、无重试或自动恢复。任何门禁、超时或数据错误立即停止，不进入更大批次。

## 3. 不同输入与 Golden

现有真实板测和 Phase4F 的 8 帧 RTL 测试均重复同一个 night_01；它们不能证明不同输入。第二帧 B 不可仅换帧号、输入 SHA 或输出 poison，也不能沿用 A 的 CNN golden。

准备 B 时复用固定量化 protocol、冻结 weights/bias/frac/LUT：从一份合法完整 720×1272 RGB planar Q14 数值帧生成 B（避免修改模型或解码图片），按原 `prepare_golden.py` 的采样点和 nearest-even 2×2规则生成 60×106 输入；离线生成 B 的完整 CNN A_low、Bilinear A_full 和 Curve enhanced，并用现有数值参考/厂商 C 仿真交叉验证。CNN reference 必须按原整数模型生成，不能拿实际板上输出反过来当 golden。B 的 input/model 与各阶段 expected SHA、字节数和逐帧映射均冻结，至少确认 A/B 输入及完整阶段输出确有差异。需要的 CSim 或模型 reference 步骤尚未执行，保持 TODO，先不扩大成新训练或综合。

重用入口：[golden 准备](../perf/v1_2_system_tb/prepare_golden.py)、[厂商 fixed-point 核对](../perf/v1_2_system_tb/tb_golden_vendor.cpp)、[Python 数值参考](../reference/fixed_point_v1/arithmetic.py)。前两个历史脚本内有实验专用路径；必须在新外部目录经 Host-only 改成显式输入输出参数，不能写回冻结数据。S2 前 B golden 未就绪是明确阻断条件。

## 4. 性能测量定义与计时条件

| 口径 | 起止与内容 | 当前条件 / 可用结论 |
| --- | --- | --- |
| A 单 IP | 内部 accepted start→internal done 的核执行；若通过 m_axi 则含DDR等待。真正纯算术不含外部DDR须另行隔离测量 | 现 bit 没有此专用事件计数；AP轮询只得到软件观察上界，不能标“纯计算时间” |
| B 串行三模块 | 第一CNN accepted start→该帧Curve done，包含三核、DDR访问及中间调度 | 板端本地计时可测应用串行kernel区间；若无内部事件观测，注明CSR提交/轮询偏差 |
| C DDR及跨模块开销 | 核实际访问、CPU缓存同步/复制、依赖等待分别记录；允许跨帧pipeline但禁止数据提前覆盖 | m_axi不等于PS又拷贝一份；没有AXI counters就不能把A/B差值全归因DDR，也不能简单相加stall |
| D 端到端 | PS取得本帧完整输入→预处理/DDR提交→三核完成→同步并取得正确增强图像 | 必须实际板端软件提交与取回；没有相机时标为“预载/内存输入E2E”，不能宣称真实相机到显示 |

Windows/JTAG 全量传输、逐笔 CSR poll 的 68/60/80 ms 是 Host 观察耗时；不能用于任何板级 30 FPS 推断。CSim 和 RTL DDR model 的约30 FPS只作规划依据，不替代真板 gate。前序结果是单槽串行；30 FPS 方案需要评估跨帧双槽流水及共享 DDR，不能默认三核总串行延迟等于稳态输出节拍。

首选运行板端可审核小程序，通过已存在计时 API/Arm generic counter记时间。记录 counter读法、权限、frequency来源、启动时校准与同核单调性；使用必要的IO/内存屏障，时间窗内不打印 UART。CNTFRQ 的值不是 PL 时钟的实测，也不能由 CPU 主频推断 system counter。现阶段尚无已部署板端程序或已核验 timer，所以性能状态仍 `NOT_TESTED`。Arm [Generic Timer 原始说明](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Generic%20Timer.pdf?revision=c710e7a7-9f52-4901-8c9d-91b19f44f9c7) 与 AMD [UG1085](https://docs.amd.com/v/u/en-US/ug1085-zynq-ultrascale-trm) 用于选择计时方法，不在本轮修改计时器、CPU执行状态或任何板端软件。

若必须得到 A 的准确内部事件，离线设计可增加一个64-bit PL自由计数器、逐核start握手/done快照、frame序号、overflow/status只读寄存器；跨PS读双字采用稳定snapshot，不能把不同瞬间的高低字拼接。监测逻辑不参与数据/控制反压；独立仿真证明事件对应、位宽与CDC，并重新离线构建/时序审核后申请program。当前 diagnostic bit不因性能计划被替换。若counter按PLclock计周期，秒换算需要证明实际频率；单靠BD100MHz配置不能校准时钟漂移。

### 真实30 FPS 批次设计

先完成S1/S2/S3。板端runner/DDR allocation/Cache一致性实现后，预先冻结一个例如 **10 warm-up +300计量帧** 的有限批次（需新审批，当前不执行）。每帧仍实际计算，禁止跳过CNN/复用旧A_low或只重复旧enhanced。两输入 alternating/多样性列表、每帧golden、buffer生命周期与所有frame IDs均预定。流水fill/drain和warm-up另记，不事后挑选更快的窗口。

数据缓冲区由板端allocator/dedicated reservation证明所有权，至少16字节AXI base对齐且Cache维护区间按实际Cache line取整并隔离guard/其它对象。选择明确非缓存映射或驱动管理DMA一致性；生产Cache可开，只做定向CPU→device clean和device→CPU invalidate/sync，分别计入D。Linux `dma_addr_t`/DMA映射与IOMMU状态要实际核验；不是任意用户虚拟地址或本次0x20000000 scratch固定值。

输入上传/定向同步、每IP提交/完成、模块依赖wait、输出同步/完整验证各记独立timestamp。D计时包含实际提交和取回，对每帧完整bit-exact和guard的开销也必须说明：若在计量窗内校验，则算入D；若外部离线校验，板端需保留每帧完整输出或提供另外独立验证批次，并明确不以抽样/不可靠CRC替代未验证的完整功能。在小buffer上不能提前覆盖未校验输出来“跑快”。完整验证都放在窗内是最保守初版，可建立 correctness+throughput 同时通过的结果。

记录至少：input帧数、各IP提交/完成数、输出数、总wall time、warm-up/fill/drain time、平均FPS、逐帧提交→输出latency、output interval min/mean/p95/max、错误/超时/guard数、Cache模式、timer frequency、输入来源和是否包含预处理/复制/完整校验。稳态输出FPS=`(N-1)/(t_last_output-t_first_output)`，整批E2E=`N/(t_last_return-t_first_submit)`分开报告。不得用第一帧延迟倒数代替稳态FPS。

验收门槛预定：全量正确性和guard无错、starts/done/output/frameId守恒、无reset/retry、稳态及所声明的D端到端平均≥30 FPS；额外把max output interval≤33.333…ms作为严格无抖动目标并独立列结果，不能只平均合格掩盖掉帧。若D未具备完整条件，只能分别报告kernel/内存input吞吐，不标真实相机系统30FPS PASS。

未达到目标时依次对照：单核执行窗口/实际overlap、DDR响应与队列/可测带宽、PS调度空隙、CPU预处理和缓存同步/输入输出复制。没有AXI统计便保留“未归因”，先做最小新证据测量；不能从仿真数值推断唯一瓶颈，不能在未批准时改算法、时钟或硬件配置。

## 5. 异常停止与交板清单

门禁不一致、AXI无响应、poll超时、unexpected auto_restart、参数读回错误、任何输出或guard mismatch，停止派发后续frame/stage，并保存active IP、最后AP值、已消费budget和原始数据。AP_CTRL没有已核对的abort位；写start=0不能撤销计算。若仍busy/事务unknown，不覆盖DDR、不移除仍被引用的mapping、不宣称所有事务完成；恢复/ reset /重新program另申请，失败帧不自动重试。

本轮交付可完成Git版本、源码/构建配置、diagnostic bit及formal release不同SHA说明、最小冷启动/恢复、接口/shape/同步说明、单帧复现输入与golden、离线多帧审批计划。最终交实体板前仍需补齐：

- S1/S2/S3或已批准长批次的实际完整结果与错误处理状态。
- 可靠板端时间基础与D真实性能结果；达不到30FPS时保留实际FPS和瓶颈，而非提高门禁文本。
- 可复现的软件启动环境、实际buffer allocation/Cache方案、最简功能调用入口；没有实现的Linux自动加载/驱动不得写成已实现。
- 一次独立cold-boot复现（未来新授权）、Git commit与bit SHA绑定、必要非仓库artifact取得方式。
- 交板前Host连接关闭、运行idle/无存储写证明、最后Cache/MMU/boot状态与known limitations，按证据决定是否可断电。

配套 [离线计划工具](../tools/kv260_v12_acceptance/README.md) 已验证成功单帧plan身份、region无重叠和精确两帧预算；该工具没有板端runner。所有未完成项保持 `NOT_TESTED`/TODO，本轮没有实际多帧启动、Cache/MMU修改、重烧或Linux部署。
