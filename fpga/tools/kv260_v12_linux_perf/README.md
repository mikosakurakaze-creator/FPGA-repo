# Linux小型ring性能计时核心（Host候选，未批准运行）

`ring_runner.py` 为 lzm 提供可绑定实际 Linux DMA 驱动的计时/生产者/全量校验循环；没有板端连接器、物理地址分配器或默认执行CLI。[protocol_reference/pipeline.c/h](protocol_reference/README.md) 保存三模块寄存器调用协议的原始参考接口，仅供Host阅读或mock绑定；它没有Linux STOP、DMA分配和真实MMIO后端，不是可直接装载的Linux驱动。尚缺完整已审核运行平台和对应的实际DMA/MMIO驱动构建产物，因此不能直接在板上启动本目录。旧U-Boot go方案已经停止，不作为推荐执行步骤，本次交接不发布该方案的固件或执行脚本。

默认3槽，严格 `slot=global_frame_id%3`、A/B=`global_frame_id%2`，固定槽下一次使用时输入翻转；必须等槽校验完成为FREE后才能覆写。任意FREE池会破坏这个性质。每帧三个输出都全量填入非Golden poison再计算、全量原码比较及Guard检查，能够检测每个word漏写。已有六Golden中 `0xA5A5` 均不存在，身份审计在Host revision输出；实际绑定须核SHA，不能套用到其他Golden。

两段各6预热+120有效帧，分别预载A/B和PS实际复制低/全分辨率输入；三模块每帧均运行，预热必须校验drain后才开有效计时窗。正常生产者与validator并行，实际一次连续RAW时钟区间包含poison、真实输入copy、控制、记录、队列等待和校验竞争；单列producer FPS及包含末尾校验drain的fully-validated FPS。不能扣掉这些间隙后宣布持续30FPS。

校验包含额外测试开销：全输出poison每帧11,028,240B写，全原码比较读取输出和Golden22,056,480B/帧（实际DDR流量受Cache影响）。达到30的实测结果是生产路径能力的保守证据；未达到30时必须先判断checker/poison限制，不能把该数字当纯PL性能或直接宣布最终产品失败。各模块软件观察窗口与串行service独立记录，不能把其时间加总形成“连续FPS”。

`Backend`明确要求真实设备的DMA分配、映射、barrier、CSR独占、full compare及永久首错STOP。`compute`和`abort_new_starts`必须共享短kernel submit锁，序列化STOP检查与AP_START写；每个下游模块都重查STOP。Python Event本身不是板端提交原子保证。已在flight的事务无法撤销；异常时禁止新start/reset/自动重试。未知DMA未停时必须由驱动保持allocation/mapping/module引用；fdclose/进程退出不能释放，不允许force unload/sysfs解绑或复用地址。

绑定必须返回准备/校验实证计数：每帧full poison=11,028,240B、copy模式实际输入copy=5,533,200B、原码比较=5,514,120标量、slot guard=384B，mismatch/error=0；省略或不完整即STOP。`Completion`的starts/dones须显式来自实际驱动计数，`stage_evidence`携带原始start/done括号、poll/AP_CTRL及参数读回记录。完整真实provenance还须独立审核，回调自报数字本身不能证明板测通过。

所有长prepare/compute/verify绑定都须释放GIL或使用独立进程，并用真实重叠日志验证。Condition等待设有RAW时钟总deadline（最多1800秒）；首错先请求独立、非阻塞的DMA quarantine，再请求软件STOP，最后有界join（最多5秒），NOT_JOINED必须留在终态，不强杀线程。quarantine/STOP失败会显式报告unsafe/unknown，不宣称释放或空闲。driver回调本身必须有界/保留未知完成记录；同步AXI挂起无法被Python deadline撤销。

Linux候选资源层：真实platform device独占三段CSR；按实际总线可达范围配置DMA mask，`dma_alloc_coherent`及`dma_mmap_coherent`。正式参考拓扑有11个AXI master跨HP0/1/2/3；地址域审核须覆盖全部路径，不能把3模块当3个master。诊断image的实际配置仍需绑定证据。不能猜测`/dev/mem`物理地址或把CPU虚拟地址交给PL；不能错误添加`dma-coherent`来宣称HP支持snoop。coherent API仍需正确的ownership和memory barrier。Golden可用普通CPU内存，减少专用DMA占用。

若coherent mapping的CPU读限制checker，最小修复候选是驱动管理的可缓存pages + streaming DMA map/sync、严格CPU/device交还和定向维护；需另行实现/审核/冻结。不能通过全局Cache/MMU切换或伪造coherent属性补速度。新ring方案的Cache一致性依赖OS DMA API，当前未实现资源层、未核实际DMA域，不能把这些设计约定写成已验证能力。

`LinuxRawClock`只允许AArch64 Linux及`arch_sys_counter` clocksource；读`CLOCK_MONOTONIC_RAW`，ns为报告单位，不把1GHz单位冒称硬件频率。实际kernel/DT、arch timer频率/配置与时钟分辨率依据必须随原始日志冻结、独立审核。kernel中的`ktime_get_raw_ns`与用户RAW时钟须核同一时间域；不依赖Windows时钟、JTAG轮询或U-Boot go ABI。

Host验证：`python -m unittest discover -s fpga/tools/kv260_v12_linux_perf -p test_ring.py`，只验证所有权、固定槽翻转、完整执行数量、首错隔离、窗口边界和无retry。mock产生的数字永远不是板测；核心也不自行更新BOARD_30FPS。

`clock_probe.c`是普通Linux用户态只读时钟探针，已有Host交叉编译产物；ELF由Linux进程loader加载，地址是进程虚拟地址。严禁把它作为U-Boot raw/go、bootelf、JTAG dow或CPU接管程序。它没有MMIO/DMA/Cache修改，尚未在板上运行。交叉编译器放入PATH后可在仓库根运行 `aarch64-linux-gnu-gcc -std=c11 -O2 -Wall -Wextra -Werror -static fpga/tools/kv260_v12_linux_perf/clock_probe.c -o outputs/clock_probe`（先创建忽略的outputs目录，静态链接需交叉工具链提供目标libc）；不在本次交接中执行产物。`analyze_ring.py`记录mean/max/p95/p99、各IP软件观察窗口、wait/prepare/verify、连续30-output窗口和validated吞吐，始终需要独立真实板端provenance审核。

已补普通进程内存上的[native prepare/verify实现](native_hotpath/README.md)和精确候选kernel build材料；[后端进一步审阅](../../docs/kv260_v12_linux_backend_review.md)记录官方脚本重加载PL分支、CMA及driver生命周期限制。实际资源层仍未实现/Kbuild/集成，不能声称完整Linux驱动已交付。下一步先取得完整已知Linux启动包、可用build环境及实际DT/PL时钟/reset/DMA域材料，再完成该层、冻结精确运行范围、申请新板端授权。若checker无法跟上30，保留一个60帧archive方案作为测量去除验证竞争的替代：只需约0.7GiB而非1.4GiB，先全窗口真实计算，再窗外全量比较；不能重新退回独立S2预实验。
