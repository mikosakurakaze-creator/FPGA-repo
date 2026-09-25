# Run with Vitis HLS: vitis_hls -f fpga/hls/run_hls.tcl
# C simulation must pass before synthesis. No RTL or Vivado project is made.
set repo_root [file normalize [file join [file dirname [info script]] .. ..]]
set package_dir [file join $repo_root outputs zero_dce_pp quantization hls_cnn]
open_project -reset [file join $repo_root outputs zero_dce_pp quantization hls_project]
set_top zero_dce_cnn_top
add_files [file join $repo_root fpga hls zero_dce_cnn_top.cpp] -cflags "-std=c++14"
add_files -tb [file join $repo_root fpga hls tb_zero_dce_cnn.cpp] -cflags "-std=c++14"
add_files -tb [file join $package_dir input_q14.bin]
add_files -tb [file join $package_dir weights_int8.bin]
add_files -tb [file join $package_dir bias_int32.bin]
add_files -tb [file join $package_dir weight_frac.bin]
add_files -tb [file join $package_dir tanh_lut_q15.bin]
add_files -tb [file join $package_dir expected_a_low_q14.bin]
open_solution -reset solution1
set_part {xc7z020clg400-1}
create_clock -period 10 -name default
csim_design
csynth_design
exit
