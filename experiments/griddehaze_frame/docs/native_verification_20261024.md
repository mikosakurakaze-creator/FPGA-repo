# GridDehazeNet 主机整图验证记录

日期：2026-10-24（本机 Windows）

本次在 `weather_fpga_integration/experiments/griddehaze_frame` 的副本中，以当前冻结 INT16 bundle `5ff57bb52cff87944261aa1fc68ae556a08a65f1c3d32de702ac47a2bda13710` 编译了整图 C++ testbench，并实际运行新生成的 `test_frame.exe`。

## 结果

- 8 组 case 均完成全部 320 个图节点，最终输出通过。
- 对 8×320 个逐节点原始输出逐字节对照既有 Golden，2,560/2,560 一致；8 组最终输出也全部相同。
- 11 项错误描述符负向检查通过。
- 进程打印 `ALL_FRAME_CASES_PASS cases=8 negative_tests=11`，退出码为 0。
- 实际运行的 EXE SHA-256：`a229361c2682c652c34d7dae7055bd86f768097f118165666c59205491bded3b`。
- 冻结包内 INT16、INT8 的 manifest、参数、图定义及 320 节点结构预检均通过。此检查只验证包和地址规划，没有执行推理。

testbench 源码静态检查未发现进程启动、网络、注册表写入、动态库加载或删除文件调用。它从 case 清单读取本地输入/参数/Golden，并将输出写到清单指定前缀。

## 运行限制和证据范围

首次从新工作目录直接启动 EXE 时，Windows 返回 `WinError 5`，因此该次没有执行推理。随后使用项目现有的 `run_windows_desktop.py` 启动同一 EXE，实际运行通过。没有修改 Defender、策略、注册表或安全设置。

该结果是主机 C++ 整图验证，使用 A 组冻结 Golden；不证明 HLS C/RTL、导出 RTL、post-route 电路、真板 DDR/DMA、CMA 分配、帧率或 HDMI。逐节点输出留在本机 `D:\weather_builds\grid_native_retry02`，不纳入本次项目文件；校验摘要也见 `native_verification_20261024.json`。

同日的 33×47 RTL 全图仿真由较早启动的 harness 继续运行中；它不满足新增的源码快照和 DDR fixture 身份门禁，不能替代后续新 harness 跨 tile 回归。最终 bit/XSA 导出仍需等各项门禁完成。

