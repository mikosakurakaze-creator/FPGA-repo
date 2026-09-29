# Continue the reviewed routed KV260 V1.1 run through bitstream and XSA.
# Use `-tclargs preflight` to audit the saved route without generating either.
set repo_root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $repo_root fpga vivado three_module_integration_v1_1]
set project_file [file join $project_dir three_module_integration_v1_1.xpr]
set bd_file [file join $project_dir three_module_integration_v1_1.srcs sources_1 bd system system.bd]
set run_dir [file join $project_dir three_module_integration_v1_1.runs impl_1]
set routed_dcp [file join $run_dir system_wrapper_routed.dcp]
set bit_file [file join $run_dir system_wrapper.bit]
set output_dir {E:/HLS/vivado_three_module_v1_1_bitstream_xsa}
set xsa_file [file join $output_dir kv260_three_module_v1_1.xsa]
file mkdir $output_dir

proc read_all {path} {
    set f [open $path r]
    set contents [read $f]
    close $f
    return $contents
}

proc audit_routed {label output_dir} {
    set timing_file [file join $output_dir ${label}_timing_summary.rpt]
    set route_file [file join $output_dir ${label}_route_status.rpt]
    set drc_file [file join $output_dir ${label}_drc.rpt]
    set check_file [file join $output_dir ${label}_check_timing.rpt]
    report_timing_summary -file $timing_file
    report_route_status -file $route_file
    report_drc -file $drc_file
    check_timing -verbose -file $check_file

    set timing [read_all $timing_file]
    set summary_start [string first {| Design Timing Summary} $timing]
    set summary_end [string first {All user specified timing constraints are met.} $timing]
    if {$summary_start < 0 || $summary_end < $summary_start} {
        error "$label timing summary does not confirm constraints are met"
    }
    set summary [string range $timing $summary_start $summary_end]
    set found 0
    foreach line [split $summary "\n"] {
        set fields [regexp -all -inline {\S+} $line]
        if {[llength $fields] == 12 && [string is double -strict [lindex $fields 0]] &&
            [string is double -strict [lindex $fields 4]] &&
            [string is double -strict [lindex $fields 8]]} {
            lassign $fields wns tns setup_fail setup_total whs ths hold_fail hold_total wpws tpws pw_fail pw_total
            set found 1
            break
        }
    }
    if {!$found} {error "$label timing numbers could not be parsed"}
    puts "$label TIMING WNS=$wns TNS=$tns SETUP_FAIL=$setup_fail WHS=$whs THS=$ths HOLD_FAIL=$hold_fail WPWS=$wpws TPWS=$tpws PW_FAIL=$pw_fail"
    if {$wns ne {1.720} || $tns ne {0.000} || $setup_fail != 0 ||
        $whs ne {0.010} || $ths ne {0.000} || $hold_fail != 0 ||
        $wpws ne {3.500} || $tpws ne {0.000} || $pw_fail != 0} {
        error "$label timing differs from the reviewed route baseline"
    }

    set route [read_all $route_file]
    foreach {key pattern expected} {
        ROUTABLE {# of routable nets[. ]*:[[:space:]]*([0-9]+)} 57441
        FULLY_ROUTED {# of fully routed nets[. ]*:[[:space:]]*([0-9]+)} 57441
        ROUTING_ERRORS {# of nets with routing errors[. ]*:[[:space:]]*([0-9]+)} 0
    } {
        if {![regexp $pattern $route -> actual] || $actual != $expected} {
            error "$label route check failed: $key expected $expected, got '$actual'"
        }
        puts "$label $key=$actual"
    }
    set drc [read_all $drc_file]
    if {[regexp -line {^\|[^|]+\|[ \t]*(Error|Critical Warning)[ \t]*\|} $drc]} {
        error "$label DRC contains Error or Critical Warning"
    }
    puts "$label DRC_BLOCKERS=0"
    set checks [read_all $check_file]
    if {![regexp {checking no_clock \(0\)} $checks] ||
        ![regexp {checking unconstrained_internal_endpoints \(0\)} $checks]} {
        error "$label contains an unchecked clock or unconstrained internal endpoint"
    }
    puts "$label TIMING_CONSTRAINT_CHECK=PASS"
}

foreach path [list $project_file $bd_file $routed_dcp] {
    if {![file isfile $path]} {error "Required routed V1.1 file is missing: $path"}
}
cd $project_dir
open_project $project_file
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c} ||
    [get_property BOARD_PART [current_project]] ne {xilinx.com:kv260_som:part0:1.4} ||
    [get_property TOP [get_filesets sources_1]] ne {system_wrapper}} {
    error {Unexpected board, part, or synthesis top}
}
set synth [get_runs synth_1]
set impl [get_runs impl_1]
puts "SYNTH_STATUS=[get_property STATUS $synth] PROGRESS=[get_property PROGRESS $synth]"
puts "IMPL_STATUS_BEFORE=[get_property STATUS $impl] PROGRESS=[get_property PROGRESS $impl]"
if {[get_property STATUS $synth] ne {synth_design Complete!} ||
    [get_property PROGRESS $synth] ne {100%} ||
    [get_property STATUS $impl] ne {route_design Complete!} ||
    [get_property PROGRESS $impl] ne {100%}} {
    error {The saved synthesis or routed implementation is not complete}
}
set routed_mtime [file mtime $routed_dcp]
puts "ROUTED_DCP=$routed_dcp MTIME_EPOCH=$routed_mtime"
open_run impl_1
audit_routed PRE_BITSTREAM $output_dir
close_design

if {[lsearch -exact $argv preflight] >= 0} {
    puts {PREFLIGHT_ONLY=PASS}
    close_project
    exit
}

puts "BITSTREAM_START_EPOCH=[clock seconds]"
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
puts "BITSTREAM_DONE_EPOCH=[clock seconds]"
set impl_status [get_property STATUS $impl]
set impl_progress [get_property PROGRESS $impl]
puts "BITSTREAM_STATUS=$impl_status PROGRESS=$impl_progress"
if {$impl_status ne {write_bitstream Complete!} || $impl_progress ne {100%}} {
    error "Bitstream run did not complete: $impl_status ($impl_progress)"
}
if {![file isfile $bit_file]} {error "Missing bitstream: $bit_file"}
if {[file mtime $routed_dcp] != $routed_mtime} {
    error {Routed checkpoint was modified during the bitstream step; audit before export}
}
puts "BITSTREAM_PATH=$bit_file BYTES=[file size $bit_file] MTIME_EPOCH=[file mtime $bit_file]"

open_run impl_1
audit_routed POST_BITSTREAM $output_dir
open_bd_design $bd_file
foreach {cell vlnv} {
    zero_dce_cnn_top_0 xilinx.com:hls:zero_dce_cnn_top:1.0
    bilinear_fixed16_buffered_0 xilinx.com:hls:bilinear_fixed16_buffered:1.0
    curve_image_fixed16_0 xilinx.com:hls:curve_image_fixed16:1.0
} {
    set obj [get_bd_cells $cell]
    if {[llength $obj] != 1 || [get_property VLNV $obj] ne $vlnv} {
        error "HLS IP differs from reviewed BD: $cell"
    }
    puts "BD_IP=$cell VLNV=[get_property VLNV $obj]"
}
foreach {name offset} {
    SEG_bilinear_fixed16_buffered_0_Reg 0xA0000000
    SEG_curve_image_fixed16_0_Reg 0xA0010000
    SEG_zero_dce_cnn_top_0_Reg 0xA0020000
} {
    set seg [get_bd_addr_segs zynq_ultra_ps_e_0/Data/$name]
    if {[llength $seg] != 1 ||
        [expr {[get_property OFFSET $seg] != $offset}] ||
        [expr {[get_property RANGE $seg] != 0x10000}]} {
        error "Control address mismatch: $name"
    }
    puts "CONTROL_ADDR=$name OFFSET=[get_property OFFSET $seg] RANGE=[get_property RANGE $seg]"
}
puts "XSA_START_EPOCH=[clock seconds]"
write_hw_platform -fixed -include_bit -force -file $xsa_file
puts "XSA_DONE_EPOCH=[clock seconds]"
if {![file isfile $xsa_file]} {error "Missing XSA: $xsa_file"}
puts "XSA_PATH=$xsa_file BYTES=[file size $xsa_file] MTIME_EPOCH=[file mtime $xsa_file]"
close_project
exit
