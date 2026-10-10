# Report timing from the checkpoint made immediately after place_design.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set placed_checkpoint {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.runs/impl_1/system_wrapper_placed.dcp}
set report_dir {E:/HLS/vivado_fixed16_implementation_v1}
open_project $project_file
open_checkpoint $placed_checkpoint
report_timing_summary -file [file join $report_dir postplace_timing_summary.rpt]
puts {POSTPLACE_AUDIT_DONE}
close_project
exit
