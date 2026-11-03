# Read-only diagnosis of inferred FIFO register packing before placement.
set out [file normalize [lindex $argv 1]]
open_checkpoint [file normalize [lindex $argv 0]]
set f [open [file join $out fifo_shape_properties.txt] w]
set pattern {*bilinear_ddr_sc*gen_rf_narrow_reg.doutb_reg_reg*}
set cells [get_cells -hierarchical -filter "NAME =~ $pattern"]
puts $f "MATCHED=[llength $cells]"
foreach cell [lrange $cells 0 1] {
    puts $f "CELL=$cell"
    foreach prop [list_property $cell] {puts $f "$prop=[get_property $prop $cell]"}
    set net [get_nets -of_objects [get_pins $cell/D]]
    foreach driver [get_cells -of_objects [get_pins -leaf -of_objects $net -filter {DIRECTION == OUT}]] {
        puts $f "DRIVER=$driver"
        foreach prop [list_property $driver] {puts $f "$prop=[get_property $prop $driver]"}
    }
}
puts $f "MACROS=[get_macros -quiet]"
puts $f "COMMANDS=[info commands *macro*]"
close $f
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
