namespace eval ::single_frame {
    variable consumed 0
    variable phase LOCKED
    variable staging_pass 0
    variable completed {}
    variable active_ip {}
}
proc ::single_frame::file_bytes {path} {
    set f [open $path r];fconfigure $f -translation binary -encoding binary
    try {return [read $f]} finally {close $f}
}
proc ::single_frame::run {approval policy r32 w32 rb wb gate tick pause record} {
    variable consumed;variable phase;variable staging_pass;variable completed;variable active_ip
    if {$approval ne {MASTER_APPROVED_SINGLE_FRAME_ONCE} || $consumed} {error {APPROVAL_OR_ONCE_BUDGET_STOP}}
    # Consume before the first callback; an exception cannot authorize a replay.
    set consumed 1
    set phase CONTROL_PRE
    {*}$gate PRE
    foreach s [dict get $policy stages] {
        set ip [dict get $s ip];set base [dict get $s AP_CTRL]
        if {[{*}$r32 "CONTROL_PRE/$ip/AP" $base]!=4 || [{*}$r32 "CONTROL_PRE/$ip/GIE" [expr {$base+4}]]!=0} {error {PRE_STAGING_IDLE_OR_IRQ_GATE_STOP}}
    }
    set phase STAGING
    foreach region [dict get $policy regions] {
        set name [dict get $region name];set a [dict get $region address];set n [dict get $region bytes]
        set data [file_bytes [dict get $region file]]
        if {[string length $data]!=$n} {error {LOCAL_STAGING_LENGTH_STOP}}
        for {set off 0} {$off<$n} {incr off 65536} {
            set count [expr {min(65536,$n-$off)}]
            {*}$wb "STAGING/W/$name/$off" [expr {$a+$off}] [string range $data $off [expr {$off+$count-1}]]
        }
        for {set off 0} {$off<$n} {incr off 65536} {
            set count [expr {min(65536,$n-$off)}]
            set raw [{*}$rb "STAGING/R/$name/$off" [expr {$a+$off}] $count]
            if {[string length $raw]!=$count || $raw ne [string range $data $off [expr {$off+$count-1}]]} {error "DDR_STAGING_READBACK_MISMATCH $name $off"}
        }
    }
    set staging_pass 1
    {*}$record STAGING_PASS [dict create bytes 19025659]
    set outcomes {}
    foreach stage [dict get $policy stages] {
        set ip [dict get $stage ip];set active_ip $ip;set phase STAGE:$ip
        {*}$gate $ip
        set base [dict get $stage AP_CTRL]
        if {[{*}$r32 "STAGE:$ip/$ip/AP" $base]!=4 || [{*}$r32 "STAGE:$ip/$ip/GIE" [expr {$base+4}]]!=0} {error "STAGE_IDLE_OR_IRQ_GATE_STOP $ip"}
        set phase ARGS:$ip;set i 0
        foreach arg [dict get $stage argument_writes] {
            set a [dict get $arg address];set value [dict get $arg value]
            {*}$w32 "ARG/W/$ip/$i" $a $value
            if {[{*}$r32 "ARG/R/$ip/$i" $a]!=$value} {error "ARGUMENT_READBACK_MISMATCH $ip $i"}
            incr i
        }
        set phase START:$ip
        {*}$gate ${ip}_START
        set began [{*}$tick]
        {*}$w32 "START/$ip" $base 1
        set phase POLL:$ip;set done 0;set count 0;set last 0
        while {$count<100} {
            if {[{*}$tick]-$began>=5000} {error "IP_DEADLINE_STOP $ip"}
            incr count
            set last [{*}$r32 "POLL/$ip" $base]
            if {[{*}$tick]-$began>=5000} {error "IP_LATE_RETURN_STOP $ip"}
            if {$last&0x80} {error "UNEXPECTED_AUTORESTART_STOP $ip"}
            if {$last&2} {
                if {($last&5)!=4} {error "DONE_WITHOUT_IDLE_START_CLEAR_STOP $ip"}
                set done 1;break
            }
            {*}$pause 10
        }
        if {!$done} {error "IP_POLL_BUDGET_STOP $ip"}
        set elapsed [expr {[{*}$tick]-$began}]
        set phase OUTPUT:$ip
        set out [dict get $policy slots [dict get $stage output]]
        set a [dict get $out address];set n [dict get $out bytes];set raw {}
        for {set off 0} {$off<$n} {incr off 65536} {
            set count_bytes [expr {min(65536,$n-$off)}]
            set block [{*}$rb "OUTPUT/$ip/$off" [expr {$a+$off}] $count_bytes]
            if {[string length $block]!=$count_bytes} {error "OUTPUT_PARTIAL_STOP $ip"}
            append raw $block
        }
        set expected [file_bytes [dict get $out golden]]
        if {[string length $expected]!=$n || $raw ne $expected} {
            {*}$record OUTPUT_MISMATCH [dict create ip $ip bytes $n actual $raw]
            error "BIT_EXACT_MISMATCH_STOP $ip"
        }
        {*}$record OUTPUT_PASS [dict create ip $ip bytes $n actual $raw]
        set phase GUARDS:$ip
        foreach region [dict get $policy regions] {
            if {[dict get $region kind] eq {data}} {continue}
            set tag "GUARD/$ip/[dict get $region name]"
            set guard [{*}$rb $tag [dict get $region address] [dict get $region bytes]]
            if {$guard ne [file_bytes [dict get $region file]]} {error "GUARD_MISMATCH_STOP $ip [dict get $region name]"}
        }
        lappend completed $ip
        set outcome [dict create ip $ip poll_reads $count AP_CTRL $last elapsed_ms $elapsed bit_exact PASS guards PASS]
        lappend outcomes $outcome
        {*}$record STAGE_PASS $outcome
    }
    set phase FINAL
    {*}$gate FINAL
    return [dict create outcome SINGLE_FRAME_BIT_EXACT_PASS stages $outcomes starts 3 retry 0 BOARD_BRINGUP_BASE PASS BOARD_30FPS NOT_TESTED]
}
