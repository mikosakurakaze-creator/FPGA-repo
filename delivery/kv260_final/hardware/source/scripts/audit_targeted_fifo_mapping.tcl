# Read-only audit of six rebuilt nodes and the inherited local-memory decoders.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 4
source D:/weather_builds/timing_margin_20261102/fifo_targeted03_nodes/node_specs.tcl
open_checkpoint $checkpoint
if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Unresolved black box}}
if {[lsort [get_clocks]] ne {clk_pl_0 clk_pl_1} ||
    [get_property PERIOD [get_clocks clk_pl_0]] != 10.0 ||
    [get_property PERIOD [get_clocks clk_pl_1]] != 5.0} {error {Clock contract changed}}
set f [open [file join $out targeted_node_mapping.tsv] w]
puts $f "key\tbram36\tbram18\tidentity_luts"
foreach row $node_specs {
    lassign $row key module file method width
    lassign [split $key /] sc node
    set prefix "system_i/$sc/inst/[lindex [split $node _] 0]_nodes/$node/"
    set b36 0;set b18 0;set buffers 0
    foreach cell [get_cells -hierarchical -filter "NAME =~ ${prefix}* && IS_PRIMITIVE == 1"] {
        set ref [get_property REF_NAME $cell]
        if {$ref eq {RAMB36E2}} {incr b36}
        if {$ref eq {RAMB18E2}} {incr b18}
        if {[string first {hold_payload_delay} [get_property NAME $cell]] >= 0} {
            if {$ref ne {LUT1} || [string tolower [get_property INIT $cell]] ne {2'h2} ||
                ![get_property DONT_TOUCH $cell]} {error "Invalid preserved buffer: $cell"}
            incr buffers
        }
    }
    if {$method eq {bram} && ($b36 != 2 || $b18 != 2)} {error "Unexpected BRAM mapping: $key: $b36/$b18"}
    if {$method eq {buffer} && ($b36 || $b18 || $buffers != 2*$width)} {error "Unexpected command FIFO mapping: $key"}
    puts $f "$key\t$b36\t$b18\t$buffers"
}
close $f
set decoders [get_cells -hierarchical -filter {NAME =~ *hold_output_decode*decode_xor && REF_NAME == LUT2}]
if {[llength $decoders] != 3616} {error "Inherited XOR decoders changed: [llength $decoders]"}
foreach cell $decoders {
    if {[string tolower [get_property INIT $cell]] ne {4'h6} || ![get_property DONT_TOUCH $cell]} {error {Inherited decoder function changed}}
}
set f [open [file join $out inherited_mapping.txt] w]
puts $f "PRESERVED_LOCAL_DECODERS=[llength $decoders]"
close $f
write_xdc [file join $out synthesized_constraints.xdc]
report_clocks -file [file join $out synthesized_clocks.rpt]
report_utilization -file [file join $out synthesized_utilization.rpt]
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
