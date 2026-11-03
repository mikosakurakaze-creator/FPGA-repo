# Standalone replacements for the six CURRENT routed nodes. No full resynthesis.
if {$argc != 7} {error {Use isolated runner}}
set out [file normalize [lindex $argv 1]]
set prepared D:/weather_builds/timing_margin_20261102/fifo_targeted03_nodes
file copy [file join $prepared node_specs.tcl] [file join $out node_specs.tcl]
source [file join $out node_specs.tcl]
set_param general.maxThreads 4
# All definitions belong to one standalone compilation. Managed IP sources are
# scoped to the probe BD and disappear when its top is replaced; do not rely on
# those scoped sources for an unrelated standalone node top.
create_project -in_memory -part xck26-sfvc784-2LV-c
set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]
set vendor D:/vivado/2025.2/Vivado/data/ip/xilinx
set_property include_dirs [list [file join $vendor sc_util_v1_0/hdl/verilog] [file join $vendor sc_node_v1_0/hdl/verilog]] [current_fileset]
set sources [list [file join $vendor sc_util_v1_0/hdl/sc_util_v1_0_vl_rfs.sv] \
                  [file join $vendor sc_node_v1_0/hdl/sc_node_v1_0_vl_rfs.sv]]
foreach row $node_specs {
    lassign $row key module file method width
    lappend sources $file
}
read_verilog -sv $sources
set f [open [file join $out node_mapping.tsv] w]
puts $f "key\tbram36\tbram18\tidentity_luts"
foreach row $node_specs {
    lassign $row key module file method width
    puts "TARGETED_NODE_SYNTH_START=$key"
    set_property top $module [current_fileset]
    update_compile_order -fileset sources_1
    synth_design -top $module -part xck26-sfvc784-2LV-c -mode out_of_context -flatten_hierarchy none
    if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error "Black box: $key"}
    set b36 [llength [get_cells -hierarchical -filter {REF_NAME == RAMB36E2}]]
    set b18 [llength [get_cells -hierarchical -filter {REF_NAME == RAMB18E2}]]
    set delays [get_cells -hierarchical -filter {NAME =~ *hold_payload_delay* && REF_NAME == LUT1}]
    if {$method eq {bram} && $b36+$b18==0} {error "BRAM mapping missing: $key"}
    if {$method eq {buffer} && [llength $delays] != 2*$width} {error "Preserved identity LUTs missing: $key"}
    foreach cell $delays {
        if {[string tolower [get_property INIT $cell]] ne {2'h2} || ![get_property DONT_TOUCH $cell]} {error {Invalid identity LUT}}
    }
    puts $f "$key\t$b36\t$b18\t[llength $delays]";flush $f
    set tag [string map {/ __} $key]
    report_utilization -file [file join $out ${tag}_utilization.rpt]
    write_checkpoint [file join $out ${tag}.dcp]
    close_design
    puts "TARGETED_NODE_SYNTH_PASS=$key"
}
close $f
puts {TIMING_MARGIN_INSPECT_PASS}
exit
