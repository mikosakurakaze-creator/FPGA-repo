# Connect the three validated HLS cores in the isolated V1.1 block design.
# Run after vivado_three_module_v1_1_create.tcl.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_1]
set project_file [file join $project_dir three_module_integration_v1_1.xpr]
set bd_file [file join $project_dir three_module_integration_v1_1.srcs sources_1 bd system system.bd]
if {![file isfile $project_file] || ![file isfile $bd_file]} {
    error {Missing isolated V1.1 project or saved BD}
}
cd $project_dir
open_project $project_file
open_bd_design $bd_file
foreach cell {
    zynq_ultra_ps_e_0 zero_dce_cnn_top_0 bilinear_fixed16_buffered_0
    curve_image_fixed16_0 axi_control cnn_data_sc cnn_model_sc
    bilinear_ddr_sc curve_ddr_sc rst_ps_100m
} {
    if {[llength [get_bd_cells $cell]] != 1} {error "Missing stage-create cell: $cell"}
}

# AXI4-Lite control: one PS master, three independent HLS slaves.
connect_bd_intf_net [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM0_FPD] \
    [get_bd_intf_pins axi_control/S00_AXI]
foreach {mi target} {
    0 zero_dce_cnn_top_0/s_axi_control
    1 bilinear_fixed16_buffered_0/s_axi_control
    2 curve_image_fixed16_0/s_axi_control
} {
    connect_bd_intf_net [get_bd_intf_pins [format {axi_control/M%02d_AXI} $mi]] \
        [get_bd_intf_pins $target]
    puts "CONTROL_MASTER=axi_control/M0${mi}_AXI -> $target"
}

# Four PS HP ports. Ordering inside each SmartConnect is frozen here.
set groups {
    {cnn_data_sc S_AXI_HP0_FPD {
        zero_dce_cnn_top_0/m_axi_gmem_input
        zero_dce_cnn_top_0/m_axi_gmem_output
        zero_dce_cnn_top_0/m_axi_gmem_workspace}}
    {cnn_model_sc S_AXI_HP1_FPD {
        zero_dce_cnn_top_0/m_axi_gmem8
        zero_dce_cnn_top_0/m_axi_gmem32
        zero_dce_cnn_top_0/m_axi_gmem_lut}}
    {bilinear_ddr_sc S_AXI_HP2_FPD {
        bilinear_fixed16_buffered_0/m_axi_gmem_input
        bilinear_fixed16_buffered_0/m_axi_gmem_output}}
    {curve_ddr_sc S_AXI_HP3_FPD {
        curve_image_fixed16_0/m_axi_gmem_input
        curve_image_fixed16_0/m_axi_gmem_parameter
        curve_image_fixed16_0/m_axi_gmem_output}}
}
set ddr_masters {}
foreach group $groups {
    lassign $group sc hp masters
    if {[get_property CONFIG.NUM_SI [get_bd_cells $sc]] != [llength $masters]} {
        error "SmartConnect SI count mismatch: $sc"
    }
    for {set i 0} {$i < [llength $masters]} {incr i} {
        set master [lindex $masters $i]
        if {[llength [get_bd_intf_pins $master]] != 1} {
            error "Missing HLS AXI master: $master"
        }
        set sink [format {%s/S%02d_AXI} $sc $i]
        connect_bd_intf_net [get_bd_intf_pins $master] [get_bd_intf_pins $sink]
        lappend ddr_masters $master
        puts "DDR_MASTER=$master -> $sink"
    }
    connect_bd_intf_net [get_bd_intf_pins $sc/M00_AXI] \
        [get_bd_intf_pins zynq_ultra_ps_e_0/$hp]
    puts "DDR_HP=$sc/M00_AXI -> zynq_ultra_ps_e_0/$hp"
}
if {[llength $ddr_masters] != 11} {error {Incorrect number of DDR masters}}

assign_bd_address
puts {INITIAL_ADDRESS_MAP_BEGIN}
foreach space [get_bd_addr_spaces] {
    puts "ADDRESS_SPACE=$space"
    foreach seg [get_bd_addr_segs -of_objects $space] {
        puts "  SEGMENT=$seg OFFSET=[get_property OFFSET $seg] RANGE=[get_property RANGE $seg]"
    }
}
puts {INITIAL_ADDRESS_MAP_END}
save_bd_design
puts {STAGE2=PASS AXI topology connected and initial addresses assigned}
close_project
exit
