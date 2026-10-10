# Host-only library. No connection, target selection or automatic invocation.
# Actual use requires new Master approval and the existing live guarded transport.
namespace eval ::gpio95_mode_candidate {variable used 0}
proc ::gpio95_mode_candidate::read_all {read32 guard {expected {}}} {
    set values {};set index 0
    foreach address {0xFF0A0054 0xFF0A0344 0xFF0A0348} {
        {*}$guard
        set word [{*}$read32 $address]
        if {![string is wideinteger -strict $word] || $word<0 || $word>0xFFFFFFFF} {error {INVALID_REGISTER_WORD_STOP}}
        if {$expected eq {}} {
            if {($word&0x80000000)!=0} {error {GPIO95_MODE_OR_LOW_PRECONDITION_CHANGED_NO_WRITES}}
        } elseif {$word!=[lindex $expected $index]} {
            error {REGISTER_READBACK_MISMATCH_STOP_NO_FURTHER_ACCESS}
        }
        lappend values $word
        incr index
    }
    return $values
}
proc ::gpio95_mode_candidate::run {approval read32 write32 guard} {
    variable used
    if {$approval ne {MASTER_APPROVED_GPIO95_DIRECTION_ENABLE_LOW_ONCE}} {error {NEW_MASTER_APPROVAL_REQUIRED}}
    if {$used} {error {ONCE_BUDGET_CONSUMED}}
    set used 1
    lassign [read_all $read32 $guard] data direction enable
    if {(($data|$direction|$enable)&0x80000000)!=0} {error {GPIO95_MODE_OR_LOW_PRECONDITION_CHANGED_NO_WRITES}}
    set direction_new [expr {$direction|0x80000000}]
    set enable_new [expr {$enable|0x80000000}]
    {*}$guard
    {*}$write32 0xFF0A0344 $direction_new
    lassign [read_all $read32 $guard [list $data $direction_new $enable]] data1 direction1 enable1
    if {$data1!=$data || $direction1!=$direction_new || $enable1!=$enable} {error {DIRECTION_VERIFY_FAILED_NO_ENABLE_WRITE}}
    {*}$guard
    {*}$write32 0xFF0A0348 $enable_new
    lassign [read_all $read32 $guard [list $data $direction_new $enable_new]] data2 direction2 enable2
    if {$data2!=$data || $direction2!=$direction_new || $enable2!=$enable_new} {error {OUTPUT_ENABLE_VERIFY_FAILED_NO_RETRY_NO_ROLLBACK}}
    return [dict create outcome GPIO95_MODE_CONFIGURED_OUTPUT_LOW writes 2 reads 9 DATA $data2 DIRM $direction2 OEN $enable2 other_bits PRESERVED PL_reset_delivery NOT_PROVED program NOT_STARTED]
}
