if {$argc != 2} {error {Expected checkpoint and new diagnostic directory}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite diagnostic output}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set fp [open [file join $output pin_constants.tsv] w]
puts $fp "pin\tlogic_value\tis_connected\tnet"
foreach cell {system_i/weather_frame_top_0 system_i/cnn_data_sc system_i/curve_ddr_sc} {
    foreach pin [get_pins -of_objects [get_cells $cell]] {
        set properties [list_property $pin]
        set value UNKNOWN
        set connected UNKNOWN
        if {"LOGIC_VALUE" in $properties} {set value [get_property LOGIC_VALUE $pin]}
        if {"IS_CONNECTED" in $properties} {set connected [get_property IS_CONNECTED $pin]}
        puts $fp "$pin\t$value\t$connected\t[get_nets -quiet -of_objects $pin]"
    }
}
close $fp
foreach pin_name {{system_i/weather_frame_top_0/s_axi_CTRL_BRESP[0]} {system_i/weather_frame_top_0/s_axi_CTRL_RDATA[31]} {system_i/cnn_data_sc/S03_AXI_araddr[63]} {system_i/cnn_data_sc/M00_AXI_araddr[48]}} {
    report_property -all [get_pins $pin_name] -append -file [file join $output pin_properties.txt]
}
help write_verilog
puts {WEATHER_DIAGNOSTIC_CONSTANTS_COMPLETED}
close_design
exit
