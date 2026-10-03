# Phase 4G release gates

All DUT CNN Verilog sources come from the sealed post-export package. The frozen
Phase 4E generator, overlays, DDR/BFM and Phase 4F evidence are read-only inputs.
The source manifest is resolved from `component.xml`; actual XSIM/Vivado compile
lists and hashes are checked separately. No tool here launches implementation,
route, bitstream/XSA export or an eight/100-frame run.

The package recipe is in `fpga/ip/cnn_v1_2_writecredit/README.md`. Build two clean
packages and compare them before running the commands below. Recorded output
names already exist after this run: choose fresh output names/suffixes for any
subsequent execution and update every corresponding command argument.

```powershell
python fpga/perf/v1_2_phase4g/audit_release.py --ip E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05 --rebuild E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_rebuild_06 --output E:/HLS/kv260_three_module_v1_2_phase4/phase4g/independent_package_audit_full.json
python fpga/perf/v1_2_phase4g/prepare_sanity.py --ip-root E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05 --out-root E:/HLS/kv260_three_module_v1_2_phase4/phase4g --suffix 05
python fpga/perf/v1_2_phase4g/run_sanity.py --kind writer --run E:/HLS/kv260_three_module_v1_2_phase4/phase4g/writer_probe_05
python fpga/perf/v1_2_phase4g/prepare_sanity.py --ip-root E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05 --out-root E:/HLS/kv260_three_module_v1_2_phase4/phase4g --suffix 06
python fpga/perf/v1_2_phase4g/run_sanity.py --kind cnn --run E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06 --local-evidence E:/HLS/kv260_three_module_v1_2_phase4/phase4g/writer_probe_05/comparison.json
python fpga/perf/v1_2_phase4g/analyze_sanity.py --run E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06
python fpga/perf/v1_2_phase4g/make_release_gate.py --ip E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05 --package-audit E:/HLS/kv260_three_module_v1_2_phase4/phase4g/independent_package_audit_full.json --rebuild E:/HLS/kv260_three_module_v1_2_phase4/phase4g/deterministic_rebuild.json --writer-probe E:/HLS/kv260_three_module_v1_2_phase4/phase4g/writer_probe_05/writer_probe_gate.json --cnn-single E:/HLS/kv260_three_module_v1_2_phase4/phase4g/cnn_single_06/cnn_single_gate.json --ooc E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05/ooc_summary.json --output E:/HLS/kv260_three_module_v1_2_phase4/phase4g/release_gate.json
python fpga/perf/v1_2_phase4g/run_integration.py --release-gate E:/HLS/kv260_three_module_v1_2_phase4/phase4g/release_gate.json
```

The final local evidence is writer_probe_05. The final CNN gate must come from
cnn_single_06, after replacing the old CNN include directory in a fresh options
copy. The original options remain unchanged; the byte/path/header audit is
recorded separately. CNN05 was stopped early for source-search audit and is not
a release gate; writer_probe_06 was prepared but never run.

`make_release_gate.py` refuses to release the package before the independent
byte/ABI/view audit, deterministic rebuild, four local writer scenarios, one
complete CNN frame and actual 100MHz OOC synthesis pass. It binds the evidence
hashes and formal manifest to the integration input. It checks exact Phase 4E
cycles, all 19,080 A_low raw values, guard/hazard and final block/HP drain.

`run_integration.py` creates a fresh independent `v12_wc` project from the saved
V1.2 BD. Only the formal CNN repository and byte-identical isolated Bilinear/Curve
copies enter its IP search path. Cache reuse is disabled. It validates topology
and addressing, generates output products, performs actual synthesis, checks all
139 resolved CNN Verilog hashes and each writer's actual primitive hierarchy,
and reports resources and pre-route timing. The original V1.2 XPR/runs and V1.1
remain unchanged.

`protection.py --phase before/after` is the separate audit for this recorded
Phase 4G run. It checks the original 5,235-file recovery manifest plus the r4
package, candidate/generator and existing Phase 4E/F evidence. Its sealed audit
filenames are deliberately not overwritten. `checkpoint_before.md` retains the
previous authoritative checkpoint. The final report and current checkpoint are
written only after all release/integration gates and the after audit pass.

The stop condition is `IMPLEMENTABLE_CNN_IP_READY`. Implementation/route,
post-route timing/DRC, bitstream/XSA, hardware tests, further performance work and
Git writes require a separate request. Suggested commit message and the exact
changed-file review are in the Phase 4G report; these scripts do not stage or
commit files.
