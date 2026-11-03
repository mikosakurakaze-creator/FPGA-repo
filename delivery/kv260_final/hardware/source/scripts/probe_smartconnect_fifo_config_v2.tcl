# Generate a disposable SmartConnect and inspect the actual emitted node RTL.
if {$argc != 7} {error {Use the isolated diagnostic runner}}
set out [file normalize [lindex $argv 1]]
create_project fifo_probe [file join $out project] -part xck26-sfvc784-2LV-c
create_bd_design fifo_probe
set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 sc]
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1 CONFIG.NUM_CLKS 1] $sc
set_property CONFIG.ADVANCED_PROPERTIES {S00_Entry {R_REG 0 W_REG 0 AR_REG 0 AW_REG 0 B_REG 0} M00_Exit {R_REG 0 W_REG 0 AR_REG 0 AW_REG 0 B_REG 0}} $sc
foreach name {S00_AXI M00_AXI} {
    make_bd_intf_pins_external [get_bd_intf_pins sc/$name]
    set p [get_bd_intf_ports ${name}_0]
    set_property -dict [list CONFIG.PROTOCOL AXI4 CONFIG.ADDR_WIDTH 32 CONFIG.DATA_WIDTH 128 CONFIG.ID_WIDTH 1] $p
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
generate_target all [get_files */fifo_probe.bd]
set f [open [file join $out emitted_fifo_parameters.txt] w]
foreach file [get_files -all -filter {NAME =~ *.sv}] {
    set path [get_property NAME $file]
    if {![file exists $path]} {continue}
    set h [open $path r]; set content [read $h]; close $h
    foreach line [split $content \n] {
        if {[regexp {^\s*\.C_FIFO_(TYPE|SIZE|OUTPUT_REG|IP)\(} $line]} {puts $f "$path\t[string trim $line]"}
    }
}
close $f
puts {TIMING_MARGIN_INSPECT_PASS}
exit
