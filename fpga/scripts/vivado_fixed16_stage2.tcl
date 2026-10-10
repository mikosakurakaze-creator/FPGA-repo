# KV260 Fixed16 V1: PS control and shared DDR interconnect.
set project_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.xpr}
set bd_file {E:/github/-/fpga/vivado/fixed16_integration_v1/fixed16_integration_v1.srcs/sources_1/bd/system/system.bd}

open_project $project_file
open_bd_design $bd_file
foreach name {zynq_ultra_ps_e_0 rst_ps_100m bilinear_fixed16_buffered_0 curve_image_fixed16_0} {
    if {[llength [get_bd_cells $name]] != 1} {error "Missing stage 1 cell: $name"}
}
# Board automation also enabled HPM1, which has no V1 peripheral and caused
# an incomplete address path and an unclocked AXI port at validation.
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP1 {0}] [get_bd_cells zynq_ultra_ps_e_0]

create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_control
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells axi_control]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_ddr
set_property -dict [list CONFIG.NUM_SI {5} CONFIG.NUM_MI {1}] [get_bd_cells axi_ddr]

# PS control master -> 1-to-2 AXI-Lite fabric -> both HLS control slaves.
connect_bd_intf_net [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM0_FPD] [get_bd_intf_pins axi_control/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_control/M00_AXI] [get_bd_intf_pins bilinear_fixed16_buffered_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins axi_control/M01_AXI] [get_bd_intf_pins curve_image_fixed16_0/s_axi_control]

# Five independent HLS AXI memory masters -> one shared PS HP0 slave -> DDR.
set masters {
    bilinear_fixed16_buffered_0/m_axi_gmem_input
    bilinear_fixed16_buffered_0/m_axi_gmem_output
    curve_image_fixed16_0/m_axi_gmem_input
    curve_image_fixed16_0/m_axi_gmem_parameter
    curve_image_fixed16_0/m_axi_gmem_output
}
for {set i 0} {$i < [llength $masters]} {incr i} {
    set source [lindex $masters $i]
    set sink [format {axi_ddr/S%02d_AXI} $i]
    if {[llength [get_bd_intf_pins $source]] != 1} {error "Missing HLS AXI master: $source"}
    connect_bd_intf_net [get_bd_intf_pins $source] [get_bd_intf_pins $sink]
    puts "DDR_MASTER=$source -> $sink"
}
connect_bd_intf_net [get_bd_intf_pins axi_ddr/M00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HP0_FPD]

connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] \
    [get_bd_pins axi_control/aclk] [get_bd_pins axi_ddr/aclk]
connect_bd_net [get_bd_pins rst_ps_100m/interconnect_aresetn] \
    [get_bd_pins axi_control/aresetn] [get_bd_pins axi_ddr/aresetn]

assign_bd_address
# The HLS masters are DDR-only in this design; remove auto-mapped QSPI access.
foreach source $masters {
    set space [string map {m_axi_ Data_m_axi_} $source]
    set qspi [get_bd_addr_segs ${space}/SEG_zynq_ultra_ps_e_0_HP0_QSPI]
    if {[llength $qspi] != 1} {error "Missing QSPI mapping for $source"}
    exclude_bd_addr_seg $qspi
}
puts {ADDRESS_SPACES_BEGIN}
foreach space [get_bd_addr_spaces] {
    puts "ADDRESS_SPACE=$space"
    foreach seg [get_bd_addr_segs -of_objects $space] {
        set offset [get_property OFFSET $seg]
        set range [get_property RANGE $seg]
        puts "  SEGMENT=$seg OFFSET=$offset RANGE=$range"
    }
}
puts {ADDRESS_SPACES_END}

set result [validate_bd_design]
puts "VALIDATE_RESULT=$result"
puts "EXT_RESET_POLARITY=[get_property CONFIG.POLARITY [get_bd_pins rst_ps_100m/ext_reset_in]]"
puts "EXT_RESET_HIGH=[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]]"
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]] ne {0}} {
    error {PS active-low pl_resetn0 is not interpreted as active-low by Processor System Reset}
}
save_bd_design
puts {STAGE2=PASS AXI control/DDR, address map, and Validate Design}
close_project
exit
