# KV260 Fixed16 V1: register the original HLS IPs and add clock/reset wiring.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set bd_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd}
set curve_ip {E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip}
set bilinear_ip {E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip}

open_project $project_file
set old_repos [get_property ip_repo_paths [current_project]]
set_property ip_repo_paths [lsort -unique [concat $old_repos [list $curve_ip $bilinear_ip]]] [current_project]
update_ip_catalog -rebuild

foreach vlnv {xilinx.com:hls:curve_image_fixed16:1.0 xilinx.com:hls:bilinear_fixed16_buffered:1.0} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {
        error "HLS IP not uniquely registered: $vlnv"
    }
    puts "REGISTERED_IP=$vlnv"
}

open_bd_design $bd_file
if {[llength [get_bd_cells zynq_ultra_ps_e_0]] != 1} {
    error {Expected the saved KV260 Zynq UltraScale+ PS in system.bd}
}
if {[get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ [get_bd_cells zynq_ultra_ps_e_0]] ne {100}} {
    error {Saved PS pl_clk0 is not 100 MHz}
}

create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps_100m
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_locked
set_property -dict [list CONFIG.CONST_VAL {1}] [get_bd_cells const_locked]

create_bd_cell -type ip -vlnv xilinx.com:hls:bilinear_fixed16_buffered:1.0 bilinear_fixed16_buffered_0
create_bd_cell -type ip -vlnv xilinx.com:hls:curve_image_fixed16:1.0 curve_image_fixed16_0

connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] \
    [get_bd_pins rst_ps_100m/slowest_sync_clk] \
    [get_bd_pins bilinear_fixed16_buffered_0/ap_clk] \
    [get_bd_pins curve_image_fixed16_0/ap_clk] \
    [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_fpd_aclk] \
    [get_bd_pins zynq_ultra_ps_e_0/saxihp0_fpd_aclk]
connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] [get_bd_pins rst_ps_100m/ext_reset_in]
connect_bd_net [get_bd_pins const_locked/dout] [get_bd_pins rst_ps_100m/dcm_locked]
connect_bd_net [get_bd_pins rst_ps_100m/peripheral_aresetn] \
    [get_bd_pins bilinear_fixed16_buffered_0/ap_rst_n] \
    [get_bd_pins curve_image_fixed16_0/ap_rst_n]

save_bd_design
puts {STAGE1=PASS IP registered, two cores added, 100MHz and reset connected}
close_project
exit
