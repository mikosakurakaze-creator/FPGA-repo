# Inspect the synthesized checkpoint only; do not launch implementation.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set report_dir {E:/HLS/vivado_fixed16_synthesis_v1}
open_project $project_file
open_run synth_1
check_timing -verbose -file [file join $report_dir system_check_timing_verbose.rpt]
report_timing -delay_type min -max_paths 10 -file [file join $report_dir system_hold_paths.rpt]
puts {POST_SYNTHESIS_TIMING_AUDIT_DONE}
close_project
exit
