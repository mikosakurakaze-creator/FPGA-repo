
if {$argc != 1} {error {Expected Phase6 output directory}}
set out [file normalize [lindex $argv 0]]
set project_file {E:/HLS/kv260_three_module_v1_2_phase4/phase4g/integration_01/project/v12_wc.xpr}
set xsa [file join $out kv260_three_module_v1_2_writecredit.xsa]
if {[file exists $xsa]} {error {Refusing to overwrite XSA}}
open_project $project_file
set impl [get_runs impl_1]
if {[get_property STATUS $impl] ne {write_bitstream Complete!} || [get_property PROGRESS $impl] ne {100%} || [get_property NEEDS_REFRESH $impl]} {error {Bitstream prerequisite failed}}
open_run impl_1
write_hw_platform -fixed -include_bit -file $xsa
if {![file isfile $xsa]} {error {XSA not generated}}
puts "PHASE6_XSA_EXPORT_COMPLETE=PASS"
puts "PHASE6_XSA_PATH=$xsa"
puts "PHASE6_XSA_BYTES=[file size $xsa]"
close_project
exit
