# Fresh V1.2 integration: use only the Phase 4G configuration and saved BD copy.
# No old XPR/cache is opened, and no implementation command is present.
if {$argc != 1} {error {Expected one Phase 4G configuration Tcl path}}
source [lindex $argv 0]
if {[file exists $project_dir]} {error "Refusing to overwrite project: $project_dir"}
foreach p $ip_repos {
    if {![file isfile [file join $p component.xml]]} {error "Missing IP: $p"}
}
file mkdir $project_dir
cd $project_dir
create_project $project_name $project_dir -part xck26-sfvc784-2LV-c
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set_property ip_repo_paths $ip_repos [current_project]
# A fresh project and disabled cache prevent an old CNN DCP from satisfying this build.
config_ip_cache -disable_cache
update_ip_catalog -rebuild
foreach vlnv {
    xilinx.com:hls:zero_dce_cnn_top:1.0
    xilinx.com:hls:bilinear_fixed16_buffered:1.0
    xilinx.com:hls:curve_image_fixed16:1.0
} {
    set defs [get_ipdefs -all $vlnv]
    if {[llength $defs] != 1} {error "Missing or ambiguous catalog IP: $vlnv"}
    set out [open [file join $report_dir "catalog_[string map {: _} $vlnv].txt"] w]
    foreach prop [lsort [list_property $defs]] {
        puts $out "$prop\t[get_property $prop $defs]"
    }
    close $out
    puts "CATALOG_IP=$vlnv"
}
set bd_dir [file join $project_dir ${project_name}.srcs sources_1 bd system]
file mkdir $bd_dir
set bd_file [file join $bd_dir system.bd]
file copy $bd_seed $bd_file
add_files -norecurse $bd_file
open_bd_design $bd_file
set cnn [get_bd_cells zero_dce_cnn_top_0]
if {[llength $cnn] != 1 || [get_property VLNV $cnn] ne {xilinx.com:hls:zero_dce_cnn_top:1.0}} {
    error {CNN ABI/VLNV differs}
}
# Explicitly refresh this instance against the sole compatible CNN catalog entry.
upgrade_bd_cells $cnn
validate_bd_design
save_bd_design
report_ip_status -file [file join $report_dir ip_status_created.rpt]
puts {PHASE4G_CREATE_VALIDATE=PASS}
close_project
exit
