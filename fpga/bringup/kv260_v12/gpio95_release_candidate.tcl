# Offline proposal only: no connection, transport, or automatic invocation.
# guard must enforce the established current Host/identity/CONFIG/runtime/quiescence proof.
namespace eval ::gpio95_release_candidate {variable used 0}
proc ::gpio95_release_candidate::run {approval read32 write32 waitms guard} {
    variable used
    if {$approval ne {MASTER_APPROVED_GPIO95_RELEASE_ONCE}} {error {NEW_EXPLICIT_MASTER_APPROVAL_REQUIRED}}
    if {$used} {error {ONE_ATTEMPT_ALREADY_CONSUMED}}
    set used 1
    {*}$guard
    set data [{*}$read32 0xFF0A0054]
    set direction [{*}$read32 0xFF0A0344]
    set enable [{*}$read32 0xFF0A0348]
    set observation [{*}$read32 0xFF0A006C]
    if {($data&0x80000000)!=0 || ($direction&0x80000000)==0 || ($enable&0x80000000)==0 || ($observation&0xE2)!=0xE2 || ($observation&0x0C)!=0} {error {PRE_RELEASE_FABRIC_GATE_CHANGED_NO_WRITE}}
    {*}$guard
    # Bank5 MSW mask: all pins masked except MSW bit15 (=bank bit31/EMIO95).
    {*}$write32 0xFF0A002C 0x7FFF8000
    set data_after [{*}$read32 0xFF0A0054]
    set direction_after [{*}$read32 0xFF0A0344]
    set enable_after [{*}$read32 0xFF0A0348]
    if {$data_after!=($data|0x80000000) || $direction_after!=$direction || $enable_after!=$enable} {error {GPIO95_RELEASE_READBACK_FAILED_NO_RETRY}}
    set deadline [expr {[clock milliseconds]+2000}]
    for {set i 0} {$i<20} {incr i} {
        {*}$guard
        set word [{*}$read32 0xFF0A006C]
        if {($word&0xE2)!=0xE2} {error {OBSERVATION_CHAIN_CHANGED_AFTER_RELEASE_STOP}}
        if {($word&0x0C)==0x0C} {return [dict create outcome FABRIC_RESET_RELEASE_OBSERVED GPIO95_request HIGH interconnect_aresetn HIGH peripheral_aresetn HIGH observation $word writes 1 functional_MMIO NOT_STARTED]}
        if {[clock milliseconds]>=$deadline} {break}
        {*}$waitms 50
    }
    error {FABRIC_RESET_RELEASE_TIMEOUT_NO_RETRY_NO_ROLLBACK}
}
