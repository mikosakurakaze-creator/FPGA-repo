# Create a fresh, isolated KV260 three-module V1.1 project.
# Source: Vivado 2025.2 -mode batch -source this_file.
# The HLS repositories are fixed inputs. CNN source commit: 72b21138ce87a16eb3d3d6163675936b82ceadbc.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_1]
if {[file exists $project_dir]} {
    error "Refusing to overwrite existing V1.1 project directory: $project_dir"
}
set cnn_ip {E:/HLS/kv260_three_module_v1_1_ip_repo/cnn_72b2113_k26_10ns}
set bilinear_ip {E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip}
set curve_ip {E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip}
foreach ip_repo [list $cnn_ip $bilinear_ip $curve_ip] {
    if {![file isfile [file join $ip_repo component.xml]]} {
        error "Missing fixed HLS IP repository: $ip_repo"
    }
}

file mkdir $project_dir
cd $project_dir
create_project three_module_integration_v1_1 $project_dir -part xck26-sfvc784-2LV-c
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set_property ip_repo_paths [list $cnn_ip $bilinear_ip $curve_ip] [current_project]
update_ip_catalog -rebuild
foreach vlnv {
    xilinx.com:hls:zero_dce_cnn_top:1.0
    xilinx.com:hls:bilinear_fixed16_buffered:1.0
    xilinx.com:hls:curve_image_fixed16:1.0
} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {
        error "HLS IP not uniquely resolved: $vlnv"
    }
    puts "REGISTERED_IP=$vlnv"
}

create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 zynq_ultra_ps_e_0
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e \
    -config {apply_board_preset "1"} [get_bd_cells zynq_ultra_ps_e_0]
set ps [get_bd_cells zynq_ultra_ps_e_0]
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {1} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP3 {1} \
    CONFIG.PSU__USE__S_AXI_GP4 {1} \
    CONFIG.PSU__USE__S_AXI_GP5 {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] $ps
foreach pin {
    M_AXI_HPM0_FPD S_AXI_HP0_FPD S_AXI_HP1_FPD
    S_AXI_HP2_FPD S_AXI_HP3_FPD
} {
    if {[llength [get_bd_intf_pins zynq_ultra_ps_e_0/$pin]] != 1} {
        error "PS AXI port not enabled: $pin"
    }
}
if {[llength [get_bd_intf_pins -quiet zynq_ultra_ps_e_0/M_AXI_HPM1_FPD]] != 0} {
    error {PS HPM1 unexpectedly enabled}
}

create_bd_cell -type ip -vlnv xilinx.com:hls:zero_dce_cnn_top:1.0 zero_dce_cnn_top_0
create_bd_cell -type ip -vlnv xilinx.com:hls:bilinear_fixed16_buffered:1.0 bilinear_fixed16_buffered_0
create_bd_cell -type ip -vlnv xilinx.com:hls:curve_image_fixed16:1.0 curve_image_fixed16_0
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps_100m
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_locked
set_property -dict [list CONFIG.CONST_VAL {1}] [get_bd_cells const_locked]

foreach {name si mi} {
    axi_control 1 3
    cnn_data_sc 3 1
    cnn_model_sc 3 1
    bilinear_ddr_sc 2 1
    curve_ddr_sc 3 1
} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 $name
    set_property -dict [list CONFIG.NUM_SI $si CONFIG.NUM_MI $mi] [get_bd_cells $name]
}

# Exactly one PL clock domain, from PS pl_clk0. No Clock Converter or CDC IP.
connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] \
    [get_bd_pins rst_ps_100m/slowest_sync_clk] \
    [get_bd_pins zero_dce_cnn_top_0/ap_clk] \
    [get_bd_pins bilinear_fixed16_buffered_0/ap_clk] \
    [get_bd_pins curve_image_fixed16_0/ap_clk] \
    [get_bd_pins axi_control/aclk] \
    [get_bd_pins cnn_data_sc/aclk] \
    [get_bd_pins cnn_model_sc/aclk] \
    [get_bd_pins bilinear_ddr_sc/aclk] \
    [get_bd_pins curve_ddr_sc/aclk] \
    [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_fpd_aclk] \
    [get_bd_pins zynq_ultra_ps_e_0/saxihp0_fpd_aclk] \
    [get_bd_pins zynq_ultra_ps_e_0/saxihp1_fpd_aclk] \
    [get_bd_pins zynq_ultra_ps_e_0/saxihp2_fpd_aclk] \
    [get_bd_pins zynq_ultra_ps_e_0/saxihp3_fpd_aclk]
connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] \
    [get_bd_pins rst_ps_100m/ext_reset_in]
connect_bd_net [get_bd_pins const_locked/dout] \
    [get_bd_pins rst_ps_100m/dcm_locked]
connect_bd_net [get_bd_pins rst_ps_100m/peripheral_aresetn] \
    [get_bd_pins zero_dce_cnn_top_0/ap_rst_n] \
    [get_bd_pins bilinear_fixed16_buffered_0/ap_rst_n] \
    [get_bd_pins curve_image_fixed16_0/ap_rst_n]
connect_bd_net [get_bd_pins rst_ps_100m/interconnect_aresetn] \
    [get_bd_pins axi_control/aresetn] \
    [get_bd_pins cnn_data_sc/aresetn] \
    [get_bd_pins cnn_model_sc/aresetn] \
    [get_bd_pins bilinear_ddr_sc/aresetn] \
    [get_bd_pins curve_ddr_sc/aresetn]

save_bd_design
puts "V1_1_PROJECT=[get_property DIRECTORY [current_project]]"
puts "V1_1_PL_CLK0_MHZ=[get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $ps]"
puts {STAGE_CREATE=PASS}
close_project
exit
