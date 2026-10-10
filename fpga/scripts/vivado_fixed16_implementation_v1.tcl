# Implement the existing KV260 Fixed16 V1 project through routing only.
# Keep the project's current implementation strategy and never launch bitstream.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
open_project $project_file

set synth [get_runs synth_1]
set synth_status [get_property STATUS $synth]
if {[string first {Complete} $synth_status] < 0} {
    error "Prerequisite synthesis is incomplete: $synth_status"
}
set impl [get_runs impl_1]
puts "SYNTHESIS_STATUS=$synth_status"
puts "IMPLEMENTATION_STRATEGY=[get_property STRATEGY $impl]"
puts "IMPLEMENTATION_FLOW=[get_property FLOW $impl]"
foreach step {OPT_DESIGN PLACE_DESIGN PHYS_OPT_DESIGN ROUTE_DESIGN WRITE_BITSTREAM} {
    puts "STEP_${step}_ENABLED=[get_property STEPS.${step}.IS_ENABLED $impl]"
}
puts {IMPLEMENTATION_LAUNCH_TO_ROUTE_DESIGN}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
set status [get_property STATUS [get_runs impl_1]]
set progress [get_property PROGRESS [get_runs impl_1]]
puts "IMPLEMENTATION_STATUS=$status"
puts "IMPLEMENTATION_PROGRESS=$progress"
if {[string first {Complete} $status] < 0} {
    error "Implementation did not complete routing: $status ($progress)"
}
close_project
exit
