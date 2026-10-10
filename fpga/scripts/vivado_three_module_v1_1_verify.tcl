# Finalize DDR-only apertures, validate, save, and audit the isolated V1.1 BD.
# Run after vivado_three_module_v1_1_stage2.tcl. Does not synthesize.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_1]
set project_file [file join $project_dir three_module_integration_v1_1.xpr]
set bd_file [file join $project_dir three_module_integration_v1_1.srcs sources_1 bd system system.bd]
cd $project_dir
open_project $project_file
open_bd_design $bd_file

set ps [get_bd_cells zynq_ultra_ps_e_0]
foreach {key expected} {
    PSU__USE__M_AXI_GP0 1
    PSU__USE__M_AXI_GP1 0
    PSU__USE__S_AXI_GP2 1
    PSU__USE__S_AXI_GP3 1
    PSU__USE__S_AXI_GP4 1
    PSU__USE__S_AXI_GP5 1
    PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ 100
} {
    set actual [get_property CONFIG.$key $ps]
    puts "PS_CONFIG=$key:$actual"
    if {$actual ne $expected} {error "PS configuration mismatch $key: $actual"}
}
foreach name {
    zynq_ultra_ps_e_0 zero_dce_cnn_top_0 bilinear_fixed16_buffered_0
    curve_image_fixed16_0 axi_control cnn_data_sc cnn_model_sc
    bilinear_ddr_sc curve_ddr_sc rst_ps_100m
} {
    set cell [get_bd_cells $name]
    if {[llength $cell] != 1} {error "Missing BD cell: $name"}
    puts "CELL=$name VLNV=[get_property VLNV $cell]"
}
foreach {name si mi} {
    axi_control 1 3
    cnn_data_sc 3 1
    cnn_model_sc 3 1
    bilinear_ddr_sc 2 1
    curve_ddr_sc 3 1
} {
    if {[get_property CONFIG.NUM_SI [get_bd_cells $name]] != $si ||
        [get_property CONFIG.NUM_MI [get_bd_cells $name]] != $mi} {
        error "SmartConnect port count mismatch: $name"
    }
    puts "SMARTCONNECT=$name SI=$si MI=$mi"
}

set ddr_masters {
    zero_dce_cnn_top_0/m_axi_gmem_input
    zero_dce_cnn_top_0/m_axi_gmem_output
    zero_dce_cnn_top_0/m_axi_gmem_workspace
    zero_dce_cnn_top_0/m_axi_gmem8
    zero_dce_cnn_top_0/m_axi_gmem32
    zero_dce_cnn_top_0/m_axi_gmem_lut
    bilinear_fixed16_buffered_0/m_axi_gmem_input
    bilinear_fixed16_buffered_0/m_axi_gmem_output
    curve_image_fixed16_0/m_axi_gmem_input
    curve_image_fixed16_0/m_axi_gmem_parameter
    curve_image_fixed16_0/m_axi_gmem_output
}
if {[llength $ddr_masters] != 11} {error {Expected 11 DDR masters}}

# Address Editor's automatic memory mapping includes QSPI on each HP port.
# These HLS pointers are DDR buffers only; OCM is likewise not a V1.1 target.
foreach master $ddr_masters {
    set space_name [string map {m_axi_ Data_m_axi_} $master]
    set space [get_bd_addr_spaces $space_name]
    if {[llength $space] != 1} {error "Missing address space: $space_name"}
    foreach seg [get_bd_addr_segs -of_objects $space] {
        if {[regexp -nocase {QSPI|OCM} $seg] &&
            [get_property OFFSET $seg] ne {}} {
            exclude_bd_addr_seg $seg
            puts "EXCLUDED=$seg"
        }
    }
}

set expected_control {
    SEG_bilinear_fixed16_buffered_0_Reg 0xA0000000
    SEG_curve_image_fixed16_0_Reg 0xA0010000
    SEG_zero_dce_cnn_top_0_Reg 0xA0020000
}
foreach {seg_name expected_offset} $expected_control {
    set seg [get_bd_addr_segs zynq_ultra_ps_e_0/Data/$seg_name]
    if {[llength $seg] != 1} {error "Missing control segment: $seg_name"}
    set offset [get_property OFFSET $seg]
    set range [get_property RANGE $seg]
    puts "CONTROL_ADDR=$seg_name OFFSET=$offset RANGE=$range"
    if {[expr {$offset != $expected_offset || $range != 0x10000}]} {
        error "Unexpected AXI-Lite address: $seg_name"
    }
}

foreach master $ddr_masters {
    set space_name [string map {m_axi_ Data_m_axi_} $master]
    set space [get_bd_addr_spaces $space_name]
    set low 0
    set high 0
    foreach seg [get_bd_addr_segs -of_objects $space] {
        set offset [get_property OFFSET $seg]
        if {$offset eq {}} {continue}
        if {[regexp {DDR_LOW$} $seg]} {incr low}
        if {[regexp {DDR_HIGH$} $seg]} {incr high}
        if {[regexp -nocase {QSPI|OCM} $seg]} {
            error "Non-DDR address remains mapped: $seg"
        }
        puts "DDR_APERTURE=$space_name SEG=$seg OFFSET=$offset RANGE=[get_property RANGE $seg]"
    }
    if {$low != 1 || $high != 1} {
        error "DDR LOW/HIGH mapping missing: $space_name ($low/$high)"
    }
}

# Verify one physical clock net connects all three HLS cores, four HP ports,
# five SmartConnect instances, the HPM0 clock, and Processor System Reset.
set clock_net [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_clk0]]
foreach pin {
    rst_ps_100m/slowest_sync_clk
    zero_dce_cnn_top_0/ap_clk
    bilinear_fixed16_buffered_0/ap_clk
    curve_image_fixed16_0/ap_clk
    axi_control/aclk cnn_data_sc/aclk cnn_model_sc/aclk
    bilinear_ddr_sc/aclk curve_ddr_sc/aclk
    zynq_ultra_ps_e_0/maxihpm0_fpd_aclk
    zynq_ultra_ps_e_0/saxihp0_fpd_aclk
    zynq_ultra_ps_e_0/saxihp1_fpd_aclk
    zynq_ultra_ps_e_0/saxihp2_fpd_aclk
    zynq_ultra_ps_e_0/saxihp3_fpd_aclk
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $clock_net} {
        error "Non-100MHz clock net: $pin"
    }
}
puts "CLOCK_NET=$clock_net FREQ_MHZ=[get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $ps]"
set ext_reset [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/ext_reset_in]]
if {$ext_reset ne [get_bd_nets -of_objects [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0]]} {
    error {PS reset output does not feed Processor System Reset}
}
puts "RESET_EXT_NET=$ext_reset POLARITY=[get_property CONFIG.POLARITY [get_bd_pins rst_ps_100m/ext_reset_in]] C_EXT_RESET_HIGH=[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]]"

# Report connected bus widths. The HLS scalar size and HP data bus width are
# separate facts; SmartConnect is responsible for any required conversion.
foreach pin {
    zero_dce_cnn_top_0/m_axi_gmem_input
    zero_dce_cnn_top_0/m_axi_gmem_output
    zero_dce_cnn_top_0/m_axi_gmem_workspace
    zero_dce_cnn_top_0/m_axi_gmem8
    zero_dce_cnn_top_0/m_axi_gmem32
    zero_dce_cnn_top_0/m_axi_gmem_lut
    bilinear_fixed16_buffered_0/m_axi_gmem_input
    bilinear_fixed16_buffered_0/m_axi_gmem_output
    curve_image_fixed16_0/m_axi_gmem_input
    curve_image_fixed16_0/m_axi_gmem_parameter
    curve_image_fixed16_0/m_axi_gmem_output
    zynq_ultra_ps_e_0/S_AXI_HP0_FPD
    zynq_ultra_ps_e_0/S_AXI_HP1_FPD
    zynq_ultra_ps_e_0/S_AXI_HP2_FPD
    zynq_ultra_ps_e_0/S_AXI_HP3_FPD
} {
    set obj [get_bd_intf_pins $pin]
    puts "BUS_PIN=$pin DATA_WIDTH=[get_property CONFIG.DATA_WIDTH $obj] PROTOCOL=[get_property CONFIG.PROTOCOL $obj]"
}

set result [validate_bd_design]
puts "VALIDATE_RESULT=$result"
puts "RESET_AFTER_VALIDATE_POLARITY=[get_property CONFIG.POLARITY [get_bd_pins rst_ps_100m/ext_reset_in]] C_EXT_RESET_HIGH=[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]]"
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst_ps_100m]] ne {0}} {
    error {Processor System Reset does not interpret PS reset as active low after validation}
}
set peripheral_reset [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/peripheral_aresetn]]
foreach pin {
    zero_dce_cnn_top_0/ap_rst_n
    bilinear_fixed16_buffered_0/ap_rst_n
    curve_image_fixed16_0/ap_rst_n
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $peripheral_reset} {
        error "HLS reset not on peripheral_aresetn: $pin"
    }
}
set interconnect_reset [get_bd_nets -of_objects [get_bd_pins rst_ps_100m/interconnect_aresetn]]
foreach pin {
    axi_control/aresetn cnn_data_sc/aresetn cnn_model_sc/aresetn
    bilinear_ddr_sc/aresetn curve_ddr_sc/aresetn
} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $interconnect_reset} {
        error "SmartConnect reset not on interconnect_aresetn: $pin"
    }
}
puts "RESET_PERIPHERAL_NET=$peripheral_reset"
puts "RESET_INTERCONNECT_NET=$interconnect_reset"

foreach pin {
    axi_control/S00_AXI axi_control/M00_AXI axi_control/M01_AXI axi_control/M02_AXI
    cnn_data_sc/S00_AXI cnn_data_sc/S01_AXI cnn_data_sc/S02_AXI cnn_data_sc/M00_AXI
    cnn_model_sc/S00_AXI cnn_model_sc/S01_AXI cnn_model_sc/S02_AXI cnn_model_sc/M00_AXI
    bilinear_ddr_sc/S00_AXI bilinear_ddr_sc/S01_AXI bilinear_ddr_sc/M00_AXI
    curve_ddr_sc/S00_AXI curve_ddr_sc/S01_AXI curve_ddr_sc/S02_AXI curve_ddr_sc/M00_AXI
} {
    set obj [get_bd_intf_pins $pin]
    puts "FABRIC_BUS=$pin DATA_WIDTH=[get_property CONFIG.DATA_WIDTH $obj] PROTOCOL=[get_property CONFIG.PROTOCOL $obj]"
}
foreach master $ddr_masters {
    set net [get_bd_intf_nets -of_objects [get_bd_intf_pins $master]]
    if {[llength $net] != 1} {error "Unconnected DDR master: $master"}
    puts "DDR_NET=$master NET=$net PEERS=[get_bd_intf_pins -of_objects $net]"
}
foreach vlnv {
    xilinx.com:hls:zero_dce_cnn_top:1.0
    xilinx.com:hls:bilinear_fixed16_buffered:1.0
    xilinx.com:hls:curve_image_fixed16:1.0
} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {
        error "Missing or ambiguous IP catalog entry: $vlnv"
    }
    puts "IP_CATALOG=RESOLVED $vlnv"
}
save_bd_design
report_ip_status -file {E:/HLS/vivado_three_module_v1_1_ip_status.rpt}
puts {V1_1_VALIDATE=PASS}
close_project
exit
