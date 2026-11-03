# Read-only classification of remaining SmartConnect output-register banks.
if {$argc != 7} {error {Use the isolated diagnostic runner}}
set out [file normalize [lindex $argv 1]]
open_checkpoint [file normalize [lindex $argv 0]]
set f [open [file join $out remaining_fifo_output_registers.tsv] w]
puts $f "cell\tref\tdriver\tdriver_ref\tparent\tparent_orig_ref\tparent_ref"
set groups [dict create]
foreach cell [get_cells -hierarchical -filter {NAME =~ *gen_rf_narrow_reg*doutb_reg_reg* && REF_NAME == FDRE}] {
    set cname [get_property NAME $cell]
    if {![regexp {^system_i/(cnn_data_sc|cnn_model_sc|bilinear_ddr_sc|curve_ddr_sc)/} $cname]} {continue}
    set d [get_pins -of_objects $cell -filter {REF_PIN_NAME == D}]
    set net [get_nets -segments -of_objects $d]
    set drivers [get_pins -leaf -of_objects $net -filter {DIRECTION == OUT}]
    if {[llength $drivers] != 1} {error "Unexpected D driver: $cname"}
    set driver [get_cells -of_objects $drivers]
    set parent [get_cells [join [lrange [split $cname /] 0 end-1] /]]
    puts $f "$cname\tFDRE\t[get_property NAME $drivers]\t[get_property REF_NAME $driver]\t[get_property NAME $parent]\t[get_property ORIG_REF_NAME $parent]\t[get_property REF_NAME $parent]"
    set prefix [lindex [split $cname /] 1]
    regexp {^(.*)/[^/]*doutb_reg_reg} $cname -> prefix
    dict incr groups $prefix
}
close $f
set f [open [file join $out remaining_fifo_output_groups.txt] w]
dict for {name count} $groups {puts $f "$name\t$count"}
close $f
report_utilization -file [file join $out synthesis_utilization.rpt]
puts {TIMING_MARGIN_INSPECT_PASS}
exit
