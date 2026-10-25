if {$argc != 2} {error {Expected build directory and stage}}
set root [file normalize [lindex $argv 0]]
set stage [lindex $argv 1]
set_param general.maxThreads 4
set_param logicopt.enableDSPCascadeFixing false
if {$stage eq {create}} {
    create_project compact_d_system [file join $root project] -part xck26-sfvc784-2LV-c
    set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
    set_property ip_repo_paths [list [file join $root ip compact_d]] [current_project]
    config_ip_cache -disable_cache
    update_ip_catalog -rebuild
    create_bd_design system
    create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 zynq_ultra_ps_e_0
    source [file join $root ps_config.tcl]
    # Reuse the actual K26 PS/DDR configuration. This is a separate D image;
    # old source projects and released images are never changed.
    set ps [get_bd_cells zynq_ultra_ps_e_0]
    set_property -dict [list CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {200} \
        CONFIG.PSU__FPGA_PL1_ENABLE {0} CONFIG.PSU__USE__S_AXI_GP3 {0} \
        CONFIG.PSU__USE__S_AXI_GP4 {0}] $ps
    create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps_d
    set_property CONFIG.C_EXT_RESET_HIGH {0} [get_bd_cells rst_ps_d]
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_locked
    set_property CONFIG.CONST_VAL {1} [get_bd_cells const_locked]
    connect_bd_net [get_bd_pins const_locked/dout] [get_bd_pins rst_ps_d/dcm_locked]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] [get_bd_pins rst_ps_d/ext_reset_in]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins rst_ps_d/slowest_sync_clk] [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihp0_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihp3_fpd_aclk]
    create_bd_cell -type ip -vlnv xilinx.com:hls:compact_d_top:1.0 compact_d_top_0
    foreach name {d_control d_input d_output} {
        create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 $name
        set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells $name]
        connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins $name/aclk]
        connect_bd_net [get_bd_pins rst_ps_d/peripheral_aresetn] [get_bd_pins $name/aresetn]
    }
    connect_bd_intf_net [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM0_FPD] [get_bd_intf_pins d_control/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins d_control/M00_AXI] [get_bd_intf_pins compact_d_top_0/s_axi_control]
    connect_bd_intf_net [get_bd_intf_pins compact_d_top_0/m_axi_gmem_in] [get_bd_intf_pins d_input/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins d_input/M00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP0_FPD]
    connect_bd_intf_net [get_bd_intf_pins compact_d_top_0/m_axi_gmem_out] [get_bd_intf_pins d_output/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins d_output/M00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP3_FPD]
    connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins compact_d_top_0/ap_clk]
    connect_bd_net [get_bd_pins rst_ps_d/peripheral_aresetn] [get_bd_pins compact_d_top_0/ap_rst_n]
    assign_bd_address -offset 0xA0050000 -range 64K -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs compact_d_top_0/s_axi_control/Reg]
    foreach master {gmem_in gmem_out} gp {2 5} hp {0 3} {
        assign_bd_address -offset 0 -range 2G -target_address_space [get_bd_addr_spaces compact_d_top_0/Data_m_axi_$master] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP$gp/HP${hp}_DDR_LOW]
    }
    validate_bd_design
    save_bd_design
    set bd_file [get_files */system.bd]
    write_bd_tcl -force [file join $root system_recreate.tcl]
    generate_target all [get_files $bd_file]
    set wrapper [make_wrapper -files [get_files $bd_file] -top]
    add_files -norecurse $wrapper
    set_property top system_wrapper [current_fileset]
    update_compile_order -fileset sources_1
    write_hw_platform -fixed -force -file [file join $root compact_d_preimpl.xsa]
} else {
    if {$stage eq {synth}} {
        open_project [file join $root project compact_d_system.xpr]
        launch_runs synth_1 -jobs 4
        wait_on_run synth_1
        if {[get_property PROGRESS [get_runs synth_1]] ne {100%}} {error {Synthesis failed}}
        open_run synth_1
        report_utilization -file [file join $root synthesis_utilization.rpt]
        report_timing_summary -file [file join $root synthesis_timing.rpt]
        write_checkpoint -force [file join $root system_synth.dcp]
    } elseif {$stage eq {impl}} {
        open_checkpoint [file join $root system_synth.dcp]
        # Preserve signed boundaries while implementing in the current process.
        set_param logicopt.enableDSPCascadeFixing false
        opt_design
        place_design -directive Explore
        phys_opt_design
        route_design -directive Explore
        report_utilization -file [file join $root routed_utilization.rpt]
        report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $root routed_timing.rpt]
        report_route_status -file [file join $root route_status.rpt]
        report_drc -file [file join $root routed_drc.rpt]
        write_checkpoint -force [file join $root system_routed.dcp]
        foreach type {max min} {
            set path [get_timing_paths -delay_type $type -max_paths 1]
            if {[llength $path] == 0 || [get_property SLACK $path] < 0} {error "Routed timing failed: $type"}
        }
    } elseif {$stage eq {verify_impl}} {
        open_checkpoint [file join $root system_routed.dcp]
        report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $root verified_timing.rpt]
        report_route_status -file [file join $root verified_route_status.rpt]
        foreach type {max min} {
            set path [get_timing_paths -delay_type $type -max_paths 1]
            if {[llength $path] == 0 || [get_property SLACK $path] < 0} {error "Routed timing failed: $type"}
        }
    } elseif {$stage eq {export}} {
        open_checkpoint [file join $root system_routed.dcp]
        foreach type {max min} {
            set path [get_timing_paths -delay_type $type -max_paths 1]
            if {[llength $path] == 0 || [get_property SLACK $path] < 0} {error "Routed timing failed: $type"}
        }
        write_bitstream -force [file join $root compact_d_system.bit]
        write_hw_platform -fixed -include_bit -force -file [file join $root compact_d_system.xsa]
    } else {error "Unknown stage: $stage"}
}
puts "D_SYSTEM_[string toupper $stage]_PASS"
exit
