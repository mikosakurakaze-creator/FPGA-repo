set core /gdn_frame_axi_test/dut/griddehaze_frame_top_0/inst
set samples [open sample_words.txt w]
run 1000ns
set loops 0
while {1} {
  set n [get_value -radix unsigned ${core}/i_2_fu_352]
  if {[string is integer -strict $n] && $n >= 3} {break}
  run 1000ns
  incr loops
  if {$loops > 4000} {error "sample watchdog: no expected graph progress"}
}
puts $samples "NODE 1"
for {set i 3072} {$i < 3200} {incr i} {
  puts $samples [get_value -radix hex /gdn_frame_axi_test/feature/mem[$i]]
}
flush $samples
puts "GDN_ROUTED_SAMPLE_CAPTURE node=1 words=128 graph_node=$n"
puts $samples "NODE 2"
for {set i 3200} {$i < 3328} {incr i} {
  puts $samples [get_value -radix hex /gdn_frame_axi_test/feature/mem[$i]]
}
flush $samples
puts "GDN_ROUTED_SAMPLE_CAPTURE node=2 words=128 graph_node=$n"
while {1} {
  set n [get_value -radix unsigned ${core}/i_2_fu_352]
  if {[string is integer -strict $n] && $n >= 5} {break}
  run 1000ns
  incr loops
  if {$loops > 4000} {error "sample watchdog: no expected graph progress"}
}
puts $samples "NODE 3"
for {set i 3328} {$i < 3456} {incr i} {
  puts $samples [get_value -radix hex /gdn_frame_axi_test/feature/mem[$i]]
}
flush $samples
puts "GDN_ROUTED_SAMPLE_CAPTURE node=3 words=128 graph_node=$n"
puts $samples "NODE 4"
for {set i 3456} {$i < 3712} {incr i} {
  puts $samples [get_value -radix hex /gdn_frame_axi_test/feature/mem[$i]]
}
flush $samples
puts "GDN_ROUTED_SAMPLE_CAPTURE node=4 words=256 graph_node=$n"
close $samples
puts "GDN_ROUTED_SAMPLE_SEQUENCE_DONE nodes=1,2,3,4"
quit
