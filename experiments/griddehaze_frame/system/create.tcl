if {$argc != 1} {error {Expected isolated build directory}}
set root [file normalize [lindex $argv 0]]
set project_dir [file join $root project]
if {[file exists $project_dir]} {error {Refuse to overwrite project}}
create_project weather_system $project_dir -part xck26-sfvc784-2LV-c
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set repos {}
foreach ip {cnn bilinear curve weather griddehaze} {lappend repos [file join $root ip $ip]}
set_property ip_repo_paths $repos [current_project]
config_ip_cache -disable_cache
update_ip_catalog -rebuild
foreach name {zero_dce_cnn_top bilinear_fixed16_buffered curve_image_fixed16 weather_frame_top griddehaze_frame_top} {
    if {[llength [get_ipdefs -all xilinx.com:hls:$name:1.0]] != 1} {error "IP resolution failed: $name"}
}
set bd_dir [file join $project_dir weather_system.srcs sources_1 bd system]
file mkdir $bd_dir
set bd_file [file join $bd_dir system.bd]
file copy [file join $root system_seed.bd] $bd_file
add_files -norecurse $bd_file
open_bd_design $bd_file
# This seed already contains the four legacy HLS cores and reviewed PS settings.
foreach name {zero_dce_cnn_top_0 bilinear_fixed16_buffered_0 curve_image_fixed16_0 weather_frame_top_0} {
    if {[llength [get_bd_cells -quiet $name]] != 1} {error "Legacy core absent: $name"}
}
if {[llength [get_bd_cells -quiet griddehaze_frame_top_0]] != 0} {error {New core already exists}}
create_bd_cell -type ip -vlnv xilinx.com:hls:griddehaze_frame_top:1.0 griddehaze_frame_top_0
set_property CONFIG.NUM_MI 5 [get_bd_cells axi_control]
set_property CONFIG.NUM_SI 5 [get_bd_cells cnn_data_sc]
set_property CONFIG.NUM_SI 5 [get_bd_cells curve_ddr_sc]
connect_bd_intf_net [get_bd_intf_pins axi_control/M04_AXI] [get_bd_intf_pins griddehaze_frame_top_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins griddehaze_frame_top_0/m_axi_feature_mem] [get_bd_intf_pins curve_ddr_sc/S04_AXI]
connect_bd_intf_net [get_bd_intf_pins griddehaze_frame_top_0/m_axi_parameter_mem] [get_bd_intf_pins cnn_data_sc/S04_AXI]
connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins griddehaze_frame_top_0/ap_clk]
connect_bd_net [get_bd_pins rst_ps_100m/peripheral_aresetn] [get_bd_pins griddehaze_frame_top_0/ap_rst_n]
assign_bd_address -offset 0xA0040000 -range 64K -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs griddehaze_frame_top_0/s_axi_control/Reg]
foreach master {feature_mem parameter_mem} hp {3 0} {
    set space [get_bd_addr_spaces griddehaze_frame_top_0/Data_m_axi_$master]
    assign_bd_address -offset 0 -range 2G -target_address_space $space [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP[expr {$hp+2}]/HP${hp}_DDR_LOW]
}
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $root system_recreate.tcl]
report_ip_status -file [file join $root ip_status.rpt]
generate_target all [get_files $bd_file]
set wrapper [make_wrapper -files [get_files $bd_file] -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
write_hw_platform -fixed -force -file [file join $root griddehaze_system_preimpl.xsa]
puts {GRID_SYSTEM_CREATE_PASS}
close_project
exit
