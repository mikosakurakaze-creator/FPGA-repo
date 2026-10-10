# Library only. No transport, connection, target selection, or automatic invocation.
# Real-board use remains unapproved. Caller must supply the established guarded
# transport and a fresh host/identity/configuration/quiescence gate.
namespace eval ::pmu_pl_candidate {variable used 0}
proc ::pmu_pl_candidate::run {approval read32 write32 waitms guard} {
    variable used
    if {$approval ne {MASTER_APPROVED_PMU_PL_WAKE_ONCE}} {error {EXPLICIT_MASTER_APPROVAL_REQUIRED}}
    if {$used} {error {ONE_ATTEMPT_ALREADY_CONSUMED}}
    set used 1
    {*}$guard
    set power [{*}$read32 0xFFD80100]
    set pending [{*}$read32 0xFFD80110]
    set mask_before [{*}$read32 0xFFD80114]
    set errors_before [{*}$read32 0xFFD80540]
    set reset_data [{*}$read32 0xFF0A0054]
    set reset_dir [{*}$read32 0xFF0A0344]
    set reset_enable [{*}$read32 0xFF0A0348]
    if {($power & 0x00800000)==0 || $pending!=0 || ($errors_before & 0x01000000)!=0 || ($reset_data & 0x80000000)!=0 || ($reset_dir & 0x80000000)==0 || ($reset_enable & 0x80000000)==0} {error {PRECONDITION_CHANGED_NO_WRITES}}
    # WO enable and trigger registers: direct one-bit writes; no RMW of WO data.
    # No power-down, DOMAIN_ISO_CNTRL, GPIO, reset, or clock register is written.
    {*}$guard
    {*}$write32 0xFFD80118 0x00800000
    set mask_after [{*}$read32 0xFFD80114]
    if {($mask_after & 0x00800000)!=0 || ($mask_before & 0xFF7FFFFF)!=($mask_after & 0xFF7FFFFF)} {error {INTERRUPT_ENABLE_VERIFY_FAILED_NO_TRIGGER}}
    {*}$guard
    {*}$write32 0xFFD80120 0x00800000
    set completed 0
    set deadline [expr {[clock milliseconds]+2000}]
    for {set i 0} {$i<20} {incr i} {
        {*}$guard
        set status [{*}$read32 0xFFD80110]
        if {($status & 0x00800000)==0} {set completed 1;break}
        if {[clock milliseconds]>=$deadline} {break}
        {*}$waitms 50
    }
    if {!$completed} {error {PMU_SERVICE_TIMEOUT_NO_RETRY}}
    set errors_after [{*}$read32 0xFFD80540]
    if {($errors_after & 0x01000000)!=0} {error {PMU_SERVICE_ERROR_NO_RETRY}}
    # At most two input observations; no functional AXI/MMIO or GPIO release.
    {*}$guard
    set signature0 [{*}$read32 0xFF0A006C]
    if {($signature0 & 0x40)==0} {return [dict create outcome SIGNATURE_STILL_ZERO writes 2 signature $signature0 isolation NOT_PROVED no_retry 1]}
    {*}$waitms 50
    {*}$guard
    set signature1 [{*}$read32 0xFF0A006C]
    if {($signature1 & 0x40)==0} {error {SIGNATURE_UNSTABLE_STOP}}
    return [dict create outcome EMIO_SIGNATURE_RESTORED writes 2 signature0 $signature0 signature1 $signature1 GPIO95 HELD_LOW clock_frequency NOT_MEASURED functional_tests NOT_STARTED]
}
