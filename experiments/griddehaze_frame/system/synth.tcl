set root [file normalize [lindex $argv 0]]
open_project [file join $root project weather_system.xpr]
set_param general.maxThreads 2
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne {100%}} {error {System synthesis failed}}
open_run synth_1
report_utilization -hierarchical -file [file join $root synthesis_utilization.rpt]
report_utilization -file [file join $root synthesis_utilization_summary.rpt]
report_timing_summary -file [file join $root synthesis_timing.rpt]
write_checkpoint -force [file join $root system_synth.dcp]
write_verilog -force -mode funcsim [file join $root system_synth_funcsim.v]
puts {GRID_SYSTEM_SYNTH_PASS}
close_project
exit
