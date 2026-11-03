set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 8
open_checkpoint $checkpoint
puts [help get_nets]
set pins {}
foreach clock {clk_pl_0 clk_pl_1} {lappend pins [get_property SOURCE_PINS [get_clocks $clock]]}
lappend pins {system_i/cnn_data_sc/inst/m00_nodes/m00_w_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst/gen_rd_b.gen_rd_b_synth_template.gen_rf_narrow_reg.doutb_reg_reg[26]/C}
set f [open [file join $out net_alias_queries.txt] w]
foreach pin $pins {
    set p [get_pins $pin]
    set nets [get_nets -of_objects $p]
    puts $f "PIN=$pin NET=$nets"
    foreach query [list [list get_nets -segments -of_objects $p] [list get_nets -segments $nets] \
        [list get_nets -top_net_of_hierarchical_group -of_objects $p] \
        [list get_nets -top_net_of_hierarchical_group $nets]] {
        set value [eval $query]
        puts $f "QUERY=$query COUNT=[llength $value] HEAD=[lrange $value 0 4]"
    }
}
close $f
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
