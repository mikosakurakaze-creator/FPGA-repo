# Only BD/output products and actual synthesis. No implementation/route/export.
if {$argc != 1} {error {Expected one Phase 4G configuration Tcl path}}
source [lindex $argv 0]
set project_file [file join $project_dir ${project_name}.xpr]
set bd_file [file join $project_dir ${project_name}.srcs sources_1 bd system system.bd]
if {![file isfile $project_file] || ![file isfile $bd_file]} {error {Fresh Phase 4G project is missing}}
cd $project_dir
open_project $project_file
open_bd_design $bd_file
config_ip_cache -disable_cache
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c}} {error {Wrong device}}
set actual_repos [get_property IP_REPO_PATHS [current_project]]
if {[llength $actual_repos] != [llength $ip_repos]} {error {Unexpected repository search path}}
foreach actual $actual_repos expected $ip_repos {
    if {![string equal -nocase [file normalize $actual] [file normalize $expected]]} {
        error {Unexpected repository search path}
    }
}
foreach {name vlnv} {
    zero_dce_cnn_top_0 xilinx.com:hls:zero_dce_cnn_top:1.0
    bilinear_fixed16_buffered_0 xilinx.com:hls:bilinear_fixed16_buffered:1.0
    curve_image_fixed16_0 xilinx.com:hls:curve_image_fixed16:1.0
} {
    if {[get_property VLNV [get_bd_cells $name]] ne $vlnv} {error "Unexpected IP: $name"}
    if {[llength [get_ipdefs -all $vlnv]] != 1} {error "Ambiguous IP: $vlnv"}
}
foreach {name si mi} {axi_control 1 3 cnn_data_sc 3 1 cnn_model_sc 3 1 bilinear_ddr_sc 2 1 curve_ddr_sc 3 1} {
    set cell [get_bd_cells $name]
    if {[get_property CONFIG.NUM_SI $cell] != $si || [get_property CONFIG.NUM_MI $cell] != $mi} {
        error "Changed SmartConnect topology: $name"
    }
}
foreach {name expected} {
    SEG_bilinear_fixed16_buffered_0_Reg 0xA0000000
    SEG_curve_image_fixed16_0_Reg 0xA0010000
    SEG_zero_dce_cnn_top_0_Reg 0xA0020000
} {
    set seg [get_bd_addr_segs zynq_ultra_ps_e_0/Data/$name]
    if {[llength $seg] != 1 || [get_property OFFSET $seg] != $expected || [get_property RANGE $seg] != 0x10000} {
        error "Changed control address: $name"
    }
}
set ps [get_bd_cells zynq_ultra_ps_e_0]
foreach {key expected} {
    PSU__USE__M_AXI_GP0 1 PSU__USE__M_AXI_GP1 0
    PSU__USE__S_AXI_GP2 1 PSU__USE__S_AXI_GP3 1 PSU__USE__S_AXI_GP4 1 PSU__USE__S_AXI_GP5 1
    PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ 100
} {
    if {[get_property CONFIG.$key $ps] ne $expected} {error "Changed PS configuration: $key"}
}
set clock_net [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_clk0]]
foreach pin {
    zero_dce_cnn_top_0/ap_clk bilinear_fixed16_buffered_0/ap_clk curve_image_fixed16_0/ap_clk
    axi_control/aclk cnn_data_sc/aclk cnn_model_sc/aclk bilinear_ddr_sc/aclk curve_ddr_sc/aclk
    zynq_ultra_ps_e_0/maxihpm0_fpd_aclk zynq_ultra_ps_e_0/saxihp0_fpd_aclk
    zynq_ultra_ps_e_0/saxihp1_fpd_aclk zynq_ultra_ps_e_0/saxihp2_fpd_aclk
    zynq_ultra_ps_e_0/saxihp3_fpd_aclk rst_ps_100m/slowest_sync_clk
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $clock_net} {error "Changed clock: $pin"}
}
set masters {
    zero_dce_cnn_top_0/m_axi_gmem_input zero_dce_cnn_top_0/m_axi_gmem_output
    zero_dce_cnn_top_0/m_axi_gmem_workspace zero_dce_cnn_top_0/m_axi_gmem8
    zero_dce_cnn_top_0/m_axi_gmem32 zero_dce_cnn_top_0/m_axi_gmem_lut
    bilinear_fixed16_buffered_0/m_axi_gmem_input bilinear_fixed16_buffered_0/m_axi_gmem_output
    curve_image_fixed16_0/m_axi_gmem_input curve_image_fixed16_0/m_axi_gmem_parameter
    curve_image_fixed16_0/m_axi_gmem_output
}
foreach master $masters {
    set space [get_bd_addr_spaces [string map {m_axi_ Data_m_axi_} $master]]
    if {[llength $space] != 1} {error "Missing address space: $master"}
    set low 0
    set high 0
    foreach seg [get_bd_addr_segs -of_objects $space] {
        if {[get_property OFFSET $seg] eq {}} {continue}
        if {[regexp {DDR_LOW$} $seg]} {incr low}
        if {[regexp {DDR_HIGH$} $seg]} {incr high}
        if {[regexp -nocase {QSPI|OCM} $seg]} {error "Non-DDR mapping: $seg"}
    }
    if {$low != 1 || $high != 1} {error "DDR aperture differs: $master"}
}
puts {PHASE4G_TOPOLOGY=PASS}
validate_bd_design
save_bd_design
puts {PHASE4G_VALIDATE=PASS}
set bd [get_files $bd_file]
report_ip_status -file [file join $report_dir ip_status_before_generation.rpt]
generate_target all $bd
report_ip_status -file [file join $report_dir ip_status_after_generation.rpt]
puts {PHASE4G_OUTPUT_PRODUCTS=PASS}
set wrappers [get_files -all *system_wrapper.v]
if {[llength $wrappers] == 0} {
    set wrapper [make_wrapper -top -add $bd]
} elseif {[llength $wrappers] == 1} {
    set wrapper $wrappers
} else {
    error {Ambiguous system wrapper}
}
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
puts {PHASE4G_WRAPPER=PASS}
set listing [open [file join $report_dir vivado_source_inventory.tsv] w]
puts $listing "path\tUSED_IN_SYNTHESIS\tUSED_IN_SIMULATION\tFILE_TYPE"
foreach f [lsort [get_files -all]] {
    puts $listing "$f\t[get_property USED_IN_SYNTHESIS $f]\t[get_property USED_IN_SIMULATION $f]\t[get_property FILE_TYPE $f]"
}
close $listing
set run [get_runs synth_1]
if {[string first {Complete} [get_property STATUS $run]] < 0 || [get_property PROGRESS $run] ne {100%}} {
    launch_runs synth_1 -jobs 4
    wait_on_run synth_1
}
set status [get_property STATUS [get_runs synth_1]]
set progress [get_property PROGRESS [get_runs synth_1]]
puts "PHASE4G_SYNTH_STATUS=$status"
if {[string first {Complete} $status] < 0 || $progress ne {100%}} {error "Synthesis failed: $status $progress"}
puts {PHASE4G_SYNTH=PASS}
set runsout [open [file join $report_dir synthesis_runs.tsv] w]
puts $runsout "name\tstatus\tprogress\tSYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY"
foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
    puts $runsout "$run\t[get_property STATUS $run]\t[get_property PROGRESS $run]\t[get_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY $run]"
}
close $runsout
set scopeout [open [file join $report_dir implementation_scope.tsv] w]
puts $scopeout "name\tstatus\tprogress"
foreach run [get_runs -filter {IS_IMPLEMENTATION == 1}] {
    set run_status [get_property STATUS $run]
    set run_progress [get_property PROGRESS $run]
    if {$run_status ne {Not started} || $run_progress ne {0%}} {
        error "Implementation scope violated: $run $run_status $run_progress"
    }
    puts $scopeout "$run\t$run_status\t$run_progress"
}
close $scopeout
open_run synth_1
report_clocks -file [file join $report_dir system_clocks.rpt]
report_utilization -file [file join $report_dir system_utilization.rpt]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 -file [file join $report_dir system_utilization_hierarchical.rpt]
report_timing_summary -file [file join $report_dir system_timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -file [file join $report_dir system_setup_paths.rpt]
report_timing -delay_type min -max_paths 10 -file [file join $report_dir system_hold_paths.rpt]
check_timing -verbose -file [file join $report_dir system_check_timing.rpt]
report_drc -file [file join $report_dir system_drc.rpt]
set hierarchy [open [file join $report_dir writecredit_hierarchy.tsv] w]
puts $hierarchy "module\tcell\tREF_NAME\tORIG_REF_NAME\tprimitive_descendants"
foreach mod $patched_modules {
    # Vivado BD OOC checkpoints prefix HLS reference names with their IP instance.
    set cells [get_cells -hier -filter "REF_NAME == $mod || ORIG_REF_NAME == $mod || REF_NAME =~ *_$mod || ORIG_REF_NAME =~ *_$mod"]
    if {[llength $cells] < 1} {error "Patched module missing from system hierarchy: $mod"}
    foreach cell $cells {
        set prims [get_cells -hier -filter "IS_PRIMITIVE == 1 && NAME =~ $cell/*"]
        if {[llength $prims] == 0} {error "Patched module has no primitives: $cell"}
        puts $hierarchy "$mod\t$cell\t[get_property REF_NAME $cell]\t[get_property ORIG_REF_NAME $cell]\t[llength $prims]"
    }
    report_utilization -cells $cells -file [file join $report_dir "module_${mod}_utilization.rpt"]
}
close $hierarchy
set creditout [open [file join $report_dir writecredit_nets.txt] w]
foreach net [lsort [get_nets -hier -filter {NAME =~ *credit_count* || NAME =~ *credit_empty*}]] {
    puts $creditout $net
}
close $creditout
puts {PHASE4G_WRITECREDIT_HIERARCHY=PASS}
puts {PHASE4G_POST_SYNTHESIS_REPORTS=PASS}
close_project
exit
