set transfer_used {};set transfer_seq 0;set get_count 0;set set_count 0
set get_bytes 0;set set_bytes 0;set start_attempts {};set parameter_attempts 0
set ddr_set_bytes 0;set csr_set_bytes 0
set gate_done {};set argument_cursor {};set argument_read_cursor {};set gate_observation_ms 0
set map_registered {};set map_cleanup {};set map_verified 0

proc validate_transfer {direction tag address word count raw} {
    global sf_policy transfer_used armed ctx exactContext gate_observation_ms gate_done
    global parameter_attempts start_attempts argument_cursor argument_read_cursor
    if {!$armed || $ctx ne $exactContext || $count<1 || $count>65536 || $word ni {1 4} || $address%$word || $count%$word} {error {TRANSFER_CONTEXT_SIZE_OR_ALIGNMENT_STOP}}
    set bank [expr {$direction eq {GET} ? {gets} : {sets}}]
    if {![dict exists $sf_policy $bank $tag]} {error "TRANSFER_NOT_WHITELISTED $tag"}
    set p [dict get $sf_policy $bank $tag]
    foreach {key actual} [list address $address word $word bytes $count] {
        if {[dict get $p $key]!=$actual} {error "TRANSFER_RANGE_OR_SIZE_STOP $tag"}
    }
    if {[dict get $p phase] ne $::single_frame::phase} {error "TRANSFER_PHASE_STOP $tag"}
    set key $direction/$tag
    set used [expr {[dict exists $transfer_used $key] ? [dict get $transfer_used $key] : 0}]
    if {$used>=[dict get $p limit]} {error "TRANSFER_ONCE_OR_BOUND_STOP $tag"}
    if {$direction eq {SET}} {
        if {[string length $raw]!=$count} {error {SET_LENGTH_STOP}}
        if {[dict exists $p value]} {
            binary scan $raw iu value
            if {$value!=[dict get $p value]} {error {EXACT_CSR_VALUE_STOP}}
        } else {
            set f [open [dict get $p file] r];fconfigure $f -translation binary -encoding binary
            try {seek $f [dict get $p offset];set expected [read $f $count]} finally {close $f}
            if {$raw ne $expected} {error {EXACT_DDR_PAYLOAD_STOP}}
        }
    }
    if {[string match ARG/* $tag]} {
        set ip [dict get $p ip];set i [dict get $p index]
        set wc [expr {[dict exists $argument_cursor $ip] ? [dict get $argument_cursor $ip] : 0}]
        set rc [expr {[dict exists $argument_read_cursor $ip] ? [dict get $argument_read_cursor $ip] : 0}]
        if {!$::single_frame::staging_pass || $::single_frame::active_ip ne $ip ||
            ($direction eq {SET} && ($i!=$wc || $rc!=$wc)) ||
            ($direction eq {GET} && ($i!=$rc || $wc!=$rc+1))} {error {ARGUMENT_ORDER_STOP}}
    }
    if {[string match START/* $tag]} {
        set ip [dict get $p ip]
        set index [lsearch -exact {cnn bilinear curve} $ip]
        set expected_count [lindex {14 6 7} $index]
        if {!$::single_frame::staging_pass || $::single_frame::active_ip ne $ip ||
            [llength $::single_frame::completed]!=$index ||
            ![dict exists $argument_cursor $ip] || [dict get $argument_cursor $ip]!=$expected_count ||
            ![dict exists $argument_read_cursor $ip] || [dict get $argument_read_cursor $ip]!=$expected_count ||
            ![dict exists $gate_done ${ip}_START] || [clock milliseconds]-$gate_observation_ms>5000} {error {START_DEPENDENCY_OR_FRESHNESS_STOP}}
    }
    verify_memory_map
    identity_guard
    # Attempt budgets are consumed before dispatch, including failed transfers.
    dict set transfer_used $key [expr {$used+1}]
    if {[string match ARG/* $tag]} {
        if {$direction eq {SET}} {dict incr argument_cursor $ip;incr parameter_attempts} else {dict incr argument_read_cursor $ip}
    }
    if {[string match START/* $tag]} {dict set start_attempts [dict get $p ip] 1}
}
proc transfer {direction tag address word count {data {}}} {
    global chan ctx run transfer_seq get_count set_count get_bytes set_bytes table ddr_set_bytes csr_set_bytes
    validate_transfer $direction $tag $address $word $count $data
    incr transfer_seq
    set begin [clock milliseconds];set bm [mono]
    set name [format %05d_%s.bin $transfer_seq [string tolower $direction]]
    set path [file join $run memory $name]
    if {$direction eq {SET}} {
        write_bin $path $data;incr set_count;incr set_bytes $count
        if {[string match STAGING/W/* $tag]} {incr ddr_set_bytes $count} else {incr csr_set_bytes $count}
    } else {incr get_count}
    emit [dict create event ${direction}_ATTEMPT seq $transfer_seq tag $tag phase $::single_frame::phase address [format 0x%08X $address] word $word bytes $count mode 24 context $ctx start_epoch_ms $begin start_mono_ns $bm payload_file [expr {$direction eq {SET} ? $name : {}}]]
    if {$direction eq {GET}} {
        set response [::tcf::send_command $chan Memory get {siiii} {Bea{o{msg o{} A}}} [list $ctx $address $word $count 24]]
        if {[llength $response]!=3 || [lindex $response 1] ne {} || [lindex $response 2] ne {} || [string length [lindex $response 0]]!=$count} {
            emit [dict create event GET_ERROR tag $tag response $response];error {GET_FAILED_OR_PARTIAL_NO_RETRY}
        }
        set data [lindex $response 0];write_bin $path $data;incr get_bytes $count
    } else {
        set response [::tcf::send_command $chan Memory set {siiiiB} {ea{o{msg o{} A}}} [list $ctx $address $word $count 24 $data]]
        if {[llength $response]!=2 || [lindex $response 0] ne {} || [lindex $response 1] ne {}} {
            emit [dict create event SET_ERROR tag $tag response $response];error {SET_FAILED_NO_RETRY}
        }
    }
    set end [clock milliseconds];set em [mono]
    emit [dict create event ${direction}_RETURN seq $transfer_seq tag $tag address [format 0x%08X $address] bytes $count return_epoch_ms $end return_mono_ns $em file $name]
    puts $table "$transfer_seq\t$direction\t$tag\t[format 0x%08X $address]\t$word\t$count\t$begin\t$end\t$bm\t$em\t$name";flush $table
    return $data
}
proc sf_r32 {tag address} {set raw [transfer GET $tag $address 4 4];binary scan $raw iu value;return $value}
proc sf_w32 {tag address value} {transfer SET $tag $address 4 4 [binary format iu $value]}
proc sf_rb {tag address count} {return [transfer GET $tag $address 1 $count]}
proc sf_wb {tag address data} {transfer SET $tag $address 1 [string length $data] $data}
proc tick_ms {} {return [expr {[mono]/1000000}]}

proc verify_memory_map {} {
    global sf_policy chan ctx exactContext
    if {$ctx ne $exactContext || [::xsdb::getcurtarget] ne $ctx || ![dict exists $::xsdb::memmaptable $chan $ctx]} {error {METADATA_CONTEXT_STOP}}
    set actual [dict get $::xsdb::memmaptable $chan $ctx]
    if {[dict size $actual]!=[dict size [dict get $sf_policy maps]]} {error {METADATA_REGION_COUNT_STOP}}
    dict for {a p} [dict get $sf_policy maps] {
        if {![dict exists $actual $a] || [llength [dict get $actual $a]]!=1} {error {METADATA_REGION_ID_STOP}}
        set row [lindex [dict get $actual $a] 0]
        if {[lsort [dict keys $row]] ne [lsort {Addr Size Flags Alignment Offs}]} {error {METADATA_FIELDS_STOP}}
        foreach {field expected} [list Addr $a Size [dict get $p size] Flags [dict get $p flags] Alignment [dict get $p alignment] Offs 0] {
            if {[dict get $row $field]!=$expected} {error {METADATA_PERMISSION_RANGE_STOP}}
        }
    }
}
proc register_memory_map {} {
    global sf_policy chan ctx targetID map_registered map_verified
    identity_guard;::xsdb::targets $targetID
    if {[::xsdb::getcurtarget] ne $ctx || ([dict exists $::xsdb::memmaptable $chan $ctx] && [dict size [dict get $::xsdb::memmaptable $chan $ctx]]!=0)} {error {FRESH_METADATA_CONTEXT_STOP}}
    dict for {a p} [dict get $sf_policy maps] {
        lappend map_registered $a
        ::xsdb::memmap -addr $a -size [dict get $p size] -flags [dict get $p flags] -alignment [dict get $p alignment]
        emit [dict create event MAP_ADD address $a properties $p board_write 0]
    }
    verify_memory_map;set map_verified 1
    emit [dict create event MAP_VERIFIED region_count [llength $map_registered] board_write 0 force 0]
}
proc clear_memory_map {} {
    global chan ctx map_registered map_cleanup
    if {![llength $map_registered]} {return}
    if {[::xsdb::getcurtarget] ne $ctx} {error {MAP_CLEANUP_CONTEXT_STOP}}
    foreach a $map_registered {
        if {![dict exists $::xsdb::memmaptable $chan $ctx $a]} {continue}
        set rc [catch {::xsdb::memmap -addr $a -clear} value options]
        lappend map_cleanup [dict create address $a return_code $rc result $value]
        emit [dict create event MAP_CLEAR address $a return_code $rc board_write 0 retry 0]
    }
    if {[dict exists $::xsdb::memmaptable $chan $ctx] && [dict size [dict get $::xsdb::memmaptable $chan $ctx]]!=0} {error {MAP_CLEANUP_NOT_EMPTY}}
    foreach item $map_cleanup {if {[dict get $item return_code]} {error {MAP_CLEANUP_FAILED}}
    }
}

proc sf_record {event value} {
    global run
    if {[dict exists $value actual]} {
        set ip [dict get $value ip]
        write_bin [file join $run ${ip}_actual.bin] [dict get $value actual]
        dict unset value actual
    }
    emit [dict merge [dict create event $event] $value]
}
