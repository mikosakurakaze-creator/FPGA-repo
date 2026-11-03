# Minimal reconstruction diagnostic; deliberately avoids a device-wide search.
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 8
open_checkpoint [file normalize [lindex $argv 0]]
source [file join $out fifo_hold_relocate.tcl]
set name {system_i/curve_ddr_sc/inst/s05_nodes/s05_aw_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst/gen_rd_b.gen_rd_b_synth_template.gen_rf_narrow_reg.doutb_reg_reg[172]}
set signature [relocate_pin_signature $name]
set properties [relocate_register_properties $name]
set f [open [file join $out reconstruction_before.txt] w]
puts $f "NAME=$name\nSIGNATURE=$signature\nPROPERTIES=$properties"
close $f
recreate_fifo_register $name $signature $properties
set f [open [file join $out reconstruction_after.txt] w]
puts $f "NAME=$name\nSIGNATURE=[relocate_pin_signature $name]\nPROPERTIES=[relocate_register_properties $name]"
close $f
if {[relocate_pin_signature $name] ne $signature || [relocate_register_properties $name] ne $properties} {
    error {Minimal reconstruction changes register function}
}
puts {RECONSTRUCTION_FUNCTION_PRESERVED}
set target {SLICE_X48Y208/DFF2}
puts "PLACEMENT_TRIAL_BEGIN\t$name\t$target"
set code [catch {place_cell [list $name $target]} reason]
if {$code} {puts $reason}
puts "PLACEMENT_TRIAL_END\t$code"
if {$code} {error {Known-free target rejected after reconstruction}}
write_checkpoint [file join $out reconstructed_placed.dcp]
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
