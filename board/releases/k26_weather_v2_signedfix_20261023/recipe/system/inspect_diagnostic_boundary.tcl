if {$argc != 2} {error {Expected checkpoint and new diagnostic directory}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite diagnostic output}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set fp [open [file join $output boundary.tsv] w]
puts $fp "cell\tpin\tdirection\tnet\tdrivers"
foreach name {system_i/weather_frame_top_0 system_i/cnn_data_sc system_i/curve_ddr_sc system_i/rst_ps_100m} {
    set cell [get_cells -quiet $name]
    if {[llength $cell] != 1} {error "Expected one cell: $name"}
    foreach pin [get_pins -of_objects $cell] {
        set nets [get_nets -quiet -of_objects $pin]
        set leaves [get_nets -quiet -segments $nets]
        set drivers [get_pins -quiet -leaf -of_objects $leaves -filter {DIRECTION == OUT}]
        puts $fp "$name\t[get_property REF_PIN_NAME $pin]\t[get_property DIRECTION $pin]\t$nets\t$drivers"
    }
}
close $fp
foreach name {system_i/cnn_data_sc system_i/curve_ddr_sc system_i/rst_ps_100m} {
    write_verilog -force -mode funcsim -cell [get_cells $name] [file join $output [file tail $name]_funcsim.v]
}
puts {WEATHER_DIAGNOSTIC_BOUNDARY_EXPORT_COMPLETED}
close_design
exit
