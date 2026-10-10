# Audit of the saved V1 block design after integration.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set bd_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd}
open_project $project_file
open_bd_design $bd_file

foreach cell [get_bd_cells] {
    puts "CELL=$cell VLNV=[get_property VLNV $cell]"
}
foreach source {
    zynq_ultra_ps_e_0/M_AXI_HPM0_FPD
    axi_control/M00_AXI axi_control/M01_AXI
    bilinear_fixed16_buffered_0/m_axi_gmem_input
    bilinear_fixed16_buffered_0/m_axi_gmem_output
    curve_image_fixed16_0/m_axi_gmem_input
    curve_image_fixed16_0/m_axi_gmem_parameter
    curve_image_fixed16_0/m_axi_gmem_output
    axi_ddr/M00_AXI
} {
    set pin [get_bd_intf_pins $source]
    set net [get_bd_intf_nets -of_objects $pin]
    puts "AXI_PIN=$source NET=$net PEERS=[get_bd_intf_pins -of_objects $net]"
}
foreach source {
    zynq_ultra_ps_e_0/pl_clk0 zynq_ultra_ps_e_0/pl_resetn0
    rst_ps_100m/ext_reset_in rst_ps_100m/slowest_sync_clk
    rst_ps_100m/dcm_locked rst_ps_100m/interconnect_aresetn
    rst_ps_100m/peripheral_aresetn
    axi_control/aclk axi_control/aresetn axi_ddr/aclk axi_ddr/aresetn
    bilinear_fixed16_buffered_0/ap_clk bilinear_fixed16_buffered_0/ap_rst_n
    curve_image_fixed16_0/ap_clk curve_image_fixed16_0/ap_rst_n
    zynq_ultra_ps_e_0/maxihpm0_fpd_aclk zynq_ultra_ps_e_0/saxihp0_fpd_aclk
} {
    set pin [get_bd_pins $source]
    puts "PIN=$source NET=[get_bd_nets -of_objects $pin]"
}
puts "PL_CLK0_MHZ=[get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ [get_bd_cells zynq_ultra_ps_e_0]]"
puts "HPM0_ENABLED=[get_property CONFIG.PSU__USE__M_AXI_GP0 [get_bd_cells zynq_ultra_ps_e_0]]"
puts "HPM1_ENABLED=[get_property CONFIG.PSU__USE__M_AXI_GP1 [get_bd_cells zynq_ultra_ps_e_0]]"
puts "HP0_ENABLED=[get_property CONFIG.PSU__USE__S_AXI_GP2 [get_bd_cells zynq_ultra_ps_e_0]]"
puts "RESET_POLARITY=[get_property CONFIG.POLARITY [get_bd_pins rst_ps_100m/ext_reset_in]]"
puts "C_EXT_RESET_HIGH=[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]]"
puts "CONTROL_NUM_SI=[get_property CONFIG.NUM_SI [get_bd_cells axi_control]]"
puts "CONTROL_NUM_MI=[get_property CONFIG.NUM_MI [get_bd_cells axi_control]]"
puts "DDR_NUM_SI=[get_property CONFIG.NUM_SI [get_bd_cells axi_ddr]]"
puts "DDR_NUM_MI=[get_property CONFIG.NUM_MI [get_bd_cells axi_ddr]]"
foreach space [get_bd_addr_spaces] {
    puts "ADDRESS_SPACE=$space"
    foreach seg [get_bd_addr_segs -of_objects $space] {
        puts "  SEGMENT=$seg OFFSET=[get_property OFFSET $seg] RANGE=[get_property RANGE $seg]"
    }
}
validate_bd_design
puts {SAVED_BD_VALIDATE=PASS}
exit
