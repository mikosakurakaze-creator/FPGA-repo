# Isolated four-core resource check. Only create/generate/synthesize; no implementation.
if {$argc != 2} {error {Expected isolated build directory and create|synth stage}}
set root [file normalize [lindex $argv 0]]
set stage [lindex $argv 1]
set_param general.maxThreads 2
set_param logicopt.enableDSPCascadeFixing false
set project [file join $root project joint_resource.xpr]
if {$stage eq {create}} {
    if {[file exists $project]} {error {Refusing to overwrite project}}
    create_project joint_resource [file join $root project] -part xck26-sfvc784-2LV-c
    set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
    set repos {}
    foreach name {cnn bilinear curve compact_d} {lappend repos [file join $root ip $name]}
    set_property ip_repo_paths $repos [current_project]
    config_ip_cache -disable_cache
    update_ip_catalog -rebuild
    set bd_dir [file join $root project joint_resource.srcs sources_1 bd system]
    file mkdir $bd_dir
    set bd_file [file join $bd_dir system.bd]
    file copy [file join $root lowlight_seed.bd] $bd_file
    add_files -norecurse $bd_file
    open_bd_design $bd_file
    # Preserve the complete frozen 100-MHz lowlight BD. Add a 200-MHz PS clock
    # and CDC-aware SmartConnect ports for the frozen Compact D core.
    set ps [get_bd_cells zynq_ultra_ps_e_0]
    set_property -dict [list CONFIG.PSU__FPGA_PL1_ENABLE {1} \
        CONFIG.PSU__CRL_APB__PL1_REF_CTRL__FREQMHZ {200}] $ps
    create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps_d
    set_property CONFIG.C_EXT_RESET_HIGH {0} [get_bd_cells rst_ps_d]
    connect_bd_net [get_bd_pins const_locked/dout] [get_bd_pins rst_ps_d/dcm_locked]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] [get_bd_pins rst_ps_d/ext_reset_in]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk1] [get_bd_pins rst_ps_d/slowest_sync_clk]
    create_bd_cell -type ip -vlnv xilinx.com:hls:compact_d_top:1.0 compact_d_top_0
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk1] [get_bd_pins compact_d_top_0/ap_clk]
    connect_bd_net [get_bd_pins rst_ps_d/peripheral_aresetn] [get_bd_pins compact_d_top_0/ap_rst_n]
    set_property -dict [list CONFIG.NUM_MI {4} CONFIG.NUM_CLKS {2}] [get_bd_cells axi_control]
    set_property -dict [list CONFIG.NUM_SI {4} CONFIG.NUM_CLKS {2}] [get_bd_cells cnn_data_sc]
    set_property -dict [list CONFIG.NUM_SI {4} CONFIG.NUM_CLKS {2}] [get_bd_cells curve_ddr_sc]
    foreach name {axi_control cnn_data_sc curve_ddr_sc} {
        connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk1] [get_bd_pins $name/aclk1]
    }
    connect_bd_intf_net [get_bd_intf_pins axi_control/M03_AXI] [get_bd_intf_pins compact_d_top_0/s_axi_control]
    connect_bd_intf_net [get_bd_intf_pins compact_d_top_0/m_axi_gmem_in] [get_bd_intf_pins cnn_data_sc/S03_AXI]
    connect_bd_intf_net [get_bd_intf_pins compact_d_top_0/m_axi_gmem_out] [get_bd_intf_pins curve_ddr_sc/S03_AXI]
    assign_bd_address -offset 0xA0050000 -range 64K -target_address_space \
        [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs compact_d_top_0/s_axi_control/Reg]
    foreach master {gmem_in gmem_out} gp {2 5} hp {0 3} {
        assign_bd_address -offset 0 -range 2G -target_address_space \
            [get_bd_addr_spaces compact_d_top_0/Data_m_axi_$master] \
            [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP$gp/HP${hp}_DDR_LOW]
    }
    validate_bd_design
    foreach name {zero_dce_cnn_top_0 bilinear_fixed16_buffered_0 curve_image_fixed16_0 compact_d_top_0} {
        if {[llength [get_bd_cells $name]] != 1} {error "Missing core $name"}
    }
    save_bd_design
    write_bd_tcl -force [file join $root reports joint_system_recreate.tcl]
    report_ip_status -file [file join $root reports ip_status.rpt]
    generate_target all [get_files $bd_file]
    set wrapper [make_wrapper -files [get_files $bd_file] -top]
    add_files -norecurse $wrapper
    set_property top system_wrapper [current_fileset]
    update_compile_order -fileset sources_1
} elseif {$stage eq {synth}} {
    open_project $project
    launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {[get_property PROGRESS [get_runs synth_1]] ne {100%} ||
        [string first {Complete} [get_property STATUS [get_runs synth_1]]] < 0} {error {Joint synthesis failed}}
    open_run synth_1
    report_utilization -file [file join $root reports joint_utilization.rpt]
    report_utilization -hierarchical -hierarchical_min_primitive_count 0 \
        -file [file join $root reports joint_utilization_hierarchical.rpt]
    report_timing_summary -delay_type min_max -file [file join $root reports joint_synthesis_timing.rpt]
    report_clocks -file [file join $root reports joint_clocks.rpt]
    report_drc -file [file join $root reports joint_synthesis_drc.rpt]
    foreach name {zero_dce_cnn_top_0 bilinear_fixed16_buffered_0 curve_image_fixed16_0 compact_d_top_0} {
        set core [get_cells -hierarchical -filter "NAME =~ */$name"]
        if {[llength $core] != 1} {error "Core hierarchy missing or ambiguous after synthesis: $name"}
        report_utilization -cells $core -file [file join $root reports core_${name}_utilization.rpt]
    }
    set boxes [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]
    if {[llength $boxes]} {error "Unresolved black boxes: $boxes"}
    write_checkpoint -force [file join $root joint_synth.dcp]
    puts {JOINT_FOUR_CORE_SYNTHESIS_PASS}
} else {error {Unknown stage}}
close_project
exit
