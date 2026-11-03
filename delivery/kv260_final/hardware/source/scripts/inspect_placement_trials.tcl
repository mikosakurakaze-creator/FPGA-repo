set out [file normalize [lindex $argv 1]]
puts [help place_cell]
puts [help set_msg_config]
puts [help reset_msg_config]
puts "LOG_COMMANDS=[info commands *log*]"
puts "REDIRECT_COMMANDS=[info commands *redirect*]"
puts {TIMING_MARGIN_INSPECT_PASS}
exit
