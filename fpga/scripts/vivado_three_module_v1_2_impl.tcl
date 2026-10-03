# Phase 5: reuse the authoritative Phase 4G project; stop at route_design.
# No IP generation, RTL edits, synthesis launch, bitstream or hardware export.
if {$argc != 1} {error {Expected the Phase 5 output directory}}
set output_dir [file normalize [lindex $argv 0]]
source {E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/integration_config.tcl}
set report_dir [file join $output_dir reports]
file mkdir $report_dir
set project_file [file join $project_dir ${project_name}.xpr]
set bd_file [file join $project_dir ${project_name}.srcs sources_1 bd system system.bd]
set run_dir [file join $project_dir ${project_name}.runs impl_1]
set status_file [open [file join $report_dir run_status.tsv] w]
puts $status_file "key\tvalue"
proc record {key value} {
    global status_file
    puts $status_file "$key\t[string map [list \n { } \r { } \t { }] $value]"
    flush $status_file
    puts "PHASE5_$key=$value"
}
cd $project_dir
open_project $project_file
record PROJECT $project_file
record TOOL_VERSION [version -short]
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c} ||
    [get_property TOP [get_filesets sources_1]] ne {system_wrapper}} {error {Wrong device/top}}
set actual_repos [get_property IP_REPO_PATHS [current_project]]
if {[llength $actual_repos] != [llength $ip_repos]} {error {Wrong IP repository count}}
foreach actual $actual_repos expected $ip_repos {
    if {![string equal -nocase [file normalize $actual] [file normalize $expected]]} {error {Wrong IP repository}}
}
set synth [get_runs synth_1]
set cnn_synth [get_runs system_zero_dce_cnn_top_0_0_synth_1]
foreach run [list $synth $cnn_synth] {
    record ${run}_STATUS [get_property STATUS $run]
    record ${run}_PROGRESS [get_property PROGRESS $run]
    if {[get_property STATUS $run] ne {synth_design Complete!} ||
        [get_property PROGRESS $run] ne {100%} || [get_property NEEDS_REFRESH $run]} {
        error "Authoritative synthesis is incomplete or stale: $run"
    }
}
open_bd_design $bd_file
set cnn [get_bd_cells zero_dce_cnn_top_0]
if {[get_property VLNV $cnn] ne {xilinx.com:hls:zero_dce_cnn_top:1.0} ||
    [get_property CONFIG.Component_Name $cnn] ne {system_zero_dce_cnn_top_0_0}} {error {Wrong CNN identity}}
set cnn_ip [get_ips system_zero_dce_cnn_top_0_0]
record CNN_IP_PROPERTIES [list_property $cnn_ip]
set cnn_xci [get_files -all *system_zero_dce_cnn_top_0_0.xci]
if {[llength $cnn_xci] != 1} {error {Ambiguous CNN XCI}}
set catalog [get_ipdefs -all xilinx.com:hls:zero_dce_cnn_top:1.0]
if {[llength $catalog] != 1} {error {Ambiguous CNN catalog}}
set component [get_property XML_FILE_NAME $catalog]
if {![string equal -nocase [file normalize $component] [file normalize [file join [lindex $ip_repos 0] component.xml]]]} {
    error {CNN catalog is not the formal package}
}
record FORMAL_CNN_COMPONENT $component
set f [open $component r]; set component_text [read $f]; close $f
if {![regexp {<[^>]*coreRevision[^>]*>2114810448</} $component_text]} {error {Wrong formal CNN revision}}
record FORMAL_CNN_REVISION 2114810448
foreach {name si mi} {axi_control 1 3 cnn_data_sc 3 1 cnn_model_sc 3 1 bilinear_ddr_sc 2 1 curve_ddr_sc 3 1} {
    set cell [get_bd_cells $name]
    if {[get_property CONFIG.NUM_SI $cell] != $si || [get_property CONFIG.NUM_MI $cell] != $mi} {error "Changed topology: $name"}
}
foreach {name expected} {
    SEG_bilinear_fixed16_buffered_0_Reg 0xA0000000
    SEG_curve_image_fixed16_0_Reg 0xA0010000
    SEG_zero_dce_cnn_top_0_Reg 0xA0020000
} {
    set seg [get_bd_addr_segs zynq_ultra_ps_e_0/Data/$name]
    if {[llength $seg] != 1 || [get_property OFFSET $seg] != $expected || [get_property RANGE $seg] != 0x10000} {error "Changed address map: $name"}
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
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]] ne {0} ||
    [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/ext_reset_in]] ne
    [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0]]} {error {Changed PS reset}}
foreach {reset pins} {
    peripheral_aresetn {zero_dce_cnn_top_0/ap_rst_n bilinear_fixed16_buffered_0/ap_rst_n curve_image_fixed16_0/ap_rst_n}
    interconnect_aresetn {axi_control/aresetn cnn_data_sc/aresetn cnn_model_sc/aresetn bilinear_ddr_sc/aresetn curve_ddr_sc/aresetn}
} {
    set net [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/$reset]]
    foreach pin $pins {if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $net} {error "Changed reset: $pin"}}
}
validate_bd_design
record BD_VALIDATE PASS
# Deliberately do not save or regenerate the BD.
open_run synth_1
set hierarchy [open [file join $report_dir preflight_writecredit_hierarchy.tsv] w]
puts $hierarchy "module\tcell\tREF_NAME\tORIG_REF_NAME\tprimitive_descendants"
foreach mod $patched_modules {
    set cells [get_cells -hier -filter "REF_NAME == $mod || ORIG_REF_NAME == $mod || REF_NAME =~ *_$mod || ORIG_REF_NAME =~ *_$mod"]
    if {[llength $cells] < 1} {error "Missing formal writer: $mod"}
    foreach cell $cells {
        set prims [get_cells -hier -filter "IS_PRIMITIVE == 1 && NAME =~ $cell/*"]
        if {[llength $prims] == 0} {error "Writer has no synthesized primitives: $mod"}
        puts $hierarchy "$mod\t$cell\t[get_property REF_NAME $cell]\t[get_property ORIG_REF_NAME $cell]\t[llength $prims]"
    }
}
close $hierarchy
set clock [get_clocks clk_pl_0]
if {[llength $clock] != 1 || abs([get_property PERIOD $clock] - 10.0) > 0.00001} {error {Wrong synthesized active 100MHz clock}}
foreach clock [get_clocks] {
    record SYNTH_CLOCK_$clock [get_property PERIOD $clock]
}
record SYNTH_WRITECREDIT_HIERARCHY PASS
close_design
set impl [get_runs impl_1]
record IMPL_STRATEGY [get_property STRATEGY $impl]
record IMPL_FLOW [get_property FLOW $impl]
record IMPL_INITIAL_STATUS [get_property STATUS $impl]
record IMPL_INITIAL_PROGRESS [get_property PROGRESS $impl]
foreach step {OPT_DESIGN PLACE_DESIGN PHYS_OPT_DESIGN ROUTE_DESIGN} {
    record ${step}_DIRECTIVE [get_property STEPS.${step}.ARGS.DIRECTIVE $impl]
}
record PHYS_OPT_INITIAL_ENABLED [get_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED $impl]
if {[get_property STATUS $impl] ne {Not started} || [get_property PROGRESS $impl] ne {0%}} {error {Implementation has already started; refusing automatic reset/retry}}
# The requested normal flow includes phys_opt_design, using its existing directive.
if {![get_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED $impl]} {
    set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true $impl
}
record PHYS_OPT_EFFECTIVE_ENABLED [get_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED $impl]
record LAUNCH_TO_STEP route_design
record START_EPOCH [clock seconds]
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
record END_EPOCH [clock seconds]
record IMPL_STATUS [get_property STATUS $impl]
record IMPL_PROGRESS [get_property PROGRESS $impl]
if {[get_property STATUS $impl] ne {route_design Complete!} || [get_property PROGRESS $impl] ne {100%}} {
    close $status_file
    error {Implementation did not naturally complete route_design; timing gate prohibited}
}
set routed_dcp [file join $run_dir system_wrapper_routed.dcp]
if {![file isfile $routed_dcp] || ![file isfile [file join $run_dir .vivado.end.rst]] || [file exists [file join $run_dir .vivado.error.rst]]} {
    error {Missing routed checkpoint or natural success marker}
}
record NATURAL_IMPLEMENTATION_END PASS
record ROUTED_DCP $routed_dcp
open_run impl_1
report_clocks -file [file join $report_dir postroute_clocks.rpt]
report_clock_interaction -file [file join $report_dir postroute_clock_interaction.rpt]
report_exceptions -summary -file [file join $report_dir postroute_timing_exceptions.rpt]
report_route_status -file [file join $report_dir postroute_route_status.rpt]
report_utilization -file [file join $report_dir postroute_utilization.rpt]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 -file [file join $report_dir postroute_utilization_hierarchical.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $report_dir postroute_timing_summary.rpt]
report_timing -delay_type max -max_paths 10 -path_type full_clock_expanded -input_pins -file [file join $report_dir postroute_setup_paths.rpt]
report_timing -delay_type min -max_paths 10 -path_type full_clock_expanded -input_pins -file [file join $report_dir postroute_hold_paths.rpt]
check_timing -verbose -file [file join $report_dir postroute_check_timing.rpt]
report_drc -file [file join $report_dir postroute_drc.rpt]
set drc [open [file join $report_dir postroute_drc_violations.tsv] w]
puts $drc "violation\tseverity\tdescription"
foreach v [get_drc_violations -quiet] {
    puts $drc "$v\t[get_property SEVERITY $v]\t[string map [list \n { } \r { } \t { }] [get_property DESCRIPTION $v]]"
}
close $drc
set hierarchy [open [file join $report_dir postroute_writecredit_hierarchy.tsv] w]
puts $hierarchy "module\tcell\tREF_NAME\tORIG_REF_NAME\tprimitive_descendants"
foreach mod $patched_modules {
    set cells [get_cells -hier -filter "REF_NAME == $mod || ORIG_REF_NAME == $mod || REF_NAME =~ *_$mod || ORIG_REF_NAME =~ *_$mod"]
    if {[llength $cells] < 1} {error "Missing routed writer hierarchy: $mod"}
    foreach cell $cells {
        set prims [get_cells -hier -filter "IS_PRIMITIVE == 1 && NAME =~ $cell/*"]
        puts $hierarchy "$mod\t$cell\t[get_property REF_NAME $cell]\t[get_property ORIG_REF_NAME $cell]\t[llength $prims]"
    }
    report_utilization -cells $cells -file [file join $report_dir module_${mod}_utilization.rpt]
}
close $hierarchy
record POSTROUTE_REPORTS_COMPLETE PASS
close $status_file
close_project
exit
