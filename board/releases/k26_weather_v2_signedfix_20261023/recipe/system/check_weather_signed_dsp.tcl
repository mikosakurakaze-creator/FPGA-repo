# OPT_DESIGN POST hook; the PRE hook must have installed the exact check.
if {[llength [info commands weather_assert_signed_boundary]] != 1} {
    error {Weather DSP PRE hook did not execute; signed-boundary check unavailable}
}
weather_assert_signed_boundary
