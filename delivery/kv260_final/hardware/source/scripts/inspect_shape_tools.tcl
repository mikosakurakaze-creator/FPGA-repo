# Tool capability query only: no checkpoint or project content is modified.
set out [file normalize [lindex $argv 1]]
set f [open [file join $out shape_tools.txt] w]
foreach pattern {*shape* *unpack* *macro* *unplace* *clock_region*} {
    puts $f "COMMANDS $pattern = [info commands $pattern]"
}
foreach command {unplace_cell delete_macros get_macros get_clock_regions phys_opt_design place_cell update_design opt_design} {
    puts "CAPABILITY_HELP=$command"
    if {[llength [info commands $command]]} {puts [help $command]}
}
close $f
puts {TIMING_MARGIN_INSPECT_PASS}
exit
