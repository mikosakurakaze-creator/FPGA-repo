# Disposable real SmartConnect. Use the vendor minimum BRAM depth (2^9).
# Failed XPM-memory backend attempts are retained in mapping01/02. Probe the
# vendor-declared XPM FIFO backend (FIFO_IP=2), not a private RTL substitution.
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
set seen [dict create]
set records {}
foreach obj [get_files -all -quiet -filter {NAME =~ *.sv}] {
    set path [file normalize [get_property NAME $obj]]
    if {[dict exists $seen $path] || ![file isfile $path]} {continue}
    dict set seen $path 1
    set f [open $path r];set before [read $f];close $f
    if {![regexp {sc_node_v1_0_[0-9]+_top\s*#\(} $before]} {continue}
    if {![regexp {\.C_FIFO_TYPE\(0\)} $before] || ![regexp {\.C_FIFO_SIZE\(5\)} $before]} {continue}
    # Vendor assertions 500-5/500-6 require address/response channels to stay
    # LUTRAM with pointer <=5. BRAM is valid only for R/W payload channels.
    if {![regexp {\.C_CHANNEL\([01]\)} $before]} {continue}
    if {[regexp -all {\.C_FIFO_OUTPUT_REG\(1\)} $before] != 1} {error {Unexpected probe output contract}}
    set backup [file join $out before [file tail [file dirname $path]] [file tail $path]]
    file mkdir [file dirname $backup]
    file copy $path $backup
    set after [string map [list {.C_FIFO_TYPE(0)} {.C_FIFO_TYPE(1)} {C_FIFO_TYPE=0,} {C_FIFO_TYPE=1,} \
        {.C_FIFO_SIZE(5)} {.C_FIFO_SIZE(9)} {C_FIFO_SIZE=5,} {C_FIFO_SIZE=9,} \
        {.C_FIFO_IP(0)} {.C_FIFO_IP(2)} {C_FIFO_IP=0,} {C_FIFO_IP=2,}] $before]
    set f [open $path w];puts -nonewline $f $after;close $f
    lappend records [list $path $backup]
}
if {[llength $records] != 4} {error "Expected R/W channel pairs, found [llength $records] files"}
set f [open [file join $out bram_probe_sources.list] w];puts $f $records;close $f
synth_design -top fifo_probe -part xck26-sfvc784-2LV-c -mode out_of_context
set brams [get_cells -hierarchical -filter {REF_NAME =~ RAMB*}]
set f [open [file join $out bram_mapping.tsv] w]
puts $f "name\tprimitive\tdoa_reg\tdob_reg"
foreach cell $brams {
    puts $f "[get_property NAME $cell]\t[get_property REF_NAME $cell]\t[get_property DOA_REG $cell]\t[get_property DOB_REG $cell]"
}
close $f
if {![llength $brams]} {error {C_FIFO_TYPE=BRAM did not infer any block RAM}}
if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Probe contains black boxes}}
report_utilization -hierarchical -file [file join $out bram_utilization.rpt]
write_checkpoint [file join $out bram_probe_synth.dcp]
puts {TIMING_MARGIN_INSPECT_PASS}
exit
