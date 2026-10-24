if {$argc!=2} {error {Expected DCP and output netlist}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite exported netlist}}
open_checkpoint $checkpoint
puts "GDN_NETLIST_DESIGN=[get_property NAME [current_design]]"
write_verilog -mode funcsim $output
puts {GDN_CORE_NETLIST_EXPORT_PASS}
close_design
exit
