# Implement the existing KV260 three-module V1.1 project through route_design.
# Reuse completed synthesis and never launch write_bitstream or export hardware.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_1]
set project_file [file join $project_dir three_module_integration_v1_1.xpr]
set bd_file [file join $project_dir three_module_integration_v1_1.srcs sources_1 bd system system.bd]
set dcp_file [file join $project_dir three_module_integration_v1_1.runs synth_1 system_wrapper.dcp]
set report_dir {E:/HLS/vivado_three_module_v1_1_implementation}
file mkdir $report_dir
foreach path [list $project_file $bd_file $dcp_file] {
    if {![file exists $path]} {error "Required synthesized V1.1 file is missing: $path"}
}

cd $project_dir
open_project $project_file
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c} ||
    [get_property BOARD_PART [current_project]] ne {xilinx.com:kv260_som:part0:1.4}} {
    error {Unexpected board or device; implementation will not start}
}
set top [get_property TOP [get_filesets sources_1]]
if {$top ne {system_wrapper}} {error "Unexpected synthesis top: $top"}
set synth [get_runs synth_1]
set synth_status [get_property STATUS $synth]
set synth_progress [get_property PROGRESS $synth]
puts "SYNTH_STATUS=$synth_status PROGRESS=$synth_progress"
if {$synth_status ne {synth_design Complete!} || $synth_progress ne {100%}} {
    error {The saved full-system synthesis is incomplete; not launching implementation}
}
puts "SYNTH_DCP=$dcp_file"

open_bd_design $bd_file
foreach {name vlnv} {
    zero_dce_cnn_top_0 xilinx.com:hls:zero_dce_cnn_top:1.0
    bilinear_fixed16_buffered_0 xilinx.com:hls:bilinear_fixed16_buffered:1.0
    curve_image_fixed16_0 xilinx.com:hls:curve_image_fixed16:1.0
} {
    set cell [get_bd_cells $name]
    if {[llength $cell] != 1 || [get_property VLNV $cell] ne $vlnv} {
        error "Unexpected HLS IP at $name"
    }
}
set ps [get_bd_cells zynq_ultra_ps_e_0]
if {[get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $ps] ne {100} ||
    [get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]] ne {0}} {
    error {Clock or reset configuration differs from the routed baseline}
}
set clock_net [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_clk0]]
foreach pin {
    zero_dce_cnn_top_0/ap_clk bilinear_fixed16_buffered_0/ap_clk
    curve_image_fixed16_0/ap_clk axi_control/aclk cnn_data_sc/aclk
    cnn_model_sc/aclk bilinear_ddr_sc/aclk curve_ddr_sc/aclk
    zynq_ultra_ps_e_0/maxihpm0_fpd_aclk
    zynq_ultra_ps_e_0/saxihp0_fpd_aclk
    zynq_ultra_ps_e_0/saxihp1_fpd_aclk
    zynq_ultra_ps_e_0/saxihp2_fpd_aclk
    zynq_ultra_ps_e_0/saxihp3_fpd_aclk
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $clock_net} {
        error "Unexpected clock net at $pin"
    }
}
if {[get_bd_nets -of_objects [get_bd_pins rst_ps_100m/ext_reset_in]] ne
    [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0]]} {
    error {PS reset is disconnected}
}
set peripheral_reset [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/peripheral_aresetn]]
foreach pin {
    zero_dce_cnn_top_0/ap_rst_n
    bilinear_fixed16_buffered_0/ap_rst_n
    curve_image_fixed16_0/ap_rst_n
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $peripheral_reset} {
        error "HLS reset disconnected: $pin"
    }
}
set interconnect_reset [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/interconnect_aresetn]]
foreach pin {
    axi_control/aresetn cnn_data_sc/aresetn cnn_model_sc/aresetn
    bilinear_ddr_sc/aresetn curve_ddr_sc/aresetn
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $interconnect_reset} {
        error "SmartConnect reset disconnected: $pin"
    }
}
puts "PREFLIGHT_BD_CLOCK_RESET=PASS CLOCK_NET=$clock_net"

set impl [get_runs impl_1]
puts "IMPL_STRATEGY=[get_property STRATEGY $impl]"
puts "IMPL_FLOW=[get_property FLOW $impl]"
set existing_status [get_property STATUS $impl]
set existing_progress [get_property PROGRESS $impl]
puts "IMPL_PREVIOUS_STATUS=$existing_status PROGRESS=$existing_progress"
if {$existing_status eq {route_design Complete!} && $existing_progress eq {100%}} {
    puts {IMPL_ALREADY_ROUTED=1}
} else {
    puts "IMPL_START_EPOCH=[clock seconds]"
    puts {IMPL_LAUNCH_TO_STEP=route_design}
    launch_runs impl_1 -to_step route_design -jobs 4
    wait_on_run impl_1
    puts "IMPL_DONE_EPOCH=[clock seconds]"
}
set status [get_property STATUS $impl]
set progress [get_property PROGRESS $impl]
puts "IMPL_STATUS=$status"
puts "IMPL_PROGRESS=$progress"
if {$status ne {route_design Complete!} || $progress ne {100%}} {
    error "Implementation did not finish routing: $status ($progress)"
}
set routed_dcp [file join $project_dir three_module_integration_v1_1.runs impl_1 system_wrapper_routed.dcp]
if {![file exists $routed_dcp]} {error "Missing routed checkpoint: $routed_dcp"}
puts "ROUTED_DCP=$routed_dcp"

open_run impl_1
puts "OPEN_RUN_DESIGN=[current_design]"
report_clocks -file [file join $report_dir postroute_clocks.rpt]
report_clock_interaction -file [file join $report_dir postroute_clock_interaction.rpt]
report_exceptions -summary -file [file join $report_dir postroute_timing_exceptions.rpt]
report_route_status -file [file join $report_dir postroute_route_status.rpt]
report_utilization -file [file join $report_dir postroute_utilization.rpt]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 \
    -file [file join $report_dir postroute_utilization_hierarchical.rpt]
report_timing_summary -file [file join $report_dir postroute_timing_summary.rpt]
report_timing -delay_type max -max_paths 10 \
    -file [file join $report_dir postroute_setup_paths.rpt]
report_timing -delay_type min -max_paths 10 \
    -file [file join $report_dir postroute_hold_paths.rpt]
check_timing -verbose -file [file join $report_dir postroute_check_timing.rpt]
report_drc -file [file join $report_dir postroute_drc.rpt]
puts {POSTROUTE_AUDIT=PASS}
close_project
exit
