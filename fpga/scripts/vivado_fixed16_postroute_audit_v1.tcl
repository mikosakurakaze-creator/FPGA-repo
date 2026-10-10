# Read the routed implementation checkpoint and produce evidence reports only.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set report_dir {E:/HLS/vivado_fixed16_implementation_v1}
file mkdir $report_dir
open_project $project_file
set run [get_runs impl_1]
puts "IMPLEMENTATION_STATUS=[get_property STATUS $run]"
puts "IMPLEMENTATION_PROGRESS=[get_property PROGRESS $run]"
open_run impl_1
puts "OPEN_RUN_DESIGN=[current_design]"
foreach clk [get_clocks] {puts "CLOCK=$clk PERIOD_NS=[get_property PERIOD $clk]"}
report_route_status -file [file join $report_dir postroute_route_status.rpt]
report_drc -file [file join $report_dir postroute_drc.rpt]
report_utilization -file [file join $report_dir postroute_utilization.rpt]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 \
    -file [file join $report_dir postroute_utilization_hierarchical.rpt]
report_timing_summary -file [file join $report_dir postroute_timing_summary.rpt]
report_timing -delay_type max -max_paths 10 \
    -file [file join $report_dir postroute_setup_paths.rpt]
report_timing -delay_type min -max_paths 10 \
    -file [file join $report_dir postroute_hold_paths.rpt]
check_timing -verbose -file [file join $report_dir postroute_check_timing_verbose.rpt]
puts {POSTROUTE_AUDIT_DONE}
close_project
exit
