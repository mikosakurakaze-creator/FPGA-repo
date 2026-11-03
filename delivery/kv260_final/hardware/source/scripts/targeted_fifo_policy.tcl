# Regenerated source policy derived only from the current passing routed build.
proc apply_fifo_output_policy {root} {
    puts [exec {C:/Users/wzh16/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe} \
        -E -B [file join $root targeted_fifo_mapping.py] apply $root]
}
proc verify_fifo_output_policy {root} {
    puts [exec {C:/Users/wzh16/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe} \
        -E -B [file join $root targeted_fifo_mapping.py] verify $root]
}
