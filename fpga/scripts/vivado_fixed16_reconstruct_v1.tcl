# Reconstruct the KV260 Fixed16 V1 Vivado project from the tracked system.bd.
# Run only in a fresh output directory. HLS IP repositories must already exist.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set bd_source [file join $repo_root fpga vivado fixed16_integration_v1 \
    fixed16_integration_v1.srcs sources_1 bd system system.bd]
set bilinear_ip {E:/HLS/fpga_bilinear_fixed16_buffered/fpga_bilinear_fixed16_buffered/hls/impl/ip}
set curve_ip {E:/HLS/fpga_curve_fixed16/fpga_curve_fixed16/hls/impl/ip}
if {![file isfile $bd_source]} {error "Missing tracked BD source: $bd_source"}
foreach ip_repo [list $bilinear_ip $curve_ip] {
    if {![file isfile [file join $ip_repo component.xml]]} {
        error "Missing packaged HLS IP repository: $ip_repo"
    }
}
if {[info exists ::env(KV260_RECONSTRUCTION_DIR)]} {
    set project_dir [file normalize $::env(KV260_RECONSTRUCTION_DIR)]
} else {
    set project_dir {E:/HLS/kv260_fixed16_v1_reconstructed}
}
if {[file exists $project_dir]} {
    error "Refusing to overwrite an existing reconstruction directory: $project_dir"
}
set bd_staging_dir [file normalize ${project_dir}_bd_source]
if {[file exists $bd_staging_dir]} {
    error "Refusing to overwrite an existing BD staging directory: $bd_staging_dir"
}

create_project fixed16_integration_v1 $project_dir -part xck26-sfvc784-2LV-c
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set_property ip_repo_paths [list $bilinear_ip $curve_ip] [current_project]
update_ip_catalog -rebuild
foreach vlnv {
    xilinx.com:hls:bilinear_fixed16_buffered:1.0
    xilinx.com:hls:curve_image_fixed16:1.0
} {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {error "IP not uniquely resolved: $vlnv"}
    puts "RECONSTRUCTION_IP_RESOLVED=$vlnv"
}

# Vivado requires a BD source tree separate from its project tree. Stage a
# private copy as a sibling, so the tracked BD cannot be modified by Vivado.
file mkdir $bd_staging_dir
set bd_copy [file join $bd_staging_dir fixed16_integration_v1.srcs \
    sources_1 bd system system.bd]
file mkdir [file dirname $bd_copy]
file copy $bd_source $bd_copy
add_files -norecurse -fileset sources_1 $bd_copy
open_bd_design $bd_copy
foreach cell {
    zynq_ultra_ps_e_0 rst_ps_100m axi_control axi_ddr
    bilinear_fixed16_buffered_0 curve_image_fixed16_0
} {
    if {[llength [get_bd_cells $cell]] != 1} {error "Missing saved BD cell: $cell"}
}
set pl_clock_mhz [get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ \
    [get_bd_cells zynq_ultra_ps_e_0]]
if {[expr {abs(double($pl_clock_mhz) - 100.0) > 0.001}]} {
    error {Reconstructed PS pl_clk0 is not 100 MHz}
}
validate_bd_design
puts {RECONSTRUCTION_VALIDATE=PASS}
set bd [get_files $bd_copy]
generate_target all $bd
puts {RECONSTRUCTION_OUTPUT_PRODUCTS=PASS}
set wrapper [make_wrapper -top -add $bd]
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
puts "RECONSTRUCTION_WRAPPER=$wrapper"
puts "RECONSTRUCTION_TOP=[get_property TOP [get_filesets sources_1]]"
close_project
puts "RECONSTRUCTION_PROJECT=$project_dir"
exit
