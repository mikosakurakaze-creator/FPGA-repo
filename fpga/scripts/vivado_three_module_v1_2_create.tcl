# Independent V1.2 project from the frozen V1.1 BD. Never open the V1.1 XPR.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_2]
set run_dir {E:/HLS/kv260_three_module_v1_2_phase4}
if {[file exists $project_dir]} {error "Refusing to overwrite existing V1.2 project: $project_dir"}
if {![file exists [file join $run_dir r4_export_gate.txt]]} {error {Fresh r4 export/ABI gate has not passed}}
set ip_repos [list [file join $run_dir ip_repo cnn_r4] [file join $run_dir ip_repo bilinear] [file join $run_dir ip_repo curve]]
foreach p $ip_repos {
    if {![file isfile [file join $p component.xml]]} {error "Missing isolated IP: $p"}
}
file mkdir $project_dir
cd $project_dir
create_project three_module_integration_v1_2 $project_dir -part xck26-sfvc784-2LV-c
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set_property ip_repo_paths $ip_repos [current_project]
update_ip_catalog -rebuild
foreach vlnv {xilinx.com:hls:zero_dce_cnn_top:1.0 xilinx.com:hls:bilinear_fixed16_buffered:1.0 xilinx.com:hls:curve_image_fixed16:1.0} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {error "IP resolution differs: $vlnv"}
    puts "ISOLATED_IP=$vlnv"
}
set bd_dir [file join $project_dir three_module_integration_v1_2.srcs sources_1 bd system]
file mkdir $bd_dir
set bd_file [file join $bd_dir system.bd]
file copy [file join $run_dir system_seed.bd] $bd_file
add_files -norecurse $bd_file
open_bd_design $bd_file
validate_bd_design
save_bd_design
report_ip_status -file [file join $run_dir v1_2_initial_ip_status.rpt]
puts {V1_2_CREATE_VALIDATE=PASS}
close_project
exit
