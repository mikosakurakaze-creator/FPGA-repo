# Collect the real V1.2 simulation source graph only after synthesis passed.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set run_dir {E:/HLS/kv260_three_module_v1_2_phase4}
if {![file exists [file join $run_dir synthesis_gate.txt]]} {error {Synthesis gate is closed}}
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_2]
open_project [file join $project_dir three_module_integration_v1_2.xpr]
set bd [get_files *system.bd]
generate_target simulation $bd
update_compile_order -fileset sim_1
set f [open [file join $run_dir simulation_files.tsv] w]
foreach src [get_files -compile_order sources -used_in simulation] {
    puts $f "[file normalize $src]\t[get_property FILE_TYPE $src]\t[get_property LIBRARY $src]"
}
close $f
set f [open [file join $run_dir simulation_all_files.tsv] w]
foreach src [get_files -all] {
    puts $f "[file normalize $src]\t[get_property FILE_TYPE $src]\t[get_property LIBRARY $src]"
}
close $f
puts {V1_2_SIMULATION_SOURCES=PASS}
close_project
exit
