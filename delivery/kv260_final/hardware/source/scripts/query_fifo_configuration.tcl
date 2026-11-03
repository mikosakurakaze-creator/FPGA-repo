# Read public SmartConnect configuration metadata; never modify an old project.
if {$argc != 7} {error {Use the isolated diagnostic runner}}
set out [file normalize [lindex $argv 1]]
create_project -in_memory -part xck26-sfvc784-2LV-c
create_bd_design fifo_configuration_probe
set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 sc]
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] $sc
set f [open [file join $out smartconnect_public_properties.txt] w]
report_property -all $sc -file [file join $out smartconnect_properties.rpt]
foreach spec {
    {S00_Entry {R_REG 0 W_REG 0 AR_REG 0 AW_REG 0 B_REG 0}}
    {S00_Entry {R_FIFO_OUTPUT_REG 0 W_FIFO_OUTPUT_REG 0}}
    {S00_Entry {FIFO_OUTPUT_REG 0}}
} {
    puts $f "TRY=$spec"
    set rc [catch {set_property CONFIG.ADVANCED_PROPERTIES $spec $sc} msg]
    puts $f "RETURN=$rc MESSAGE=$msg ACTUAL=[get_property CONFIG.ADVANCED_PROPERTIES $sc]"
}
close $f
puts {TIMING_MARGIN_INSPECT_PASS}
exit
