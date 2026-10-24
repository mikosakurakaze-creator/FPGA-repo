# 保留旧核、新增去雾核：本轮变更与验证

用户已明确最终系统保留旧 weather 核，另加 GridDehazeNet 去雾核。本轮落实范围文档，并补齐新核所需的逐元素 HLS 算子。旧仓库和旧发布物未修改。

## 修改与原因

| 文件 | 原因及关键差异 |
|---|---|
| hls/elementwise_top.hpp、elementwise_top.cpp（新增） | 新核内部算子：ReLU、系数乘法、加法、拼接；输入和输出为INT16、48位中间运算、256标量片上分块、逐节点RHAZ与饱和；先查形状/尺度/长度再读数据 |
| hls/tb_elementwise.cpp（新增） | 对照208个真实Golden节点，另覆盖全部特征尺度组合、负数half tie、提前饱和负对照、拼接顺序、块尾、输入保护和非法长度 |
| tools/elementwise_trial.py（新增） | 冻结执行源与fixture身份，运行主机或真实Vitis C仿真/综合，校验实际raw和完整PASS标记；日志ERROR即失败 |
| src/host_graph.cpp | 可将全部逐元素节点交给新增HLS源码执行，原独立CPU实现仍用于参考路径 |
| tools/verify_cpp.py | 增加--elementwise，可与--tile组合验证全部算子源码在整图中的实际输出 |
| tools/collect_review.py | 可收集本轮小报告、原始日志、实际CSR和RTL总线宽度；权重、图片和运行raw仍不收进评审目录 |
| docs/integration_scope_20261024.md（新增） | 固定用户选择；保留旧接口、增设新核；记录真实旧BD接法、资源依据与剩余门禁 |
| README、interface_proposal、b_reply、verification | 区分范围已确定、算子已综合、整网尚未实现，补充真实新增算子接口与后续验证 |

## 实际执行

| 检查 | 结果与证据 |
|---|---|
| 新算子主机原生执行 | 全208个Golden节点、6,921组边界通过；work/elementwise_native02 |
| 新算子Vitis C仿真 | 真正使用ap_int<48>，同208节点和6,921组边界通过；work/elementwise_hls02/csim.log和实际raw |
| 新算子HLS综合/IP导出 | 通过，生成RTL和IP；LUT11,419、FF5,899、BRAM18K7、DSP13、URAM0，周期估算7.300ns，动态延迟undef |
| 全部算子原生整图 | --tile --elementwise；8组小图每组320节点与最终raw一致，输入不变、guard通过；work/operators02 |
| 固定数学基础 | 独立130项边界检查通过，编译启用-Wall -Wextra -Werror |
| 新算子实际RTL接口 | read_mem/write_mem均数据32位、地址64位；控制数据32位、地址8位；以生成RTL和驱动头为依据 |
| 旧系统依据 | 只读核对e8662ce发布的BD脚本、routed资源和时序；原工作区保持干净 |

完整算子主机执行使用INT64替代ap_int，PL图调度器还未实现；不能称为整网48位HLS/RTL验证。两组大图的独立CPU结果仍属于首次评审，本轮没有用新增算子重跑大图。

初版elementwise_native01/hls01/operators01均通过，综合DSP为24。随后将负shift的二次幂缩放改成非负幅值移位再恢复符号，避免通用变量乘法；重跑同样的完整检查和HLS综合，DSP降至13，LUT由11,092增至11,419，FF由5,668增至5,899。旧证据在review03，新证据在review04，不覆盖原始报告。

## 未执行与主要限制

- 没有新增核RTL co-sim、综合后/实现后数值回归，HLS时钟属于估算。
- 没有最终PL图调度器、整图ABI和model/version guard、AXI错误/写排空、设备专用复位实现。
- 没有把两类算子作为完成的整网设备连接到PS；当前两个top属于内部算子原型。
- 没有新整机综合、布局布线、bit/XSA/BIN或板测，也没有验证450MiB scratch实际分配。
- 保留旧系统后资源余量较紧，实际旧LUT63.22%、DSP77%；粗略叠加两类新核LUT约87.82%，仍需容纳调度/互连并重新收敛时序。
- 本轮没有改变A的参数、Golden、数值合同，也没有改Zero-DCE++网络。

## 审核与Git状态

新工作仍位于 `C:/Users/wzh16/Desktop/competing/griddehaze_fpga`，没有独立Git绑定；本轮没有执行add/commit/push或新建/切换分支。旧仓库 `C:/Users/wzh16/Desktop/github clone/weather_fpga_integration` 在weather_fpga_integration、HEAD e8662ce，工作区干净。

建议Commit Message：`feat(griddehaze): preserve legacy cores and add exact elementwise HLS engine`。

本轮只提交文件供审核，Git操作等待用户明确授权；遵循上级AGENTS.md的“随后停止，等待用户审核”。
