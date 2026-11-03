# Small real 32/128-bit interconnect with the mixed policy for the CURRENT route.
if {$argc != 7} {error {Use the isolated diagnostic runner}}
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 4
create_project fifo_probe [file join $out project] -part xck26-sfvc784-2LV-c
create_bd_design fifo_probe
set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 sc]
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1 CONFIG.NUM_CLKS 1] $sc
foreach {name width} {S00_AXI 32 M00_AXI 128} {
    make_bd_intf_pins_external [get_bd_intf_pins sc/$name]
    set_property -dict [list CONFIG.PROTOCOL AXI4 CONFIG.ADDR_WIDTH 32 CONFIG.DATA_WIDTH $width CONFIG.ID_WIDTH 1] [get_bd_intf_ports ${name}_0]
}
set clk [create_bd_port -dir I -type clk aclk]
set_property CONFIG.FREQ_HZ 100000000 $clk
set_property CONFIG.ASSOCIATED_BUSIF {S00_AXI_0:M00_AXI_0} $clk
connect_bd_net $clk [get_bd_pins sc/aclk]
set rst [create_bd_port -dir I -type rst aresetn]
set_property CONFIG.POLARITY ACTIVE_LOW $rst
connect_bd_net $rst [get_bd_pins sc/aresetn]
assign_bd_address
validate_bd_design
save_bd_design
set bd [get_files */fifo_probe.bd]
set_property synth_checkpoint_mode None $bd
generate_target all $bd
file copy {D:/github clone/feat-software/fpga/joint_lowlight_compact_d/scripts/targeted_fifo_mapping.py} [file join $out targeted_fifo_mapping.py]
set receipt [exec {C:/Users/wzh16/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe} -E -B \
    [file join $out targeted_fifo_mapping.py] probe $out]
set expected [dict get $receipt buffer_luts]
synth_design -top fifo_probe -part xck26-sfvc784-2LV-c -mode out_of_context
set brams [get_cells -hierarchical -filter {REF_NAME =~ RAMB*}]
set delays [get_cells -hierarchical -filter {NAME =~ *hold_payload_delay* && REF_NAME == LUT1}]
if {[llength $delays] != $expected || ![llength $brams]} {error {Targeted storage/output mapping did not survive synthesis}}
set f [open [file join $out targeted_mapping.tsv] w]
puts $f "name\tprimitive\tinit\tdont_touch"
foreach cell $delays {
    if {[string tolower [get_property INIT $cell]] ne {2'h2} || ![get_property DONT_TOUCH $cell]} {error {Invalid preserved identity LUT}}
    puts $f "[get_property NAME $cell]\tLUT1\t[get_property INIT $cell]\t[get_property DONT_TOUCH $cell]"
}
foreach cell $brams {puts $f "[get_property NAME $cell]\t[get_property REF_NAME $cell]\t-\t-"}
close $f
if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Black box in targeted probe}}
report_utilization -hierarchical -file [file join $out targeted_utilization.rpt]
write_checkpoint [file join $out targeted_probe_synth.dcp]
puts {TIMING_MARGIN_INSPECT_PASS}
exit
