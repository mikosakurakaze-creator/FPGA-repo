# Read-only device object discovery using a small OOC checkpoint.
set out [file normalize [lindex $argv 1]]
open_checkpoint [file normalize [lindex $argv 0]]
set f [open [file join $out bel_queries.txt] w]
foreach expression {{get_bels -quiet SLICE*/*6LUT} {get_bels -quiet -filter {TYPE =~ *LUT*}} {get_bels -quiet -filter {IS_OCCUPIED == 0}} {get_sites -quiet SLICE*}} {
    set objects [eval $expression]
    puts $f "$expression COUNT=[llength $objects] SAMPLE=[lrange $objects 0 4]"
}
set site [lindex [get_sites -quiet SLICE*] 0]
set bels [get_bels -quiet -of_objects $site]
puts $f "SITE=$site BELS=$bels"
foreach bel [lrange $bels 0 10] {
    puts $f "OBJECT=$bel"
    foreach prop [list_property $bel] {
        puts $f "  $prop=[get_property $prop $bel]"
    }
}
close $f
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
