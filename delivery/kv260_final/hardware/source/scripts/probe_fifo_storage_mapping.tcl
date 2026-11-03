if {$argc != 7} {error {Use the isolated diagnostic runner}}
set out [file normalize [lindex $argv 1]]
set build D:/weather_builds/timing_margin_20261102/fifo_storage01
set top [file join $out fifo_mapping_probe.v]
set f [open $top w]
puts $f {
module fifo_mapping_probe(input clk100,clk200,reset,ce,we,re,
 input [5:0] ra,wa,input [127:0] din,
 output [127:0] dq,pq, output [15:0] cq,output full_n,empty_n,
 output [5:0] num,cap);
compact_d_top_fifo_w128_d32_A d(clk200,reset,full_n,ce,we,din,num,cap,empty_n,ce,re,dq);
zero_dce_cnn_top_p_anonymous_namespace_depth_band_actor_source_RAM_2P_LUTRAM_1R1W c(
ra[4:0],ce,cq,wa[4:0],ce,din[15:0],we,reset,clk100);
joint_rgb8_prepare_convert_tiles_original_tile_RAM_2P_LUTRAM_1R1W p(
ra,ce,pq,wa,ce,din,we,reset,clk100);
endmodule
}
close $f
create_project -in_memory -part xck26-sfvc784-2LV-c
read_verilog [list $top \
 [file join $build ip/compact_d/hdl/verilog/compact_d_top_fifo_w128_d32_A.v] \
 [file join $build ip/cnn/hdl/verilog/zero_dce_cnn_top_p_anonymous_namespace_depth_band_actor_source_RAM_2P_LUTRAM_1R1W.v] \
 [file join $build prepare/hls/impl/ip/hdl/verilog/joint_rgb8_prepare_convert_tiles_original_tile_RAM_2P_LUTRAM_1R1W.v]]
synth_design -top fifo_mapping_probe -part xck26-sfvc784-2LV-c -mode out_of_context
create_clock -name clk100 -period 10.0 [get_ports clk100]
create_clock -name clk200 -period 5.0 [get_ports clk200]
set decoders [get_cells -hierarchical -filter {NAME =~ *hold_output_decode* && REF_NAME == LUT2}]
if {[llength $decoders] != 272} {error "Expected 272 preserved decode LUTs, found [llength $decoders]"}
foreach cell $decoders {
 if {[string tolower [get_property INIT $cell]] ne {4'h6}} {error "Incorrect output decode $cell"}
}
set f [open [file join $out storage_mapping_audit.txt] w]
puts $f "PRESERVED_DECODERS=[llength $decoders]"
foreach cell $decoders {puts $f "[get_property NAME $cell]\t[get_property REF_NAME $cell]\t[get_property INIT $cell]"}
close $f
report_utilization -hierarchical -file [file join $out storage_mapping_utilization.rpt]
write_checkpoint [file join $out storage_mapping_synth.dcp]
puts {TIMING_MARGIN_INSPECT_PASS}
exit
