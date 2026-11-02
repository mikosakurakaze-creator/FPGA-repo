# Explicit derivative of generated wrappers, using the vendor node's declared
# C_FIFO_OUTPUT_REG parameter. No vendor installation or encrypted RTL is edited.
# Regeneration must never silently restore the old parameter before synthesis.
proc apply_fifo_output_policy {root} {
    set original_root [file join $root fifo_generated_before]
    file mkdir $original_root
    set records {}
    set seen [dict create]
    foreach obj [get_files -all -quiet -filter {NAME =~ *.sv}] {
        set file [file normalize [get_property NAME $obj]]
        if {[dict exists $seen $file]} {continue}
        dict set seen $file 1
        if {[string first [string tolower "$root/"] [string tolower $file]]!=0 ||
            [string first {joint_system.gen/} $file]<0 || ![file isfile $file]} {continue}
        set f [open $file r]; set before [read $f]; close $f
        if {![regexp {sc_node_v1_0_[0-9]+_top\s*#\(} $before]} {continue}
        if {![regexp {\.C_FIFO_TYPE\(0\)} $before] || ![regexp {\.C_FIFO_SIZE\(5\)} $before]} {continue}
        if {[regexp -all {\.C_FIFO_OUTPUT_REG\(1\)} $before]!=1} {error "Unexpected generated FIFO output contract: $file"}
        set rel [string range $file [expr {[string length $root]+1}] end]
        set backup [file join $original_root $rel]
        file mkdir [file dirname $backup]
        file copy $file $backup
        set after [string map [list {.C_FIFO_OUTPUT_REG(1)} {.C_FIFO_OUTPUT_REG(0)} \
                                  {C_FIFO_OUTPUT_REG=1,} {C_FIFO_OUTPUT_REG=0,}] $before]
        set f [open $file w]; puts -nonewline $f $after; close $f
        lappend records [list $file $backup]
    }
    # Covers the five data SmartConnects, including arbitration and clock nodes;
    # command FIFOs with FIFO_SIZE=0 and FIFO_TYPE=2 are deliberately untouched.
    if {[llength $records]<100 || [llength $records]>160} {
        error "Unexpected generated FIFO source coverage: [llength $records]"
    }
    set f [open [file join $root fifo_output_override_records.list] w]
    puts $f $records
    close $f
    puts "FIFO_OUTPUT_OVERRIDE_FILES=[llength $records]"
    verify_fifo_output_policy $root
}

proc verify_fifo_output_policy {root} {
    set f [open [file join $root fifo_output_override_records.list] r]
    set records [read $f];close $f
    foreach record $records {
        lassign $record file backup
        set f [open $backup r];set before [read $f];close $f
        set f [open $file r];set after [read $f];close $f
        set expected [string map [list {.C_FIFO_OUTPUT_REG(1)} {.C_FIFO_OUTPUT_REG(0)} \
                                       {C_FIFO_OUTPUT_REG=1,} {C_FIFO_OUTPUT_REG=0,}] $before]
        if {$after ne $expected} {error "Generated FIFO override changed or was regenerated: $file"}
    }
    puts "FIFO_OUTPUT_OVERRIDE_VERIFIED=[llength $records]"
}
