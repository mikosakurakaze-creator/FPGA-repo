# Reopen and synthesize the existing KV260 three-module V1.2 project.
# Deliberately does not create a project or launch implementation.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_2]
set project_file [file join $project_dir three_module_integration_v1_2.xpr]
set bd_file [file join $project_dir three_module_integration_v1_2.srcs sources_1 bd system system.bd]
set report_dir {E:/HLS/kv260_three_module_v1_2_phase4/synthesis}
file mkdir $report_dir
if {![file exists $project_file] || ![file exists $bd_file]} {
    error {The saved V1.2 project or system.bd is missing}
}

cd $project_dir
open_project $project_file
open_bd_design $bd_file
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c}} {
    error "Unexpected device: [get_property PART [current_project]]"
}
foreach {name vlnv} {
    zero_dce_cnn_top_0 xilinx.com:hls:zero_dce_cnn_top:1.0
    bilinear_fixed16_buffered_0 xilinx.com:hls:bilinear_fixed16_buffered:1.0
    curve_image_fixed16_0 xilinx.com:hls:curve_image_fixed16:1.0
} {
    set cell [get_bd_cells $name]
    if {[llength $cell] != 1 || [get_property VLNV $cell] ne $vlnv} {
        error "Missing or wrong BD IP: $name ($vlnv)"
    }
    if {[llength [get_ipdefs -all $vlnv]] != 1} {
        error "Missing or ambiguous catalog IP: $vlnv"
    }
    puts "PREFLIGHT_IP=$name VLNV=$vlnv"
}
foreach name {
    zynq_ultra_ps_e_0 rst_ps_100m axi_control cnn_data_sc cnn_model_sc
    bilinear_ddr_sc curve_ddr_sc
} {
    if {[llength [get_bd_cells $name]] != 1} {error "Missing BD cell: $name"}
}
foreach {name si mi} {
    axi_control 1 3
    cnn_data_sc 3 1
    cnn_model_sc 3 1
    bilinear_ddr_sc 2 1
    curve_ddr_sc 3 1
} {
    set cell [get_bd_cells $name]
    if {[get_property CONFIG.NUM_SI $cell] != $si ||
        [get_property CONFIG.NUM_MI $cell] != $mi} {
        error "Unexpected SmartConnect topology: $name"
    }
}
set ps [get_bd_cells zynq_ultra_ps_e_0]
foreach {key expected} {
    PSU__USE__M_AXI_GP0 1
    PSU__USE__M_AXI_GP1 0
    PSU__USE__S_AXI_GP2 1
    PSU__USE__S_AXI_GP3 1
    PSU__USE__S_AXI_GP4 1
    PSU__USE__S_AXI_GP5 1
    PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ 100
} {
    if {[get_property CONFIG.$key $ps] ne $expected} {
        error "Unexpected PS setting $key"
    }
}
set expected_control {
    SEG_bilinear_fixed16_buffered_0_Reg 0xA0000000
    SEG_curve_image_fixed16_0_Reg 0xA0010000
    SEG_zero_dce_cnn_top_0_Reg 0xA0020000
}
foreach {seg_name expected_offset} $expected_control {
    set seg [get_bd_addr_segs zynq_ultra_ps_e_0/Data/$seg_name]
    if {[llength $seg] != 1 ||
        [expr {[get_property OFFSET $seg] != $expected_offset ||
               [get_property RANGE $seg] != 0x10000}]} {
        error "Unexpected AXI-Lite address: $seg_name"
    }
}
set ddr_masters {
    zero_dce_cnn_top_0/m_axi_gmem_input
    zero_dce_cnn_top_0/m_axi_gmem_output
    zero_dce_cnn_top_0/m_axi_gmem_workspace
    zero_dce_cnn_top_0/m_axi_gmem8
    zero_dce_cnn_top_0/m_axi_gmem32
    zero_dce_cnn_top_0/m_axi_gmem_lut
    bilinear_fixed16_buffered_0/m_axi_gmem_input
    bilinear_fixed16_buffered_0/m_axi_gmem_output
    curve_image_fixed16_0/m_axi_gmem_input
    curve_image_fixed16_0/m_axi_gmem_parameter
    curve_image_fixed16_0/m_axi_gmem_output
}
if {[llength $ddr_masters] != 11} {error {Expected 11 HLS DDR masters}}
foreach master $ddr_masters {
    set space_name [string map {m_axi_ Data_m_axi_} $master]
    set space [get_bd_addr_spaces $space_name]
    if {[llength $space] != 1} {error "Missing address space $space_name"}
    set low 0
    set high 0
    foreach seg [get_bd_addr_segs -of_objects $space] {
        set offset [get_property OFFSET $seg]
        if {$offset eq {}} {continue}
        if {[regexp {DDR_LOW$} $seg]} {incr low}
        if {[regexp {DDR_HIGH$} $seg]} {incr high}
        if {[regexp -nocase {QSPI|OCM} $seg]} {
            error "Non-DDR address is mapped: $seg"
        }
    }
    if {$low != 1 || $high != 1} {
        error "Missing DDR LOW/HIGH aperture: $space_name"
    }
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
    rst_ps_100m/slowest_sync_clk
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $clock_net} {
        error "Unexpected clock domain at $pin"
    }
}
if {[get_bd_nets -of_objects [get_bd_pins rst_ps_100m/ext_reset_in]] ne
    [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0]]} {
    error {PS reset is not connected to Processor System Reset}
}
puts {PREFLIGHT_TOPOLOGY=PASS}
puts {VALIDATE_START}
validate_bd_design
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]] ne {0} ||
    [get_property CONFIG.POLARITY [get_bd_pins rst_ps_100m/ext_reset_in]] ne {ACTIVE_LOW}} {
    error {Processor System Reset polarity is not active low}
}
puts {VALIDATE=PASS}

set bd [get_files $bd_file]
report_ip_status -file [file join $report_dir ip_status_before_generation.rpt]
puts "GENERATE_START_EPOCH=[clock seconds]"
generate_target all $bd
puts "GENERATE_DONE_EPOCH=[clock seconds]"
report_ip_status -file [file join $report_dir ip_status_after_generation.rpt]
puts {OUTPUT_PRODUCTS=PASS}

set wrappers [get_files -all *system_wrapper.v]
if {[llength $wrappers] == 0} {
    set wrapper [make_wrapper -top -add $bd]
} elseif {[llength $wrappers] == 1} {
    set wrapper $wrappers
} else {
    error "Ambiguous wrapper files: $wrappers"
}
puts "WRAPPER_PATH=$wrapper"
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
if {[get_property TOP [get_filesets sources_1]] ne {system_wrapper}} {
    error {The synthesis top is not system_wrapper}
}
puts {WRAPPER=PASS}

set run [get_runs synth_1]
set existing_status [get_property STATUS $run]
set existing_progress [get_property PROGRESS $run]
if {[string first {Complete} $existing_status] >= 0 &&
    $existing_progress eq {100%}} {
    puts "SYNTH_ALREADY_COMPLETE=$existing_status"
} else {
    puts "SYNTH_START_EPOCH=[clock seconds]"
    launch_runs synth_1 -jobs 4
    wait_on_run synth_1
    puts "SYNTH_DONE_EPOCH=[clock seconds]"
}
set status [get_property STATUS $run]
set progress [get_property PROGRESS $run]
puts "SYNTH_STATUS=$status"
puts "SYNTH_PROGRESS=$progress"
if {[string first {Complete} $status] < 0 || $progress ne {100%}} {
    error "Full synthesis did not complete: $status ($progress)"
}
puts {SYNTH=PASS}

open_run synth_1
puts "OPEN_RUN_DESIGN=[current_design]"
foreach clk [get_clocks] {
    puts "CLOCK=$clk PERIOD_NS=[get_property PERIOD $clk]"
}
report_clocks -file [file join $report_dir system_clocks.rpt]
report_exceptions -summary -file [file join $report_dir system_timing_exceptions.rpt]
report_utilization -file [file join $report_dir system_utilization.rpt]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 \
    -file [file join $report_dir system_utilization_hierarchical.rpt]
report_timing_summary -file [file join $report_dir system_timing_summary.rpt]
report_timing -delay_type max -max_paths 10 \
    -file [file join $report_dir system_setup_paths.rpt]
report_timing -delay_type min -max_paths 10 \
    -file [file join $report_dir system_hold_paths.rpt]
report_clock_interaction -file [file join $report_dir system_clock_interaction.rpt]
check_timing -verbose -file [file join $report_dir system_check_timing.rpt]
report_drc -file [file join $report_dir system_drc.rpt]
puts {POST_SYNTHESIS_REPORTS=PASS}
close_project
exit
