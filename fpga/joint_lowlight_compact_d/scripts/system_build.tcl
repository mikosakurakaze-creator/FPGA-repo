# Six-core integration, using the locked four-core reconstruction verbatim.
if {$argc != 3} {error {Expected build directory, stage and exact project path}}
set root [file normalize [lindex $argv 0]]
set stage [lindex $argv 1]
set reports [file join $root reports]
set project [file normalize [lindex $argv 2]]
set_param general.maxThreads 2
set_param logicopt.enableDSPCascadeFixing false

# These hard-PS peripheral clock outputs exist in PS8 even when no PL logic or
# package port consumes them. Record exact leaf fanout; do not create clocks,
# false paths, waivers, or suppress the raw check_timing report.
proc audit_unused_ps_clocks {reports tag} {
    check_timing -verbose -file [file join $reports ${tag}_clock_check.rpt]
    set f [open [file join $reports ${tag}_unused_ps_clocks.txt] w]
    foreach name {EMIOENET0MDIOMDC EMIOENET1MDIOMDC EMIOENET2MDIOMDC EMIOENET3MDIOMDC EMIOSDIO0CLKOUT EMIOSDIO1CLKOUT EMIOSPI0SCLKO EMIOSPI1SCLKO} {
        set pin [get_pins -quiet system_i/zynq_ultra_ps_e_0/inst/PS8_i/$name]
        if {[llength $pin] != 1} {error "Missing expected PS pin $name"}
        set cell [get_cells -of_objects $pin]
        if {[get_property REF_NAME $cell] ne {PS8} || [get_property DIRECTION $pin] ne {OUT}} {error {Unexpected pin identity}}
        set nets [get_nets -quiet -segments -of_objects $pin]
        set loads [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == IN}]
        set ports [get_ports -quiet -of_objects $nets]
        set clocks [get_clocks -quiet -of_objects $pin]
        puts $f "PIN $pin REF=PS8 DIR=OUT INPUT_LOADS=[llength $loads] TOP_PORTS=[llength $ports] CLOCKS=[llength $clocks] NETS=$nets"
        if {[llength $loads] || [llength $ports] || [llength $clocks]} {error "PS output is not an unused unclocked leaf: $name"}
    }
    puts $f {CHECKED_UNUSED_PS_OUTPUTS=8}
    close $f
}

proc route_step_ready {} {
    set run [get_runs impl_1]
    set status [get_property STATUS $run]
    set directory [get_property DIRECTORY $run]
    if {[get_property NEEDS_REFRESH $run]} {return 0}
    # With the post-route strategy Vivado advances STATUS to the next,
    # unstarted step immediately after a successful route_design.
    set status_ok [expr {[string first {route_design Complete} $status] >= 0 ||
        $status eq {Not started phys_opt_design (Post-Route)}}]
    return [expr {$status_ok && [file exists [file join $directory .route_design.end.rst]] &&
        ![file exists [file join $directory .route_design.error.rst]] &&
        [file exists [file join $directory system_wrapper_routed.dcp]]}]
}

if {$stage eq {create}} {
    create_project joint_system [file dirname $project] -part xck26-sfvc784-2LV-c
    set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
    set repos {}
    foreach name {cnn bilinear curve compact_d fusion} {lappend repos [file join $root ip $name]}
    lappend repos [file join $root prepare hls impl ip]
    set_property ip_repo_paths $repos [current_project]
    config_ip_cache -disable_cache
    update_ip_catalog -rebuild
    source [file join $root four_core_seed.tcl]
    foreach name {zero_dce_cnn_top_0 bilinear_fixed16_buffered_0 curve_image_fixed16_0 compact_d_top_0} {
        if {[llength [get_bd_cells -quiet $name]] != 1} {error "Seed reconstruction failed: $name"}
    }
    create_bd_cell -type ip -vlnv xilinx.com:hls:joint_rgb8_prepare:1.0 joint_rgb8_prepare_0
    create_bd_cell -type ip -vlnv joint.local:rtl:joint_fusion:1.0 joint_fusion_0
    set_property CONFIG.SCALAR_COUNT {2747520} [get_bd_cells joint_fusion_0]
    foreach cell {joint_rgb8_prepare_0 joint_fusion_0} {
        connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins $cell/ap_clk]
        connect_bd_net [get_bd_pins rst_ps_100m/peripheral_aresetn] [get_bd_pins $cell/ap_rst_n]
    }
    set_property CONFIG.NUM_MI {6} [get_bd_cells axi_control]
    connect_bd_intf_net [get_bd_intf_pins axi_control/M04_AXI] [get_bd_intf_pins joint_rgb8_prepare_0/s_axi_control]
    connect_bd_intf_net [get_bd_intf_pins axi_control/M05_AXI] [get_bd_intf_pins joint_fusion_0/s_axi_control]

    # Arbitration remains on the original four independent HP ports. SmartConnect
    # explicitly retains both clocks on HP0/HP3/control for the 200-MHz D core.
    set_property CONFIG.NUM_SI {6} [get_bd_cells cnn_data_sc]
    set_property CONFIG.NUM_SI {3} [get_bd_cells bilinear_ddr_sc]
    set_property CONFIG.NUM_SI {6} [get_bd_cells curve_ddr_sc]
    foreach {master target gp hp} {
        joint_rgb8_prepare_0/m_axi_gmem_rgb cnn_data_sc/S04_AXI 2 0
        joint_rgb8_prepare_0/m_axi_gmem_cnn cnn_data_sc/S05_AXI 2 0
        joint_rgb8_prepare_0/m_axi_gmem_d bilinear_ddr_sc/S02_AXI 4 2
        joint_rgb8_prepare_0/m_axi_gmem_i curve_ddr_sc/S04_AXI 5 3
        joint_fusion_0/m_axi_gmem curve_ddr_sc/S05_AXI 5 3
    } {
        connect_bd_intf_net [get_bd_intf_pins $master] [get_bd_intf_pins $target]
        set space [get_bd_addr_spaces -of_objects [get_bd_intf_pins $master]]
        if {[llength $space] != 1} {error "Missing master address space: $master"}
        assign_bd_address -offset 0 -range 2G -target_address_space $space \
            [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP$gp/HP${hp}_DDR_LOW]
    }
    foreach {cell base} {joint_rgb8_prepare_0 0xA0030000 joint_fusion_0 0xA0040000} {
        assign_bd_address -offset $base -range 64K -target_address_space \
            [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs $cell/s_axi_control/Reg]
    }
    validate_bd_design
    foreach cell {rst_ps_100m rst_ps_d} {
        if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells $cell]] != 0} {error "Incorrect external reset polarity: $cell"}
    }
    save_bd_design
    write_bd_tcl -force [file join $reports six_core_recreate.tcl]
    report_ip_status -file [file join $reports ip_status.rpt]
    set audit [open [file join $reports address_clock_audit.txt] w]
    foreach space [get_bd_addr_spaces] {
        puts $audit "SPACE $space"
        foreach seg [get_bd_addr_segs -of_objects $space] {
            puts $audit "  $seg OFFSET=[get_property OFFSET $seg] RANGE=[get_property RANGE $seg]"
        }
    }
    foreach cell {zynq_ultra_ps_e_0 rst_ps_100m rst_ps_d axi_control cnn_data_sc curve_ddr_sc joint_fusion_0} {
        puts $audit "CELL $cell"
        foreach prop [list_property [get_bd_cells $cell]] {
            if {[regexp {CONFIG\.(NUM_CLKS|NUM_SI|NUM_MI|SCALAR_COUNT|C_EXT_RESET_HIGH|PSU__CRL_APB__PL[01]_REF_CTRL__.*FREQMHZ)} $prop]} {
                puts $audit "  $prop=[get_property $prop [get_bd_cells $cell]]"
            }
        }
    }
    close $audit
    set bd [get_files */system.bd]
    generate_target all $bd
    set wrapper [make_wrapper -files $bd -top]
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
    if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Unresolved black boxes}}
    report_utilization -file [file join $reports synthesis_utilization.rpt]
    report_utilization -hierarchical -file [file join $reports synthesis_hierarchical.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $reports synthesis_timing.rpt]
    report_clocks -file [file join $reports synthesis_clocks.rpt]
    report_drc -file [file join $reports synthesis_drc.rpt]
    write_checkpoint -force [file join $root joint_synth.dcp]
    close_design
} elseif {$stage eq {implement}} {
    open_project $project
    set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
    puts "IMPLEMENT_RUN_BEFORE STATUS=[get_property STATUS [get_runs impl_1]] PROGRESS=[get_property PROGRESS [get_runs impl_1]]"
    # A run stopped at route_design need not report 100% of the complete
    # implementation/bitstream flow. Require the actual route step to complete.
    report_property -all -file [file join $reports implementation_run_properties.rpt] [get_runs impl_1]
    if {![route_step_ready]} {
        launch_runs impl_1 -to_step route_design -jobs 2
        wait_on_run impl_1
    }
    puts "IMPLEMENT_RUN_AFTER STATUS=[get_property STATUS [get_runs impl_1]] PROGRESS=[get_property PROGRESS [get_runs impl_1]]"
    if {![route_step_ready]} {
        error "Joint route step failed: [get_property STATUS [get_runs impl_1]]"
    }
    if {[file exists [file join $root joint_routed.dcp]]} {error {Preserve existing routed candidate before another implementation attempt}}
    # A partial implementation run can refuse open_run while its next
    # post-route step is unstarted. Open its completed route checkpoint.
    open_checkpoint [file join [get_property DIRECTORY [get_runs impl_1]] system_wrapper_routed.dcp]
    # launch_runs accepts route_design; run the post-route optimization on the
    # opened routed design explicitly and bind reports/export to its new DCP.
    phys_opt_design -directive Explore
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $reports routed_timing.rpt]
    report_utilization -file [file join $reports routed_utilization.rpt]
    report_route_status -file [file join $reports route_status.rpt]
    report_drc -file [file join $reports routed_drc.rpt]
    report_cdc -details -file [file join $reports routed_cdc.rpt]
    report_clock_interaction -file [file join $reports routed_clock_interaction.rpt]
    write_checkpoint -force [file join $root joint_routed.dcp]
    # Independent export gate also reads these reports and checks route coverage.
    if {[llength [get_timing_paths -delay_type max -slack_lesser_than 0]] ||
        [llength [get_timing_paths -delay_type min -slack_lesser_than 0]]} {error {Negative routed setup/hold slack}}
    set bad [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]
    if {[llength $bad]} {error "Unresolved DRC violations: $bad"}
    close_design
} elseif {$stage eq {coverage}} {
    open_checkpoint [file join $root joint_routed.dcp]
    audit_unused_ps_clocks $reports routed
    report_bus_skew -file [file join $reports routed_bus_skew.rpt]
    close_design
} elseif {$stage eq {export}} {
    # The Python driver requires a fresh acceptance record bound to this exact
    # checkpoint/report/Golden identity before this stage can be invoked.
    open_checkpoint [file join $root joint_routed.dcp]
    audit_unused_ps_clocks $reports export
    report_bus_skew -file [file join $reports export_bus_skew.rpt]
    foreach type {max min} {
        set path [get_timing_paths -delay_type $type -max_paths 1]
        if {[llength $path] != 1 || [get_property SLACK $path] < 0} {error "Reopened routed timing failed: $type"}
    }
    if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Unresolved export black boxes}}
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $reports export_verified_timing.rpt]
    report_route_status -file [file join $reports export_verified_route.rpt]
    set export_dir [file join $root export]
    file mkdir $export_dir
    write_bitstream -force [file join $export_dir joint_system.bit]
    write_hw_platform -fixed -include_bit -force -file [file join $export_dir joint_system.xsa]
    close_design
} else {error {Unknown stage}}
puts "JOINT_SYSTEM_[string toupper $stage]_PASS"
if {[llength [get_projects -quiet]]} {close_project}
exit
