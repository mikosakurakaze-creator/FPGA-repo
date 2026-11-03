# Independently reopen the new synthesis and examine actual hardware mapping.
if {$argc != 7} {error {Use the isolated diagnostic runner}}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
open_checkpoint $checkpoint
set f [open [file join $out fifo_synthesis_mapping.txt] w]
foreach {name period} {clk_pl_0 10.0 clk_pl_1 5.0} {
    set clock [get_clocks $name]
    if {[llength $clock]!=1 || abs([get_property PERIOD $clock]-$period)>0.001} {
        error "Unexpected effective clock: $name"
    }
    puts $f "CLOCK=$name PERIOD_NS=[get_property PERIOD $clock]"
}
set decoders [get_cells -hierarchical -filter {NAME =~ *hold_output_decode* && REF_NAME == LUT2}]
puts $f "PRESERVED_OUTPUT_DECODERS=[llength $decoders]"
if {[llength $decoders]<2000} {error {Missing derived memory output decoders}}
set counts [dict create]
foreach cell $decoders {
    set name [get_property NAME $cell]
    if {[string tolower [get_property INIT $cell]] ne {4'h6}} {error "Decoder function changed: $name"}
    set top [lindex [split $name /] 1]
    dict incr counts $top
}
dict for {top count} $counts {puts $f "DECODE_GROUP=$top COUNT=$count"}
foreach top {compact_d_top_0 zero_dce_cnn_top_0 joint_rgb8_prepare_0} {
    if {![dict exists $counts $top]} {error "Missing changed storage group $top"}
}
set remaining 0
foreach top {cnn_data_sc cnn_model_sc bilinear_ddr_sc curve_ddr_sc} {
    set registers [get_cells -hierarchical -quiet -filter "NAME =~ system_i/$top/*gen_rf_narrow_reg*doutb_reg_reg* && REF_NAME == FDRE"]
    puts $f "SMARTCONNECT=$top OLD_PACKED_OUTPUT_REGISTERS=[llength $registers]"
    incr remaining [llength $registers]
}
puts $f "OLD_PACKED_SMARTCONNECT_OUTPUT_REGISTERS=$remaining"
close $f
# Do not silently proceed if the generic override retained the problematic bank.
if {$remaining} {error {SmartConnect output generic did not remove the old packed register bank}}
if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Synthesis contains black boxes}}
report_utilization -file [file join $out synthesis_utilization.rpt]
report_clocks -file [file join $out synthesis_clocks.rpt]
write_xdc -exclude_physical [file join $out synthesis_constraints.xdc]
puts {TIMING_MARGIN_INSPECT_PASS}
exit
