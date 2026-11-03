# Read-only capacity census. Same controls are a conservative sufficient rule;
# place_cell legality and routed timing still have to be checked separately.
set out [file normalize [lindex $argv 1]]
open_checkpoint [file normalize [lindex $argv 0]]
set by_site [dict create]
foreach cell [get_cells -hierarchical -filter {IS_PRIMITIVE == 1 && (REF_NAME =~ FD* || REF_NAME =~ LD*)}] {
    set loc [get_property LOC $cell]
    if {$loc ne {}} {dict lappend by_site $loc $cell}
}
set f [open [file join $out relocation_capacity.tsv] w]
puts $f "site_type\tff_status\tfree_lut_pair_slots\tall_empty_ff_slots\tsites"
set counts [dict create]
foreach site [get_sites -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}] {
    set controls {}
    set status empty
    if {[dict exists $by_site $site]} {
        set status homogeneous
        foreach cell [dict get $by_site $site] {
            if {[get_property REF_NAME $cell] ne {FDRE}} {set status other; break}
            set sig {}
            foreach pin {C CE R} {lappend sig [get_property NAME [get_nets -of_objects [get_pins $cell/$pin]]]}
            if {$controls eq {}} {set controls $sig} elseif {$sig ne $controls} {set status mixed; break}
        }
    }
    set pairs 0
    set slots 0
    foreach letter {A B C D E F G H} {
        set pair_free [expr {![get_property IS_USED [get_bels $site/${letter}5LUT]] && ![get_property IS_USED [get_bels $site/${letter}6LUT]]}]
        foreach suffix {FF FF2} {
            if {![get_property IS_USED [get_bels $site/${letter}${suffix}]]} {
                incr slots
                if {$pair_free} {incr pairs}
            }
        }
    }
    set key [list [get_property SITE_TYPE $site] $status]
    if {![dict exists $counts $key]} {dict set counts $key {0 0 0}}
    lassign [dict get $counts $key] p s n
    dict set counts $key [list [expr {$p+$pairs}] [expr {$s+$slots}] [expr {$n+1}]]
}
dict for {key values} $counts {puts $f "[join $key \t]\t[join $values \t]"}
close $f
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
