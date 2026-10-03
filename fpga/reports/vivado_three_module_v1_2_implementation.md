# KV260 三模块 V1.2 Phase 5：Implementation 与 post-route 审计

日期：2026-10-03（Asia/Shanghai）。结论：**POST_ROUTE_100MHZ_PASS**。正式Phase4G write-credit CNN工程自然完成implementation与route，100MHz setup/hold/pulse均满足，DRC无Error/Critical Warning。BOARD_30FPS=**NOT_TESTED**。本批未生成bitstream/XSA，没有运行新system TB或板测。

## 1. 固定工程、自然完成与保护

正式delivery identity=`a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9`；ABI保持不变。权威历史：Phase4E/4G CNN单帧3,301,639 cycles、raw mismatch=0；Phase4F SHORT_MULTI_FRAME_30FPS_PASS，max steady interval=3,307,317 cycles。本批保留原证据，没有重新运行这些仿真。

| 项目 | 实际值 |
| --- | --- |
| 工程 | E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.xpr |
| Vivado | 2025.2 |
| Formal CNN revision | 2114810448 |
| Formal package | e:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05/component.xml |
| Synthesis / writer hierarchy / BD Validate | PASS / PASS / PASS |
| Strategy / flow | Vivado Implementation Defaults / Vivado Implementation 2025 |
| Run status / progress | route_design Complete! / 100% |
| Vivado batch exit | 0 |
| 自然退出 / 强制终止 | True / False |
| 开始 / 结束 | 2026-10-03T12:19:33.995120+08:00 / 2026-10-03T12:40:41.704569+08:00 |
| Implementation等待时长 | 984秒 |
| Routed checkpoint | E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.runs/impl_1/system_wrapper_routed.dcp |
| Launch stop step | route_design |
| Phys-opt原始 / 最终enabled | 1 / 1 |

| 阶段 | 默认directive | 自然end marker | error marker | 日志完成 |
| --- | --- | --- | --- | --- |
| opt_design | Default | True | False | True |
| place_design | Default | True | False | True |
| phys_opt_design | Default | True | False | True |
| route_design | Default | True | False | True |

阶段工具实报：

| 阶段 | Result | elapsed秒 | peak MB | 累计 Error / Critical / Warning |
| --- | --- | --- | --- | --- |
| opt_design | PASS | 90.0 | 3927.504 | 0 / 0 / 0 |
| place_design | PASS | 341.0 | 4693.035 | 0 / 0 / 0 |
| phys_opt_design | PASS | 20.0 | 4693.035 | 0 / 0 / 0 |
| route_design | PASS | 224.0 | 5465.945 | 0 / 0 / 0 |

同一run的阶段日志计数为累计值，不能将四行相加。

所有阶段为默认/既定策略。没有手工aggressive directive、RTL修补或重试性能优化。只有自然route完成、100%与routed DCP/end marker确认后才进入post-route timing gate。

输入与旧证据保护：**PASS**，原有15687项hash未变；project configuration/source sets、Git branch/HEAD/staged状态保持，.bit/.xsa为零。

初始严格逐字保护审计为FAIL，Python执行器因此exit=1；Vivado batch已自然exit=0。变化仅为11个自动生成的synthesis `gen_run.xml`运行索引，mtime在implementation launch，原synthesis LaunchTime、run identity、device、strategy和源引用保持合法。原始FAIL保存在[protection_after_initial.json](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/protection_after_initial.json)。

修正后的保护审计明确区分15,687个未变文件与11个索引变化：所有被引用的设计源、source sets、配置、综合Tcl/log/end marker/DCP及旧证据逐字未变；每个索引的原/新SHA与逐项判定见[generated_metadata_audit.json](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/generated_metadata_audit.json)。原索引只有before SHA，未备份before XML字节，不能宣称逐字段old/new XML相等；该例外依据未变输入/综合输出和当前XML语义、刷新时间作窄范围审计，不是放宽RTL或证据保护。

补充保护：**PASS**（[supplement_protection.json](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/supplement_protection.json)）。报告生成前再次执行完整正式/稳定IP文件树只读审计，PASS。未修改CNN/Bilinear/Curve、PS、SmartConnect、HP/HPM、100MHz clock/reset、address map或fixed-point协议。

## 2. Routing完整性

| 指标 | 实际值 |
| --- | --- |
| Total logical nets | 233332 |
| 无需routing | 155044 |
| Internally routed | 135137 |
| No loads | 19907 |
| Total routable nets | 78288 |
| Fully routed | 78288 |
| Routing errors | 0 |
| Failed nets | 0 |
| Unrouted | 0 |
| Partially routed | 0 |
| Node overlaps | 0 |
| Router Completed Successfully | True |

最终route complete，unrouted=0、partially routed=0、routing errors=0；router中间未布通计数不当作最终状态。

## 3. 100MHz post-route timing gate

| 100 MHz post-route指标 | 实际值 | 失败 / 总端点 | Gate |
| --- | --- | --- | --- |
| Setup WNS / TNS (ns) | +0.636 / 0.000 | 0 / 170914 | PASS |
| Hold WHS / THS (ns) | +0.010 / 0.000 | 0 / 170914 | PASS |
| Pulse WPWS / TPWS (ns) | +3.500 / 0.000 | 0 / 54198 | PASS |

时钟period=10.000ns；Vivado最终timing clean=True。以上均来自routed报告，不以synthesis估计替代。

| 指标 | V1.1 routed | V1.2 Phase4G post-synthesis | V1.2 routed |
| --- | --- | --- | --- |
| WNS_ns | 1.72 | 2.613 | 0.636 |
| TNS_ns | 0.0 | 0.0 | 0.0 |
| setup_failing_endpoints | 0 | 0 | 0 |
| WHS_ns | 0.01 | -0.093 | 0.01 |
| THS_ns | 0.0 | -1863.689 | 0.0 |
| hold_failing_endpoints | 0 | 58257 | 0 |
| WPWS_ns | 3.5 | 3.5 | 3.5 |
| TPWS_ns | 0.0 | 0.0 | 0.0 |
| pulse_failing_endpoints | 0 | 0 | 0 |

Phase4G pre-route hold WHS=-0.093ns/THS=-1863.689ns是历史综合估计；最终hold结论只采用本次routed实报。

### Worst setup path

| 字段 | 实际post-route值 |
| --- | --- |
| Startpoint | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/point_inputs_5_U/gen_buffer[1].zero_dce_cnn_top_p_anonymous_namespace_group_rowstream_block_point_inputs_RAM_2P_BRAM_1R1W_memcore_U/ram_reg_bram_0/CLKBWRCLK` |
| Endpoint | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/p_anonymous_namespace_point_tile_compute_actor_U0/grp_p_anonymous_namespace_compute_point_tile30313233343536373839404142434445464748495_2_fu_550/grp_p_anonymous_namespace_compute_point_tile30313233343536373839404142434445464748495_1_fu_857/partial_3_reg_4630_reg[25]/D` |
| Launch / capture clock | clk_pl_0 / clk_pl_0 |
| Clock / path group | clk_pl_0 |
| Path type | Setup (Max at Slow Process Corner) |
| Requirement / slack (ns) | 10.000 / +0.636 |
| Data / logic / route delay (ns) | 8.865 / 4.940 / 3.925 |
| Logic levels | 15 |
| Start hierarchy | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/point_inputs_5_U/gen_buffer[1].zero_dce_cnn_top_p_anonymous_namespace_group_rowstream_block_point_inputs_RAM_2P_BRAM_1R1W_memcore_U` |
| End hierarchy | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/p_anonymous_namespace_point_tile_compute_actor_U0/grp_p_anonymous_namespace_compute_point_tile30313233343536373839404142434445464748495_2_fu_550/grp_p_anonymous_namespace_compute_point_tile30313233343536373839404142434445464748495_1_fu_857` |
| Hierarchy分类 | CNN |

### Worst hold path

| 字段 | 实际post-route值 |
| --- | --- |
| Startpoint | `system_i/bilinear_ddr_sc/inst/s01_nodes/s01_w_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst/gen_rd_b.gen_rd_b_synth_template.gen_rf_narrow_reg.doutb_reg_reg[91]/C` |
| Endpoint | `system_i/bilinear_ddr_sc/inst/switchboards/w_switchboard/inst/gen_mi[0].inst_opipe_payld/gen_pipe[1].pipe_reg[1][91]/D` |
| Launch / capture clock | clk_pl_0 / clk_pl_0 |
| Clock / path group | clk_pl_0 |
| Path type | Hold (Min at Slow Process Corner) |
| Requirement / slack (ns) | 0.000 / +0.010 |
| Data / logic / route delay (ns) | 0.248 / 0.112 / 0.136 |
| Logic levels | 0 |
| Start hierarchy | `system_i/bilinear_ddr_sc/inst/s01_nodes/s01_w_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst` |
| End hierarchy | `system_i/bilinear_ddr_sc/inst/switchboards/w_switchboard/inst/gen_mi[0].inst_opipe_payld` |
| Hierarchy分类 | SmartConnect |

最差setup分类为**CNN**，最差hold分类为**SmartConnect**；依据实际startpoint/endpoint归属判断，没有先假定CNN是最差路径。

## 4. Routed资源与writer审计

| 资源 | V1.1 routed | Phase4G post-synth | V1.2 routed | Δ vs synth | Δ vs V1.1 |
| --- | --- | --- | --- | --- | --- |
| LUT | 27045 | 40993 | 37864 | -3129 | +10819 |
| FF | 39451 | 47653 | 45326 | -2327 | +5875 |
| RAMB36 | 24 | 29 | 29 | 0 | +5 |
| RAMB18 | 10 | 72 | 72 | 0 | +62 |
| BRAM_tiles | 29.0 | 65.0 | 65.0 | 0 | +36 |
| URAM | 0 | 18 | 18 | 0 | +18 |
| DSP | 76 | 146 | 146 | 0 | +70 |

BRAM tile=RAMB36+RAMB18/2；BRAM18 equivalent=130。URAM=**18**，相对正式Phase4G的18颗状态为PASS。

| Writer inclusive subtree | Synth LUT / FF | Routed LUT / FF | Δ LUT / FF | Routed BRAM / URAM / DSP |
| --- | --- | --- | --- | --- |
| zero_dce_cnn_top_row_axi_writer | 78 / 103 | 77 / 103 | -1 / 0 | 0.0 / 0 / 0 |
| zero_dce_cnn_top_row_axi_writer_2 | 85 / 103 | 84 / 103 | -1 / 0 | 0.0 / 0 / 0 |
| zero_dce_cnn_top_p_anonymous_namespace_output_writer | 216 / 461 | 210 / 461 | -6 / 0 | 0.0 / 0 / 2 |

output_writer父层级包含两个row writer子层级，三行不能相加；这些是完整writer subtree资源，不能当作overlay新增资源。

实际whole-system和writer资源对照未发现审计规则识别的异常膨胀。

层级资源补充实报：

| Hierarchy | LUT | FF | BRAM tiles | URAM | DSP |
| --- | --- | --- | --- | --- | --- |
| system_wrapper | 37864 | 45326 | 65.0 | 18 | 146 |
| axi_control | 942 | 996 | 0.0 | 0 | 0 |
| bilinear_ddr_sc | 2178 | 4157 | 0.0 | 0 | 0 |
| bilinear_fixed16_buffered_0 | 3938 | 4912 | 1.5 | 0 | 33 |
| cnn_data_sc | 3711 | 6250 | 0.0 | 0 | 0 |
| cnn_model_sc | 2267 | 3760 | 0.0 | 0 | 0 |
| curve_ddr_sc | 2794 | 5046 | 0.0 | 0 | 0 |
| curve_image_fixed16_0 | 2899 | 4641 | 1.0 | 0 | 24 |
| rst_ps_100m | 17 | 38 | 0.0 | 0 | 0 |
| zero_dce_cnn_top_0 | 19124 | 15526 | 62.5 | 18 | 89 |

| Hierarchy | V1.1 routed LUT / FF | Phase4G synth LUT / FF | V1.2 routed LUT / FF |
| --- | --- | --- | --- |
| system_wrapper | 27045 / 39451 | 40993 / 47653 | 37864 / 45326 |
| axi_control | 946 / 996 | 1042 / 1096 | 942 / 996 |
| bilinear_ddr_sc | 2184 / 4157 | 2439 / 4588 | 2178 / 4157 |
| bilinear_fixed16_buffered_0 | 3937 / 4912 | 4173 / 4912 | 3938 / 4912 |
| cnn_data_sc | 3721 / 6250 | 4159 / 6970 | 3711 / 6250 |
| cnn_model_sc | 2264 / 3760 | 2514 / 4231 | 2267 / 3760 |
| curve_ddr_sc | 2791 / 5046 | 3141 / 5647 | 2794 / 5046 |
| curve_image_fixed16_0 | 2900 / 4641 | 3207 / 4641 | 2899 / 4641 |
| rst_ps_100m | 17 / 38 | 19 / 40 | 17 / 38 |
| zero_dce_cnn_top_0 | 8295 / 9651 | 20035 / 15528 | 19124 / 15526 |

V1.1与V1.2是不同CNN实现，资源差值只表示实际版本/实现成本，不能全部归因于三writer overlay；也不能由资源表推算DDR吞吐或板上FPS。

## 5. Post-route DRC与constraint检查

Errors=**0**；Critical Warnings=**0**；Warnings=**198**。

| Rule | Severity | 数量 | Vivado描述 | 分析 |
| --- | --- | --- | --- | --- |
| DPIP-2 | Warning | 78 | Input pipelining | DSP输入缺少相应流水级的性能建议。以本次实际post-route timing判断收敛；本批不修改HLS/RTL。 |
| DPOP-3 | Warning | 70 | PREG Output pipelining | DSP PREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |
| DPOP-4 | Warning | 49 | MREG Output pipelining | DSP MREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |
| RTSTAT-10 | Warning | 1 | No routable loads | 无可路由负载的net提示；与最终unrouted=0、routing errors=0分别审计。复位管道或优化后无负载的net不是未布通net；后续板级reset/AXI行为尚未验证。 |

独立解析器已逐条核对全部诊断与summary数量。完整原文见[postroute_drc.rpt](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_drc.rpt)，逐项结构化记录见[implementation_gate.json](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/implementation_gate.json)。普通DSP建议按规则及对象模块分类；Error/Critical与RTSTAT逐条展开。Warning保留原Severity。

### DPIP-2 — 78条

| 对象模块 | 条数 | 代表对象（全量见原报告） | 分析 |
| --- | --- | --- | --- |
| bilinear_fixed16_buffered_0 | 11 | `system_i/bilinear_fixed16_buffered_0/inst/grp_bilinear_fixed16_buffered_Pipeline_VITIS_LOOP_82_5_fu_354/mul_33ns_16s_49_1_1_U15/tmp_product` | DSP输入缺少相应流水级的性能建议。以本次实际post-route timing判断收敛；本批不修改HLS/RTL。 |
| curve_image_fixed16_0 | 16 | `system_i/curve_image_fixed16_0/inst/mul_32s_16s_48_1_1_U1/tmp_product` | DSP输入缺少相应流水级的性能建议。以本次实际post-route timing判断收敛；本批不修改HLS/RTL。 |
| zero_dce_cnn_top_0 | 51 | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/p_anonymous_namespace_depth_band_actor_U0/grp_p_anonymous_namespace_compute_depth_tile296264707274_fu_511/grp_p_anonymous_namespace_compute_depth_tile296264707274_Pipeline_VITIS_LOOP_183_4_VI_fu_872/accumulator_10_fu_6348_p2` | DSP输入缺少相应流水级的性能建议。以本次实际post-route timing判断收敛；本批不修改HLS/RTL。 |

### DPOP-3 — 70条

| 对象模块 | 条数 | 代表对象（全量见原报告） | 分析 |
| --- | --- | --- | --- |
| bilinear_fixed16_buffered_0 | 29 | `system_i/bilinear_fixed16_buffered_0/inst/grp_bilinear_fixed16_buffered_Pipeline_VITIS_LOOP_82_5_fu_354/mul_33ns_16s_49_1_1_U15/tmp_product` | DSP PREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |
| curve_image_fixed16_0 | 8 | `system_i/curve_image_fixed16_0/inst/mul_32s_16s_48_1_1_U1/tmp_product__0` | DSP PREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |
| zero_dce_cnn_top_0 | 33 | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/p_anonymous_namespace_point_tile_compute_actor_U0/grp_p_anonymous_namespace_compute_point_tile30313233343536373839404142434445464748495_2_fu_550/grp_p_anonymous_namespace_compute_point_tile30313233343536373839404142434445464748495_1_fu_857/mul_16s_8s_24_1_1_U693/tmp_product` | DSP PREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |

### DPOP-4 — 49条

| 对象模块 | 条数 | 代表对象（全量见原报告） | 分析 |
| --- | --- | --- | --- |
| bilinear_fixed16_buffered_0 | 33 | `system_i/bilinear_fixed16_buffered_0/inst/grp_bilinear_fixed16_buffered_Pipeline_VITIS_LOOP_82_5_fu_354/mul_33ns_16s_49_1_1_U15/tmp_product` | DSP MREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |
| curve_image_fixed16_0 | 8 | `system_i/curve_image_fixed16_0/inst/mul_32s_16s_48_1_1_U1/tmp_product__0` | DSP MREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |
| zero_dce_cnn_top_0 | 8 | `system_i/zero_dce_cnn_top_0/inst/grp_p_anonymous_namespace_group_rowstream_block_fu_420/p_anonymous_namespace_depth_band_actor_U0/grp_p_anonymous_namespace_compute_depth_tile296264707274_fu_511/grp_p_anonymous_namespace_compute_depth_tile296264707274_Pipeline_VITIS_LOOP_183_4_VI_fu_872/mac_muladd_16s_8s_24s_25_4_1_U408/zero_dce_cnn_top_mac_muladd_16s_8s_24s_25_4_1_DSP48_0_U/p_reg_reg` | DSP MREG输出流水级建议。保留现有算法和时序结构，不因该Warning自动优化。 |

### RTSTAT-10 — 1条

**RTSTAT-10#1**：无可路由负载的net提示；与最终unrouted=0、routing errors=0分别审计。复位管道或优化后无负载的net不是未布通net；后续板级reset/AXI行为尚未验证。

> No routable loads  
> 20 net(s) have no routable loads. The problem bus(es) and/or net(s) are system_i/axi_control/inst/m00_nodes/m00_aw_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m00_nodes/m00_b_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m00_nodes/m00_r_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m00_nodes/m00_w_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m01_nodes/m01_ar_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m01_nodes/m01_aw_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m01_nodes/m01_w_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m02_nodes/m02_aw_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m02_nodes/m02_b_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m02_nodes/m02_r_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/m02_nodes/m02_w_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/s00_nodes/s00_ar_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/s00_nodes/s00_aw_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/s00_nodes/s00_b_node/inst/mi_handler_m_sc_areset_pipe,
> system_i/axi_control/inst/s00_nodes/s00_r_node/inst/mi_handler_m_sc_areset_pipe
>  (the first 15 of 20 listed nets/buses).
> Related violations: <none>


check_timing实际记录：

| 检查 | 实际数量 |
| --- | --- |
| no_clock | 0 |
| constant_clock | 0 |
| pulse_width_clock | 0 |
| unconstrained_internal_endpoints | 0 |
| no_input_delay | 0 |
| no_output_delay | 0 |
| multiple_clock | 0 |
| generated_clocks | 0 |
| loops | 0 |
| partial_input_delay | 0 |
| partial_output_delay | 0 |
| latch_loops | 0 |

Implementation run中的Warning/Error原行（与DRC条目分开计数）：

无Warning/Error行。

报告命令兼容性提示：Vivado batch另有**2条Critical Warning [Vivado 12-1569]**，均因`report_timing -nets`参数已弃用。工具明确说明默认已显示net；独立审计成功解析20条详细路径，worst setup/hold slack与global summary精确一致，数据完整可信。这两条是报告API提示，implementation run与post-route DRC的Critical Warning均为0；原日志完整保留，没有将提示隐藏或改计Severity。

当前执行脚本已删除-nets供以后使用，本次未重跑implementation或重导报告。实际执行版本见[implementation_script_executed.tcl](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/implementation_script_executed.tcl)。


无可路由负载的reset管道net与routing error分别判断。本批物理布线不能证明PS软件、板级reset时序、AXI实际事务、DDR吞吐或30 FPS已经通过。

## 6. 最终gate、状态与NEXT STEP

| Gate | 结果 |
| --- | --- |
| implementation | PASS |
| route_complete | PASS |
| clock_100MHz | PASS |
| setup | PASS |
| hold | PASS |
| pulse_width | PASS |
| drc_no_error_critical | PASS |
| timing_constraints_complete | PASS |
| expected_URAM_18 | PASS |
| implementation_log_no_error_critical | PASS |
| report_commands_no_unexplained_error_critical | PASS |

| 总状态 | 结果 |
| --- | --- |
| CNN_RTL_30FPS | PASS |
| SHORT_MULTI_FRAME_30FPS | PASS |
| IMPLEMENTABLE_CNN_IP | PASS |
| POST_ROUTE_100MHZ | PASS |
| BOARD_30FPS | NOT_TESTED |

**POST_ROUTE_100MHZ_PASS**。仅代表该正式工程在当前约束下的100MHz物理实现/时序/DRC结果；不自动标记HW_READY，BOARD_30FPS仍为NOT_TESTED。

NEXT STEP — **WAIT MASTER**：本批完成后立即停止。下一批单独授权后才可做bitstream、XSA和hardware handoff；板测仍需明确安排。本批不自动生成bitstream、导出XSA或进行板测。

## 7. 文件变更、验证与Git review

| 新增 / 修改文件 | 原因与关键差异 |
| --- | --- |
| [fpga/scripts/vivado_three_module_v1_2_impl.tcl](E:/github/-/fpga/scripts/vivado_three_module_v1_2_impl.tcl) | 复用正式Phase4G工程，核对revision/BD/综合源，默认implementation止于route，生成routed实报；采集后移除已弃用-nets参数，实际执行版本另行归档 |
| [fpga/perf/v1_2_phase5/run_implementation.py](E:/github/-/fpga/perf/v1_2_phase5/run_implementation.py) | 保护输入/旧证据、记录自然exit与禁止导出边界；严格审计launcher刷新生成的11个run索引并保留初始FAIL，不生成IP或启动system TB |
| [fpga/perf/v1_2_phase5/analyze_implementation.py](E:/github/-/fpga/perf/v1_2_phase5/analyze_implementation.py) | 独立严格解析实际路由/时序/DRC/资源；缺失字段拒绝产生完整gate |
| [fpga/perf/v1_2_phase5/finalize_reports.py](E:/github/-/fpga/perf/v1_2_phase5/finalize_reports.py) | 完整gate、证据SHA与保护PASS后写报告/checkpoint，保留权威历史并明确停止 |
| [fpga/reports/vivado_three_module_v1_2_implementation.md](E:/github/-/fpga/reports/vivado_three_module_v1_2_implementation.md) | 记录Phase5真实结果、worst paths、资源和V1.1对照及下一批边界 |
| [fpga/reports/v1_2_phase4_checkpoint.md](E:/github/-/fpga/reports/v1_2_phase4_checkpoint.md) | 更新当前post-route状态，同时保留Phase4E/4F/4G正式identity与cycles历史 |

实际执行验证：正式输入/源与旧证据hash、BD/clock/reset/address预检、现有synth状态与三writer hierarchy、完整opt/place/phys_opt/route自然完成、routed setup/hold/pulse、route status、DRC、整体与writer资源对照、check_timing、完整IP文件树及最终证据SHA核对。

Vivado 2025.2的-nets参数兼容性修正是在本次报告采集后进行，未重新执行Vivado；原执行脚本与两条提示完整归档，独立解析已核对路径完整性和global slack一致性。

未执行：新CNN IP构建、新HLS、任何新system TB、性能优化、RTL timing修补、bitstream、XSA、hardware handoff、PS软件/DDR实际吞吐/30 FPS板测、git add/commit/push/PR。

建议 Commit Message：`docs(fpga): record V1.2 post-route timing and implementation audit`。

当前 branch=`codex/curve-fp32-baseline`，HEAD=`660010bfea9f43c99623ee2ba99662292783a02e`；tracked diff=empty；staged diff=empty。工作区未暂存文件/既有untracked保留，当前untracked 304项；完整现场见[git_review.json](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/git_review.json)。没有创建/切换分支或执行Git写操作。外部IP、log、DCP、备份和运行输出留在E:/HLS，不自动上传。

证据索引：[implementation gate](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/implementation_gate.json)；[natural exit](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/exit_status.json)；[run status](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/run_status.tsv)；[timing](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_timing_summary.rpt)；[setup paths](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_setup_paths.rpt)；[hold paths](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_hold_paths.rpt)；[utilization](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_utilization.rpt)；[route status](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_route_status.rpt)；[DRC](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/reports/postroute_drc.rpt)；[protection](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/protection_after.json)；[原Phase4G checkpoint备份](E:/HLS/kv260_three_module_v1_2_phase4/phase5/implementation_01/checkpoint_before.md)。
