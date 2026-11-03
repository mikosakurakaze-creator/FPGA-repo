open_checkpoint [file normalize [lindex $argv 0]]
puts [help place_design]
puts [help set_property]
set cells [get_cells -hierarchical -filter {REF_NAME == FDRE}]
puts "SMALL_DESIGN_FF=[llength $cells]"
set code [catch {place_design -unplace -cells [lrange $cells 0 0]} result]
puts "PARTIAL_UNPLACE_CODE=$code RESULT=$result"
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
