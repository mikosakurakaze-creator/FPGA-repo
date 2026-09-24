# Run the complete KV260 Fixed16 V1 project through synthesis only.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set report_dir {E:/HLS/vivado_fixed16_synthesis_v1}
file mkdir $report_dir

open_project $project_file
set top [get_property TOP [get_filesets sources_1]]
if {$top ne {system_wrapper}} {error "Unexpected synthesis top: $top"}
if {[llength [get_files -all *system_wrapper.v]] != 1} {error {Missing managed HDL wrapper}}
puts "SYNTHESIS_TOP=$top"
puts {SYNTHESIS_RUN_START}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
set run [get_runs synth_1]
set status [get_property STATUS $run]
set progress [get_property PROGRESS $run]
puts "SYNTHESIS_STATUS=$status"
puts "SYNTHESIS_PROGRESS=$progress"
if {[string first {Complete} $status] < 0 || $progress ne {100%}} {
    error "Synthesis did not complete: $status ($progress)"
}

open_run synth_1
puts "OPEN_RUN_DESIGN=[current_design]"
foreach clk [get_clocks] {
    puts "CLOCK=$clk PERIOD_NS=[get_property PERIOD $clk]"
}
report_utilization -file [file join $report_dir system_utilization.rpt]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 \
    -file [file join $report_dir system_utilization_hierarchical.rpt]
report_timing_summary -file [file join $report_dir system_timing_summary.rpt]
report_timing -max_paths 10 -file [file join $report_dir system_timing_paths.rpt]
report_drc -file [file join $report_dir system_drc.rpt]
puts {POST_SYNTHESIS_REPORTS_DONE}
close_project
exit
