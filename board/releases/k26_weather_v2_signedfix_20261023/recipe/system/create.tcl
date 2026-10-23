if {$argc != 1} {error {Expected output directory}}
set root [file normalize [lindex $argv 0]]
set project_dir [file join $root project]
if {[file exists $project_dir]} {error {Refuse to overwrite project}}
# The copied CNN package contains the independently hash-checked writer overlay.
ipx::open_core [file join $root ip cnn component.xml]
ipx::update_checksums [ipx::current_core]
ipx::check_integrity [ipx::current_core]
ipx::save_core [ipx::current_core]
ipx::unload_core [ipx::current_core]
create_project weather_system $project_dir -part xck26-sfvc784-2LV-c
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set_property ip_repo_paths [list [file join $root ip cnn] [file join $root ip bilinear] [file join $root ip curve] [file join $root ip weather]] [current_project]
config_ip_cache -disable_cache
update_ip_catalog -rebuild
foreach vlnv {xilinx.com:hls:zero_dce_cnn_top:1.0 xilinx.com:hls:bilinear_fixed16_buffered:1.0 xilinx.com:hls:curve_image_fixed16:1.0 xilinx.com:hls:weather_frame_top:1.0} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {error "IP resolution failed: $vlnv"}
}
set bd_dir [file join $project_dir weather_system.srcs sources_1 bd system]
file mkdir $bd_dir
set bd_file [file join $bd_dir system.bd]
file copy [file join $root system_seed.bd] $bd_file
add_files -norecurse $bd_file
open_bd_design $bd_file
# Same public low-light ABI, newly generated candidates. No original checkout/IP is edited.
upgrade_bd_cells [get_bd_cells {zero_dce_cnn_top_0 bilinear_fixed16_buffered_0 curve_image_fixed16_0}]
set weather [create_bd_cell -type ip -vlnv xilinx.com:hls:weather_frame_top:1.0 weather_frame_top_0]
set_property CONFIG.NUM_MI 4 [get_bd_cells axi_control]
set_property CONFIG.NUM_SI 4 [get_bd_cells cnn_data_sc]
set_property CONFIG.NUM_SI 4 [get_bd_cells curve_ddr_sc]
connect_bd_intf_net [get_bd_intf_pins axi_control/M03_AXI] [get_bd_intf_pins weather_frame_top_0/s_axi_CTRL]
connect_bd_intf_net [get_bd_intf_pins weather_frame_top_0/m_axi_gmem_in] [get_bd_intf_pins cnn_data_sc/S03_AXI]
connect_bd_intf_net [get_bd_intf_pins weather_frame_top_0/m_axi_gmem_out] [get_bd_intf_pins curve_ddr_sc/S03_AXI]
connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins weather_frame_top_0/ap_clk]
connect_bd_net [get_bd_pins rst_ps_100m/peripheral_aresetn] [get_bd_pins weather_frame_top_0/ap_rst_n]
assign_bd_address -offset 0xA0030000 -range 64K -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs weather_frame_top_0/s_axi_CTRL/Reg]
# Restrict the new masters to low DDR. The PS backend allocates buffers there;
# OCM/QSPI/high-DDR are intentionally not made accessible to this core.
foreach master {gmem_in gmem_out} hp {0 3} {
    set space [get_bd_addr_spaces weather_frame_top_0/Data_m_axi_$master]
    assign_bd_address -offset 0x00000000 -range 2G -target_address_space $space [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP[expr {$hp + 2}]/HP${hp}_DDR_LOW]
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
write_hw_platform -fixed -force -file [file join $root weather_system_preimpl.xsa]
puts {WEATHER_SYSTEM_CREATE_PASS}
close_project
exit
