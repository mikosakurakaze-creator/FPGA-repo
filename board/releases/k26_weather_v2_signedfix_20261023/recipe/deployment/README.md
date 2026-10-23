# 可移植 PS 控制与分块适配

此目录提供可移植 C11 控制逻辑，已在主机 MMIO/DMA mock 上验证。另提供 A53 standalone MMIO/cache/timer 后端与测试源。缺少本机 A53 Embedded 编译工具，当前没有 ELF 或板测证据；Linux DMA 后端尚未实现。

| 文件 | 用途 |
|---|---|
| `weather_control.h/.c` | ABI v1/v2 参数校验、64 位地址配置、DMA 所有权、轮询、超时隔离和恢复 |
| `weather_tiled.c` | 现有 A 组 v1 IP 的 CPU gather → IP → core scatter 正确性路径 |
| `tests/test_weather_control.cpp` | 模拟 MMIO/DMA 并调用实际 C++ 核，检查状态机与拼图结果 |
| `tests/verify_driver.py` | C11/C++11 编译、严格警告和可复现报告 |

## 两种 ABI

`WEATHER_TILE_V1` 对应已交付的 `derain_top` 或 `dehaze_top`。初始化 `fixed_task=0/1`，每次 job 必须匹配这个物理 IP。三个独立 DMA buffer 为 input、output、scratch，尺寸不大于 140×140。每个最大 tile 分别需要 117,600、117,600、940,800 字节。output 在原核中也作为中间空间，方向为读写。

`WEATHER_FRAME_V2` 对应新的 `weather_frame_top` 原型；初始化 `fixed_task=-1`，job 中 task 选 0/1。只有整帧 input/output，scratch 的三个字段都置零。最大 720×1280。v2 寄存器已与当前生成 IP/BD 核对，系统基址为 `0xA0030000`。

## 平台需实现的回调

`read32/write32` 的偏移相对于该 IP 的控制基址；回调内部负责有序设备 MMIO，不能用普通内存指针代替。`barrier` 必须覆盖平台所需的内存和 MMIO 顺序。

`weather_buffer` 同时保存 CPU 映射地址、设备可访问的 DMA 地址、分配容量。虚拟地址不能直接当物理地址；设备地址也未必等于 CPU 物理地址。每个 buffer 应来自独立、DMA/cache-line 对齐、满足目标设备地址宽度的分配。通用层只检查 2 字节对齐、容量、地址溢出和范围重叠，不替代 IOMMU/物理连续性检查。

`sync` 接收本次活跃字节数、方向和目标所有者。它要使用对应平台的 DMA API 完成 CPU↔device 的所有权/缓存操作，包括只读输入的归还。成功返回 0；失败必须保持原所有权，不能部分完成后仍返回失败。不要手写一套可能与 Linux DMA API 冲突的 cache flush。

`now_us` 应单调递增；`poll` 可选，用于 yield。每次运行同时受微秒超时和最大轮询次数约束，时钟停止也不会无限循环。两者均由集成者按实测延迟配置。

`reset_and_quiesce` 可选，但恢复隔离必须提供。它返回成功前，必须证明 master 已停止且先前读写的在途 DDR 事务已排空。只拉一下 IP reset 不足以满足合同。

## 调用顺序

```c
struct weather_device device;
/* platform 和各 buffer 由板端后端提供；fresh device 只初始化一次。 */
int rc = weather_device_init(&device, &platform, WEATHER_TILE_V1, 0);
/* job={input,output,scratch,height,width,task}; 先准备 CPU-owned 输入。 */
uint32_t core_status = 0;
if (rc == WEATHER_OK)
    rc = weather_run(&device, &job, timeout_us, max_polls, &core_status);
```

`WEATHER_OK` 才表示本次输出有效且所有 buffer 已交回 CPU。`WEATHER_ECORE` 表示 IP 已完成但返回非零，输出不可用。`WEATHER_EINVAL/EBUSY` 拒绝启动；启动前的缓存/MMIO 故障尝试归还已取得的 buffer。

`WEATHER_ETIMEOUT` 或 `WEATHER_EQUARANTINED` 后，不要释放、CPU 读写或复用 device 仍持有的范围。对象记录 `owned_mask`；之后的提交会被拒绝。调用 `weather_recover`，仅当停止并排空设备访问、成功同步所有 buffer 后才允许复用。不能再次 init 来清除隔离状态。

代码要求单调用者独占 IP；没有内部线程锁，不能和另一线程、ISR、auto-restart 或另一套 MMIO 驱动同时操作该核。初次控制读取会消费旧 `ap_done`；不启用中断。

## 现有 v1 IP 的整帧调度

`weather_run_tiled` 接受 CPU-owned 连续 RGB NCHW 帧和预先分配的最大 tile workspace。core 只允许 64/128，halo 固定 6，整帧不大于 720×1280。它先验证帧/工作空间范围，并在每次 pack 前确认 IP 空闲，随后复制 tile、运行、复制有效 core。

`completed_tiles` 可区分部分完成；非零错误返回时整帧不可交给显示。超时上限按每个 tile 生效，没有隐含整帧 deadline。这是首次正确性联调路径，CPU memcpy 和缓存操作要单独测时，不能用作长期视频吞吐已达标的依据。

## 实际验证与板端待办

最新本地报告为 `../work/stream_driver01/verification.json`，已选择 `stream_frame` 真实新核。实际执行 C11 编译和 C++ 链接，均开启 `-Wall -Wextra -Werror`。测试覆盖高 32 位地址、旧 done、连续调用、ABI/task 混用、非法内存范围、busy/auto-restart、启动前回滚、不确定启动、超时/停止时钟、失败及成功的 reset/drain、CPU sync 失败；两任务 core64/128 的 145×149 拼图与整帧原型逐位相等。此报告是主机模拟控制器与真实 C++ 算术核验证，不是板端 MMIO/cache 测试。

板端仍需实现上述回调，确认 DMA/cache 合同、实际 CSR、DDR 路由、复位隔离和设备访问权限，再跑单 tile、单帧、多帧 Golden。采集/显示、颜色格式转换、模式策略和生产视频 DMA 不在当前控制模块内。
## A53 裸机集成补充

`weather_xilinx_standalone.c/.h` 为恒等映射、由链接器分配的低 DDR 提供 BSP MMIO、缓存和计时回调。`standalone/` 包含连续三帧 Golden/越界保护最小测试应用。该应用不负责配置 PL，也不负责系统复位或排空在途事务。当前构建证据和限制见 `../docs/stream_revision_20261020.md`。Linux DMA 仍需单独实现平台后端。
