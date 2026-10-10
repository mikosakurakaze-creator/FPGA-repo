# KV260 V1.2：Linux后端进一步Host审阅

2026-10-09。现有审阅材料交接给lzm；本次不继续开发性能框架、不板端操作，未知go停止，BOARD_30FPS=NOT_TESTED。本文补充[小ring方案](kv260_v12_runtime_alternative_review.md)，不构成新的板端批准，也没有把目标改成Host模拟验收。

## 已补齐的材料与实现

已从[Canonical官方kernel pool](https://ports.ubuntu.com/pool/universe/l/linux-xilinx-zynqmp/)取得精确5.15.0-1027.31的image、headers/common headers和buildinfo，四包共33,610,702B；来源/URL/SHA和离线审计由硬件端本地保管；未确认再分发条件的第三方包不进入本次Git或大文件交接包，接收方按官方来源取得匹配版本。image中的压缩内核与先前FIT的kernel-1逐字节一致（SHA256 `bffb86cca8b6964a18cf63657cc0502ea577f267996c45230d957b3a64221399`），解压后亦一致。headers含`.config`、生成头、真实`Module.symvers`；config与buildinfo相同，启用MODVERSIONS。这是精确的候选内核/build身份，仍不是板上当前U-Boot或bootchain匹配；尚未验证发行签名。

新增[native prepare/verify helper](../tools/kv260_v12_linux_perf/native_hotpath/README.md)：对普通进程映射执行三个完整输出的逐word poison、A/B输入copy、INT16全量Golden比较和Guard扫描。通过ctypes.CDLL调用可释放GIL，长校验可与另一槽生产者并行；没有transport、ioctl、DMA分配或CSR操作。成功回执由实际完成的11,028,240B poison、5,533,200B copy（copy阶段）、5,514,120标量和384B Guard生成；首错即返回部分实际检查量，真实binding须立即STOP，不能把部分扫描记作PASS。

span校验涵盖溢出、界限、对齐、Guard空间和所有只读/可写/元数据的虚拟地址别名；它不能证明两个VA不映射同一DMA物理页，不能代替真实kernel owner或Cache同步。六Golden的独立SHA和poison不存在检查必须在计时前通过。模型/共享输入/工作区及全部Guard仍由实际backend独立审计。Host复制Golden模拟输出只测试比较器，未执行CNN/Bilinear/Curve。

## 官方启动脚本不能原样盲用

已只读审核精确下载归档的script payload。正常MMC/USB分支识别KV/KR后追加`cma=1000M`，KD为512M；KV260 revB候选DT无CMA节点，只有PMU保留区，Kconfig无override默认32MiB。因此不能由默认32MiB断言实际CMA不足，也不能假定实际有1000MiB。未来须核真实bootargs、CMA实际reserve/free与各次分配，参考75.4MiB总工作集不是CMA参数；约49.7MiB DMA数据和页对齐/allocator余量须单独计。

同一script在介质存在`/system.bit`时会执行`fpga load`。这与“保留已验证诊断bit”的优先选择有直接关系；未检查完整启动介质、boot分支及rootfs服务前，不能原样启动并声称PL未变。未来方案需要明确是否保留原bit、哪些boot配置/服务会加载FPGA或改变PL clock/reset，逐项纳入新授权。本文没有执行脚本、准备可自动启动介质或修改bootargs。

## DMA拓扑和所有权必须覆盖全部11路

正式参考[便携寄存器map](kv260_v12_register_map.json)的连接为：

| PS入口 | PL AXI master | 数量 |
| --- | --- | ---: |
| HP0 | CNN/gmem_input、gmem_output、gmem_workspace | 3 |
| HP1 | CNN/gmem8、gmem32、gmem_lut | 3 |
| HP2 | Bilinear/gmem_input、gmem_output | 2 |
| HP3 | Curve/gmem_input、gmem_parameter、gmem_output | 3 |

三模块共有11个AXI master跨4条HP路径，不能把“3模块”简化成“3个master”。当前诊断bit没有配套XSA，正式映射是参考；现场诊断image的实际路由、stream ID和PS配置仍须绑定证据。

最小聚合single-DMA-device实现须证明全部11路的bus窗口、dma-ranges、SMMU/stream ID/domain和mask，使同一dma_addr_t对每个consumer有相同意义。DT自报属性或仅比较iommu_get_domain结果不够。不同域则为共享底层buffer按每个device取得各自映射/地址，或由最小实现直接拒绝；不能把一个device返回的DMA handle写给另一未经证明的consumer。[Linux DMA API依据](https://docs.kernel.org/core-api/dma-api-howto.html)。

真实driver应独占三CSR resource，独占session/唯一AP_CTRL reader，只接受driver分配的buffer ID/slot/frame，不接受用户raw物理地址；GIE/IER/ISR及idle/start/auto-restart门禁通过后才写参数，所有64-bit pointer low/high都写并读回。resource claim只能排除其它遵循内核resource机制的driver，仍须核UIO、FPGA manager、root /dev/mem、JTAG及其它CSR reader。没有这些证据不进入首次start，不能用一次试跑替代地址域审核。

## STOP和退出不能只靠文件句柄

STOP须区分REQUESTED和CONFIRMED：先独立发布stop_requested，AP_START在短submit mutex内重查并登记admitted stage，STOP确认用有界trylock，不跨整个poll持锁。记录首次错误、STOP请求/确认、最后已受理start的时间；已受理事务不能撤销。同步AXI卡住时确认应报告UNKNOWN，保留全部在途buffer；不得用spin_lock_irqsave把可能挂起的AXI访问包住并宣称可取消。每IP timeout/poll预算不能撤销总线挂起，每级看到STOP都不启动下游。stage开始前在内核持久化frame/slot/generation/timestamp，而非等用户态成功回执才留证。native返回错误需保留原始receipt并raise，不能继续提交下一模块或下一帧。

未知DMA时保留allocation/mapping/module/device引用，独立非阻塞quarantine先于worker join；process exit/fdclose不能释放在途地址。fops.owner随file/VMA生命周期，file-backed mmap可在fdclose后继续持有file引用，但最终munmap/进程退出后的未知DMA仍需独立DMA-session引用；不能把这种暂时持有当永久quarantine，也不能使用自动teardown的DMA分配来承诺保留。

Linux v5.15的platform core会忽略remove回调非零返回，并继续detach电源域，故remove返回EBUSY不等于阻止解绑。suppress_bind_attrs仅关闭普通sysfs入口；还需受控静态DT、禁止overlay removal/force unload/suspend/PL重配，以及符合实际DMA/SMMU/电源域生命周期的实现。仅留下内存不证明IOMMU或电源域仍有效。同一core在driver probe之前还会应用DT clock defaults和attach电源域，装载/绑定也可能产生硬件影响。[v5.15 platform core](https://raw.githubusercontent.com/torvalds/linux/v5.15/drivers/base/platform.c)。

## 真正的driver build仍未完成

当前交付没有经过实际Kbuild验证的资源驱动。候选headers的fixdep/modpost是Linux AArch64 ELF；不能直接在Windows/MSYS2执行。已取得build材料不等于完整Kbuild；手工gcc生成kernel.o不能证明modpost、import CRC、vermagic或模块加载。此次没有生成或安装假装可用的ko，没有启动VM/WSL或安装替代系统。

已知标准构建入口是允许使用的Linux ARM64 build host、两份精确headers、匹配GCC11.4/binutils2.38、真实外部模块Kbuild；普通x86 Linux cross build需相应可运行的host tools，不能照搬包内ARM64工具。候选headers身份已审计，但不作为现场匹配证明，也不在此次包中再分发；仍需实际driver/UAPI/binding源、完整构建和signature/lockdown审核。[官方Kbuild说明](https://docs.kernel.org/kbuild/modules.html)。

现有 `Backend.compute/abort_new_starts/quarantine/final_audit` 仍是未实现接口；native helper补prepare/verify实际内存操作，没有补出完整DMA驱动。因此不得直接在板运行，也不能据Host DLL速度或mock计数宣告30FPS。这些未完成项交由lzm牵头软件集成，硬件端提供拓扑/身份材料与支持。后续双方共同验收30 FPS，无需重跑S1或S2预实验。

## 验证与交接边界

实际执行：官方小包离线身份/FIT byte-match审计、native Host DLL及Linux AArch64共享库编译、真实Host RAM和独立S1数据SHA/全量比较测试、源代码审阅与包身份核查。完整日志/receipt在忽略的outputs。旧ring的7项Host测试是上一轮结果，未冒称新增板测。

未执行：真实kernel driver Kbuild/modpost、目标ELF/ko加载、Linux/板端时钟运行、DDR/CSR/IP操作、持续FPS、相机链。BOARD_30FPS仍NOT_TESTED；原S1 PASS作为已有基线。

原候选与历史包保持原SHA，仅作本地追溯，旧go不进入推荐执行流程。当前共享入口为[START_HERE](kv260_v12_START_HERE.md)，本地大文件以[独立清单](kv260_v12_large_artifacts.md)安排渠道；本次不自动外发。
