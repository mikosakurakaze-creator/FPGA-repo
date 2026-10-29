if {$argc != 2} {error {Expected checkpoint and new report directory}}
set checkpoint [file normalize [lindex $argv 0]]
set root [file normalize [lindex $argv 1]]
file mkdir $root
set_param general.maxThreads 2
open_checkpoint $checkpoint
if {[get_property PART [current_design]] ne {xck26-sfvc784-2LV-c}} {error {Wrong part}}
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error {Unresolved blackbox}}
if {[llength [get_clocks ap_clk -quiet]] != 1} {error {Missing clock}}
if {abs([get_property PERIOD [get_clocks ap_clk]]-10.0)>0.0001} {error {Wrong clock}}
report_utilization -file [file join $root utilization.rpt]
report_timing_summary -delay_type min_max -file [file join $root timing.rpt]
report_drc -file [file join $root drc.rpt]
puts {FUSION_CHECKPOINT_VERIFICATION_PASS}
close_design
exit
