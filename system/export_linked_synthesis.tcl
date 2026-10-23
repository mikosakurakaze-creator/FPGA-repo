# Read the original completed synthesis with its OOC checkpoints resolved.
# Write to a new directory; do not reset/save/relaunch the original project.
if {$argc != 2} {error {Expected original project and new export directory}}
set project [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to replace diagnostic evidence}}
file mkdir $output
set_param general.maxThreads 2
open_project $project
open_run synth_1
set blackboxes [get_cells -hier -filter {IS_BLACKBOX == 1}]
if {[llength $blackboxes] != 0} {error "Unresolved blackboxes: $blackboxes"}
set target {system_i/weather_frame_top_0/inst/grp_frame_fu_160/spatial_5_U0/grp_spatial_5_Pipeline_VITIS_LOOP_133_2_fu_450/mac_muladd_15ns_7s_22s_23_4_1_U1742/weather_frame_top_mac_muladd_15ns_7s_22s_23_4_1_DSP48_0_U/p_reg_reg}
set cell [get_cells -quiet $target]
if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne {DSP48E2}} {error {Expected DSP receiver absent}}
report_property $cell -file [file join $output receiver_properties.rpt]
set fd [open [file join $output receiver_connections.txt] w]
foreach port {C PCIN OPMODE} {
    for {set bit 0} {$bit < [expr {$port eq {OPMODE} ? 9 : 48}]} {incr bit} {
        set pin [get_pins -quiet "$target/$port\[$bit\]"]
        set nets [get_nets -of_objects $pin]
        puts $fd "$port $bit $nets [get_pins -of_objects $nets -filter {DIRECTION == OUT}]"
    }
}
close $fd
write_checkpoint [file join $output system_linked_synth.dcp]
puts {WEATHER_LINKED_SYNTHESIS_EXPORT_COMPLETED}
close_project
exit
