set root [file normalize [lindex $argv 0]]
open_project [file join $root project weather_system.xpr]
set_param general.maxThreads 2
# A cancelled child can leave a stale Running state without a live tool. The
# operator marks only that generated run for an explicit isolated rebuild.
if {[file exists [file join $root retry_weather_only.flag]]} {
    reset_run [get_runs system_weather_frame_top_0_0_synth_1]
    file delete [file join $root retry_weather_only.flag]
}
foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
    set status [get_property STATUS $run]
    puts "SYNTH_RUN_STATUS=$run $status"
    if {[string match -nocase {*error*} $status]} {reset_run $run}
}
if {[get_property PROGRESS [get_runs synth_1]] ne {100%}} {reset_run synth_1}
launch_runs synth_1 -jobs 1
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne {100%}} {error {Synthesis failed}}
open_run synth_1
report_utilization -hierarchical -file [file join $root synthesis_utilization.rpt]
report_timing_summary -file [file join $root synthesis_timing.rpt]
write_checkpoint -force [file join $root system_synth.dcp]
puts {WEATHER_SYSTEM_SYNTH_PASS}
close_project
exit
