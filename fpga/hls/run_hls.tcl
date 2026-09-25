# Run from the repository root with: vitis-run --mode hls --tcl fpga/hls/run_hls.tcl
# Vitis HLS rejects spaces in source paths. Stage source and test data under a
# whitespace-free build root before creating the HLS component.
set repo_root [file normalize [file join [file dirname [info script]] .. ..]]
set package_dir [file join $repo_root outputs zero_dce_pp quantization hls_cnn]

if {[info exists ::env(ZERO_DCE_HLS_BUILD_ROOT)]} {
    set build_root [file normalize $::env(ZERO_DCE_HLS_BUILD_ROOT)]
} elseif {[info exists ::env(TEMP)]} {
    set build_root [file normalize $::env(TEMP)]
} elseif {[info exists ::env(TMPDIR)]} {
    set build_root [file normalize $::env(TMPDIR)]
} else {
    error "Set ZERO_DCE_HLS_BUILD_ROOT to a writable path without whitespace."
}
if {[regexp {\s} $build_root]} {
    error "HLS build root contains whitespace: $build_root; set ZERO_DCE_HLS_BUILD_ROOT."
}

set run_dir [file join $build_root [format "zero_dce_cnn_%s_%s" \
    [clock format [clock seconds] -format %Y%m%d_%H%M%S] [pid]]]
set source_dir [file join $run_dir src]
set data_dir [file join $run_dir data]
file mkdir $source_dir
file mkdir $data_dir

foreach filename {zero_dce_cnn_top.cpp zero_dce_cnn_top.h tb_zero_dce_cnn.cpp} {
    set source [file join $repo_root fpga hls $filename]
    if {![file isfile $source]} {
        error "Missing HLS source: $source"
    }
    file copy $source [file join $source_dir $filename]
}
set data_files {
    input_q14.bin weights_int8.bin bias_int32.bin weight_frac.bin
    tanh_lut_q15.bin expected_a_low_q14.bin
}
foreach filename $data_files {
    set source [file join $package_dir $filename]
    if {![file isfile $source]} {
        error "Missing HLS test data: $source; run deployment/export_hls_cnn_package.py first."
    }
    file copy $source [file join $data_dir $filename]
}

set config_path [file join $run_dir hls_config.cfg]
set config [open $config_path w]
puts $config {part=xc7z020clg400-1}
puts $config ""
puts $config {[hls]}
puts $config {flow_target=vivado}
puts $config {clock=10ns}
puts $config "syn.file=[file join $source_dir zero_dce_cnn_top.cpp]"
puts $config {syn.top=zero_dce_cnn_top}
puts $config "tb.file=[file join $source_dir tb_zero_dce_cnn.cpp]"
foreach filename $data_files {
    puts $config "tb.file=[file join $data_dir $filename]"
}
close $config

puts "HLS build directory: $run_dir"
cd $run_dir
open_component [file join $run_dir component] -config $config_path -apply_ini
csim_design
if {![info exists ::env(ZERO_DCE_HLS_CSIM_ONLY)] ||
    $::env(ZERO_DCE_HLS_CSIM_ONLY) ne "1"} {
    csynth_design
}
exit
