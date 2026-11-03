# Isolated analysis first; physical experiments must keep original clock periods.
if {$argc ni {5 6 7}} {error {Expected checkpoint, output, stage, setup margin, hold margin, optional strategy/reference}}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set stage [lindex $argv 2]
set setup_margin [lindex $argv 3]
set hold_margin [lindex $argv 4]
set strategy [expr {$argc >= 6 ? [lindex $argv 5] : {reroute}}]
set reference [expr {$argc == 7 ? [lindex $argv 6] : {}}]
set resume_physical [file exists [file join $out resume_physical.dcp]]
set resume_initial_route [file exists [file join $out resume_initial_route.marker]]
if {$strategy ni {reroute preplace preplace_fresh preplace_hold preplace_relocate preplace_fifo_logic}} {error {Unknown physical strategy}}
set_param general.maxThreads 8
set_param logicopt.enableDSPCascadeFixing false

puts [help phys_opt_design]
puts [help route_design]
puts [help set_clock_uncertainty]
if {$stage eq {help}} {
    puts {TIMING_MARGIN_HELP_PASS}
    exit
}
open_checkpoint $checkpoint
write_xdc -force [file join $out baseline_constraints.xdc]
report_clocks -file [file join $out baseline_clocks.rpt]
report_timing -delay_type max -max_paths 40 -nworst 1 -path_type full_clock_expanded \
    -file [file join $out baseline_setup_paths.rpt]
report_timing -delay_type min -max_paths 40 -nworst 1 -path_type full_clock_expanded \
    -file [file join $out baseline_hold_paths.rpt]
set f [open [file join $out baseline_clock_properties.txt] w]
foreach clock [get_clocks] {
    puts $f "CLOCK $clock"
    foreach property [list_property $clock] {
        puts $f "$property=[get_property $property $clock]"
    }
}
close $f
set f [open [file join $out baseline_path_summary.txt] w]
foreach type {max min} {
    foreach path [get_timing_paths -delay_type $type -max_paths 40 -nworst 1] {
        puts $f "$type SLACK=[get_property SLACK $path] START=[get_property STARTPOINT_PIN $path] END=[get_property ENDPOINT_PIN $path]"
    }
}
close $f
if {$stage in {optimize implement}} {
    # This experiment only accepts the reviewed two-clock checkpoint, which has
    # no user uncertainty. Add a stricter optimisation target, then restore zero
    # user uncertainty without touching the intrinsic jitter or clock periods.
    if {$setup_margin <= 0 || $hold_margin <= 0} {error {Margins must be positive}}
    set clocks [get_clocks]
    if {[lsort $clocks] ne {clk_pl_0 clk_pl_1}} {error {Unexpected clock set}}
    if {[get_property PERIOD [get_clocks clk_pl_0]] != 10.0 ||
        [get_property PERIOD [get_clocks clk_pl_1]] != 5.0} {error {Clock periods changed}}
    set f [open [file join $out baseline_constraints.xdc] r]
    set baseline_xdc [read $f]
    close $f
    if {[regexp -line {^\s*set_clock_uncertainty\s} $baseline_xdc]} {
        error {Baseline has user uncertainty; this experiment requires an explicit additive/restoration policy}
    }
    if {$stage eq {implement}} {
        if {$reference eq {} || $strategy ni {preplace preplace_fresh preplace_hold preplace_relocate preplace_fifo_logic}} {error {Missing implementation reference/strategy}}
        if {$resume_physical} {
            puts {TIMING_MARGIN_PHASE=resume_retained_physopt}
            close_design
            open_checkpoint [file join $out resume_physical.dcp]
            write_xdc [file join $out resumed_constraints.xdc]
        } else {
            puts {TIMING_MARGIN_PHASE=logic_optimization}
            opt_design
            write_checkpoint [file join $out logic_optimized_candidate.dcp]
        }
        if {$resume_physical} {
            if {$strategy ne {preplace_relocate}} {error {Unexpected physical resume strategy}}
        } elseif {$strategy eq {preplace_fresh}} {
            # Structural FIFO changes exceed the old incremental placer's
            # legal local-search envelope. Keep the reference for comparison
            # only and let the native placer assign all new positions.
            puts {TIMING_MARGIN_REFERENCE_ROLE=comparison_only_fresh_placement}
        } elseif {$strategy eq {preplace_fifo_logic}} {
            # Incremental placement explicitly prioritizes reused placement
            # over new Pblock boundaries (Place 46-12). Use a fresh placement
            # for this structural physical change; the audited old DCP is
            # retained for identity/timing/resource comparison only.
            puts {TIMING_MARGIN_REFERENCE_ROLE=comparison_only_fresh_placement}
            source [file join $out fifo_hold_floorplan.tcl]
            prepare_fifo_floorplan $out
        } else {
            read_checkpoint -incremental $reference
        }
    }
    # opt_design can replace clock objects. Resolve them again rather than
    # reusing handles captured before the netlist transformation.
    set clocks [get_clocks]
    puts "TIMING_MARGIN_ACTIVE_CLOCKS=$clocks"
    if {[lsort $clocks] ne {clk_pl_0 clk_pl_1} ||
        [get_property PERIOD [get_clocks clk_pl_0]] != 10.0 ||
        [get_property PERIOD [get_clocks clk_pl_1]] != 5.0} {error {Clock contract changed during logic optimization}}
    if {!$resume_physical} {
        set_clock_uncertainty -setup $setup_margin $clocks
        set_clock_uncertainty -hold $hold_margin $clocks
    }
    report_clocks -file [file join $out tightened_clocks.rpt]
    report_timing_summary -delay_type min_max -file [file join $out tightened_before.rpt]
    puts {TIMING_MARGIN_PHASE=physical_optimization}
    if {$stage eq {implement} && !$resume_physical} {
        puts {TIMING_MARGIN_PHASE=placement}
        place_design -directive Explore
        write_checkpoint [file join $out placed_candidate.dcp]
        if {$strategy eq {preplace_fifo_logic}} {
            verify_fifo_floorplan [file join $out fifo_floorplan_records.list] [file join $out fifo_floorplan_after_place.tsv]
        }
    }
    if {!$resume_physical} {phys_opt_design -directive ExploreWithAggressiveHoldFix}
    report_timing_summary -delay_type min_max -file [file join $out tightened_physopt.rpt]
    write_checkpoint [file join $out tightened_physopt.dcp]
    if {$stage eq {implement} && !$resume_initial_route} {
        puts {TIMING_MARGIN_PHASE=initial_routing}
        route_design -directive Explore
        report_timing_summary -delay_type min_max -file [file join $out tightened_initial_route.rpt]
        write_checkpoint [file join $out initial_routed_candidate.dcp]
    }
    if {$strategy eq {preplace_hold}} {
        puts {TIMING_MARGIN_PHASE=fifo_hold_eco}
        source [file join $out fifo_hold_eco.tcl]
        insert_fifo_hold_eco $out
        route_design -eco
        verify_fifo_hold_eco [file join $out hold_eco_records.list] [file join $out hold_eco_after_eco_route.tsv]
        report_timing_summary -delay_type min_max -file [file join $out tightened_hold_eco.rpt]
    }
    if {$strategy eq {preplace_relocate}} {
        puts {TIMING_MARGIN_PHASE=fifo_register_relocation}
        source [file join $out fifo_hold_relocate.tcl]
        source [file join $out fifo_hold_relocation_collect.tcl]
        collect_and_relocate_fifo $out $setup_margin $hold_margin
        # Match the scoped SLICEL probe and keep completed unrelated routes.
        # A failed relocated route is retained; do not rip up the whole design
        # merely to absorb a conflicting speculative site-pin assignment.
        route_design -preserve
        verify_fifo_relocation [file join $out relocation_records.list] [file join $out relocation_after_route.tsv]
        report_timing_summary -delay_type min_max -file [file join $out tightened_relocation.rpt]
    }
    if {[llength [get_timing_paths -delay_type max -slack_lesser_than 0]] ||
        [llength [get_timing_paths -delay_type min -slack_lesser_than 0]]} {
        puts {TIMING_MARGIN_PHASE=route_cleanup}
        # A fully routed design plus -tns_cleanup only invokes TNS cleanup and
        # ignores the routing directive (Vivado Route 35-558). Explicitly reopen
        # data nets feeding tight endpoints so the normal setup/hold router runs.
        # Leave clock nets and unrelated legal routing intact.
        set critical_nets {}
        foreach type {max min} {
            foreach path [get_timing_paths -delay_type $type -slack_lesser_than 0 -max_paths 10000 -nworst 1] {
                set pin [get_property ENDPOINT_PIN $path]
                foreach net [get_nets -of_objects $pin] {
                    if {[llength [get_clocks -quiet -of_objects $net]] == 0} {
                        lappend critical_nets $net
                    }
                }
            }
        }
        set critical_nets [lsort -unique $critical_nets]
        if {![llength $critical_nets]} {error {No critical data nets selected for rerouting}}
        set f [open [file join $out rerouted_data_nets.txt] w]
        puts $f "COUNT=[llength $critical_nets]"
        foreach net $critical_nets {puts $f $net}
        close $f
        puts "TIMING_MARGIN_REROUTE_NETS=[llength $critical_nets]"
        route_design -unroute -nets $critical_nets
        # Explore is compatible with the inherited incremental flow.
        route_design -directive Explore
    }
    report_timing_summary -delay_type min_max -file [file join $out tightened_final.rpt]
    write_checkpoint [file join $out tightened_final.dcp]
    if {$strategy eq {preplace_hold}} {
        release_hold_eco_placement [file join $out hold_eco_records.list]
        verify_fifo_hold_eco [file join $out hold_eco_records.list] [file join $out hold_eco_final.tsv]
        hold_leaf_snapshot [file join $out hold_eco_final_cells.tsv]
    }
    if {$strategy eq {preplace_relocate}} {
        release_fifo_relocation [file join $out relocation_records.list]
        verify_fifo_relocation [file join $out relocation_records.list] [file join $out relocation_final.tsv]
        relocate_leaf_snapshot [file join $out relocation_final_cells.tsv]
    }
    if {$strategy eq {preplace_fifo_logic}} {
        verify_fifo_floorplan [file join $out fifo_floorplan_records.list] [file join $out fifo_floorplan_final.tsv]
        release_fifo_floorplan
    }
    set_clock_uncertainty -setup 0.0 [get_clocks]
    set_clock_uncertainty -hold 0.0 [get_clocks]
    write_xdc [file join $out restored_constraints.xdc]
    report_clocks -file [file join $out restored_clocks.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose \
        -file [file join $out routed_timing.rpt]
    report_timing -delay_type max -max_paths 40 -nworst 1 -path_type full_clock_expanded \
        -file [file join $out final_setup_paths.rpt]
    report_timing -delay_type min -max_paths 40 -nworst 1 -path_type full_clock_expanded \
        -file [file join $out final_hold_paths.rpt]
    report_utilization -file [file join $out routed_utilization.rpt]
    if {$stage eq {implement}} {
        report_utilization -hierarchical -file [file join $out routed_hierarchical.rpt]
        set f [open [file join $out cnn_address_mapping.txt] w]
        set dsp [get_cells -quiet -hierarchical -filter {(NAME =~ *ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1* || NAME =~ *am_addmul_5ns_2ns_6ns_11_4_1*) && REF_NAME =~ DSP*}]
        puts $f "CNN_ADDRESS_DSP_CELLS=[llength $dsp]"
        foreach cell $dsp {puts $f $cell}
        close $f
        if {[llength $dsp]} {error {CNN address calculation still mapped to DSP}}
    }
    report_route_status -file [file join $out route_status.rpt]
    report_drc -file [file join $out routed_drc.rpt]
    report_cdc -details -file [file join $out routed_cdc.rpt]
    report_bus_skew -file [file join $out routed_bus_skew.rpt]
    report_clock_interaction -file [file join $out routed_clock_interaction.rpt]
    check_timing -verbose -file [file join $out routed_clock_check.rpt]
    set f [open [file join $out final_path_summary.txt] w]
    foreach type {max min} {
        foreach path [get_timing_paths -delay_type $type -max_paths 40 -nworst 1] {
            puts $f "$type SLACK=[get_property SLACK $path] START=[get_property STARTPOINT_PIN $path] END=[get_property ENDPOINT_PIN $path]"
        }
    }
    close $f
    # Preserve the candidate even if the attempt misses signoff or the target.
    write_checkpoint [file join $out optimized_routed.dcp]
    if {[llength [get_timing_paths -delay_type max -slack_lesser_than 0]] ||
        [llength [get_timing_paths -delay_type min -slack_lesser_than 0]]} {
        error {Optimized candidate fails original setup/hold constraints}
    }
    if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {
        error {Optimized candidate has blocking DRC violations}
    }
} elseif {$stage eq {verify}} {
    # Independent read-only reopen: validate the saved physical result without
    # exporting a bitstream or creating a delivery package.
    if {[file exists [file join $out hold_eco_records.list]]} {
        source [file join $out fifo_hold_eco.tcl]
        verify_fifo_hold_eco [file join $out hold_eco_records.list] [file join $out hold_eco_reopened.tsv]
        hold_leaf_snapshot [file join $out hold_eco_reopened_cells.tsv]
    }
    if {[file exists [file join $out relocation_records.list]]} {
        source [file join $out fifo_hold_relocate.tcl]
        verify_fifo_relocation [file join $out relocation_records.list] [file join $out relocation_reopened.tsv]
        relocate_leaf_snapshot [file join $out relocation_reopened_cells.tsv]
    }
    if {[file exists [file join $out fifo_floorplan_records.list]]} {
        source [file join $out fifo_hold_floorplan.tcl]
        if {[llength [get_pblocks -quiet hold_fifo_logic_only]]} {error {Temporary FIFO Pblock persists in saved checkpoint}}
        verify_fifo_floorplan [file join $out fifo_floorplan_records.list] [file join $out fifo_floorplan_reopened.tsv]
    }
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose \
        -file [file join $out reopened_timing.rpt]
    report_route_status -file [file join $out reopened_route.rpt]
    report_drc -file [file join $out reopened_drc.rpt]
    report_bus_skew -file [file join $out reopened_bus_skew.rpt]
    check_timing -verbose -file [file join $out reopened_clock_check.rpt]
    set f [open [file join $out reopened_unused_ps_clocks.txt] w]
    foreach name {EMIOENET0MDIOMDC EMIOENET1MDIOMDC EMIOENET2MDIOMDC EMIOENET3MDIOMDC EMIOSDIO0CLKOUT EMIOSDIO1CLKOUT EMIOSPI0SCLKO EMIOSPI1SCLKO} {
        set pin [get_pins -quiet system_i/zynq_ultra_ps_e_0/inst/PS8_i/$name]
        if {[llength $pin] != 1} {error "Missing expected PS pin $name"}
        set cell [get_cells -of_objects $pin]
        if {[get_property REF_NAME $cell] ne {PS8} || [get_property DIRECTION $pin] ne {OUT}} {error {Unexpected pin identity}}
        set nets [get_nets -quiet -segments -of_objects $pin]
        set loads [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == IN}]
        set ports [get_ports -quiet -of_objects $nets]
        set clocks [get_clocks -quiet -of_objects $pin]
        puts $f "PIN $pin REF=PS8 DIR=OUT INPUT_LOADS=[llength $loads] TOP_PORTS=[llength $ports] CLOCKS=[llength $clocks] NETS=$nets"
        if {[llength $loads] || [llength $ports] || [llength $clocks]} {error "PS output is not an unused unclocked leaf: $name"}
    }
    puts $f {CHECKED_UNUSED_PS_OUTPUTS=8}
    close $f
    foreach type {max min} {
        set path [get_timing_paths -delay_type $type -max_paths 1]
        if {[llength $path] != 1 || [get_property SLACK $path] < 0} {error "Reopened timing failed: $type"}
    }
    if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]]} {error {Unresolved black boxes}}
    if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {
        error {Reopened candidate has blocking DRC violations}
    }
} elseif {$stage ne {inspect}} {error {Unknown stage}}
close_design
puts "TIMING_MARGIN_[string toupper $stage]_PASS"
exit
