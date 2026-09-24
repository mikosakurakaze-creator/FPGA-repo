# Generate full BD output products and a Vivado-managed top wrapper.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set bd_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd}
set report_dir {E:/HLS/vivado_fixed16_synthesis_v1}
file mkdir $report_dir

open_project $project_file
open_bd_design $bd_file
foreach cell {
    zynq_ultra_ps_e_0 rst_ps_100m axi_control axi_ddr
    bilinear_fixed16_buffered_0 curve_image_fixed16_0
} {
    if {[llength [get_bd_cells $cell]] != 1} {error "Missing saved BD cell: $cell"}
}
foreach vlnv {
    xilinx.com:hls:bilinear_fixed16_buffered:1.0
    xilinx.com:hls:curve_image_fixed16:1.0
} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {error "Missing HLS IP: $vlnv"}
    puts "IP_RESOLVED=$vlnv"
}
validate_bd_design
set bd [get_files $bd_file]
report_ip_status -file [file join $report_dir ip_status_before_generation.rpt]
puts {OUTPUT_PRODUCTS_START}
generate_target all $bd
puts {OUTPUT_PRODUCTS_DONE}

set existing_wrapper [get_files -all *system_wrapper.v]
if {[llength $existing_wrapper] == 0} {
    set wrapper [make_wrapper -top -add $bd]
} else {
    set wrapper $existing_wrapper
}
puts "WRAPPER_PATH=$wrapper"
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
puts "SYNTHESIS_TOP=[get_property TOP [get_filesets sources_1]]"
puts "WRAPPER_FILES=[get_files -all *system_wrapper*]"
puts "LOCKED_IPS=[get_ips -filter {IS_LOCKED==1}]"
report_ip_status -file [file join $report_dir ip_status_after_generation.rpt]
close_project
puts {OUTPUT_PRODUCTS_WRAPPER_STAGE=PASS}
exit
