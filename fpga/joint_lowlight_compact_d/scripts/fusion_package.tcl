if {$argc != 2} {error {Expected source file and new package directory}}
set source [file normalize [lindex $argv 0]]
set root [file normalize [lindex $argv 1]]
file mkdir $root
create_project fusion_package [file join $root project] -part xck26-sfvc784-2LV-c
set_property source_mgmt_mode None [current_project]
read_verilog [list $source]
set_property top joint_fusion [current_fileset]
ipx::package_project -root_dir [file join $root ip] -vendor joint.local -library rtl -taxonomy /UserIP -import_files -set_current true
set core [ipx::current_core]
set_property name joint_fusion $core
set_property version 1.0 $core
set_property core_revision 2 $core
set_property display_name {Joint RGB Q14 three-way fusion} $core
set_property description {Fixed 1272x720 RGB NCHW signed Q14 fusion; full 32-bit Q15 weight validation, start snapshots, i64 RNE and final clamp. Production SCALAR_COUNT must be 2747520.} $core
puts "INFERRED_BUSES [get_property NAME [ipx::get_bus_interfaces -of_objects $core]]"
foreach name {s_axi_control m_axi_gmem ap_clk ap_rst_n} {
    if {[llength [ipx::get_bus_interfaces $name -of_objects $core]] != 1} {error "Missing inferred interface $name"}
}
ipx::associate_bus_interfaces -busif s_axi_control -clock ap_clk $core
ipx::associate_bus_interfaces -busif m_axi_gmem -clock ap_clk $core
set clk [ipx::get_bus_interfaces ap_clk -of_objects $core]
# Leave FREQ_HZ to BD propagation, as in the frozen HLS IPs. A fixed nominal
# 100 MHz blocks connection to the PS divider's actual 99,999,001 Hz clock.
set p [ipx::add_bus_parameter ASSOCIATED_RESET $clk]
set_property value ap_rst_n $p
set rst [ipx::get_bus_interfaces ap_rst_n -of_objects $core]
set p [ipx::add_bus_parameter POLARITY $rst]
set_property value ACTIVE_LOW $p

set slave [ipx::get_bus_interfaces s_axi_control -of_objects $core]
foreach {name value} {PROTOCOL AXI4LITE DATA_WIDTH 32 ADDR_WIDTH 7} {
    set p [ipx::add_bus_parameter $name $slave];set_property value $value $p
}
set map [ipx::get_memory_maps s_axi_control -of_objects $core]
if {![llength $map]} {set map [ipx::add_memory_map s_axi_control $core]}
set_property slave_memory_map_ref s_axi_control $slave
foreach block [ipx::get_address_blocks -of_objects $map] {ipx::remove_address_block [get_property NAME $block] $map}
set block [ipx::add_address_block Reg $map]
set_property range 128 $block
set_property width 32 $block
set_property usage register $block
foreach {name offset access} {
    AP_CTRL 0 read-write GIE 4 read-write IER 8 read-write ISR 12 read-write
    AP_RETURN 16 read-only I_LOW 24 read-write I_HIGH 28 read-write
    L_LOW 36 read-write L_HIGH 40 read-write D_LOW 48 read-write D_HIGH 52 read-write
    O_LOW 60 read-write O_HIGH 64 read-write W_I 72 read-write W_L 80 read-write
    W_D 88 read-write COOKIE 96 read-write FRAME_ID 104 read-write
    COMPLETED_FRAME 112 read-only ACTIVE_FRAME 116 read-only
} {
    set reg [ipx::add_register $name $block]
    set_property address_offset $offset $reg
    set_property size 32 $reg
    set_property access $access $reg
}
set master [ipx::get_bus_interfaces m_axi_gmem -of_objects $core]
foreach {name value} {PROTOCOL AXI4 DATA_WIDTH 32 ADDR_WIDTH 64 MAX_BURST_LENGTH 1 NUM_READ_OUTSTANDING 1 NUM_WRITE_OUTSTANDING 1} {
    set p [ipx::add_bus_parameter $name $master];set_property value $value $p
}
set space [ipx::get_address_spaces m_axi_gmem -of_objects $core]
if {![llength $space]} {set space [ipx::add_address_space m_axi_gmem $core]}
set_property range 2147483648 $space
set_property width 32 $space
set_property master_address_space_ref m_axi_gmem $master
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::save_core $core
ipx::check_integrity $core
ipx::archive_core [file join $root joint_fusion_ip.zip] $core
puts {FUSION_IP_PACKAGE_PASS}
close_project
exit
