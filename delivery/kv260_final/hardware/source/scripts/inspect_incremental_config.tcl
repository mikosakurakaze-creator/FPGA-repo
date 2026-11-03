set out [file normalize [lindex $argv 1]]
open_checkpoint [file normalize [lindex $argv 0]]
help config_implementation
report_config_implementation
puts {AVAILABLE_INCREMENTAL_COMMANDS}
puts [lsort [info commands *increment*]]
puts [lsort [info commands *reuse*]]
puts [lsort [info commands *config*impl*]]
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
