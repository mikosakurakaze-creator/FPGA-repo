# CNN V1.2 write-credit IP release recipe

This directory freezes a **post-export RTL scheduling overlay**, rather than a
new HLS algorithm or HLS export. The fixed Phase 4E generator is imported without
calling its candidate-creation entry point. No protected input is edited.

## Inputs and allowed difference

- Frozen export: `E:/HLS/kv260_three_module_v1_2_phase4/cnn_r4_export/hls/impl/ip`.
- Frozen C++ reference: `fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4`.
- Verified overlay and manifest: adjacent `candidate_b_rowstream_r4_writecredit`.
- Generator: `fpga/perf/v1_2_phase4e/build_writecredit_candidate.py`.
- Tool: Vivado 2025.2, K26 `xck26-sfvc784-2LV-c`, 10 ns OOC clock.

`input_lock.json` records SHA-256 for all IP payload files, the original generator,
the overlay manifest, the three original/verified RTL files and frozen C++ inputs.
Every build checks the lock both before and after execution. The fresh export's
three base hashes equal the older generated RTL used by Phase 4E.

Exactly these Verilog files change:

1. `zero_dce_cnn_top_row_axi_writer.v`
2. `zero_dce_cnn_top_row_axi_writer_2.v`
3. `zero_dce_cnn_top_p_anonymous_namespace_output_writer.v`

Every other original payload file remains byte-identical, except `component.xml`.
Runtime logs, launch scripts, `.Xil` and the original unpatched IP ZIP are not
release payload. In particular, that old ZIP cannot act as a shadow release.

## Metadata and ABI

The VLNV stays `xilinx.com:hls:zero_dce_cnn_top:1.0`. Core revision changes from
2114810447 to the fixed 2114810448 so the isolated V1.2 catalog can identify the
replacement. Top ports, bus interfaces, address spaces, memory/register maps,
parameters, every driver file and xgui are checked against the frozen export.

The frozen HLS export also advertises VHDL synthesis/simulation views containing
the old writer scheduling. The release **removes those two active views and their
two filegroups**. The original VHDL files remain byte-identical as archival files;
no active model view or compile list references them. Both available RTL views
use the exact same Verilog/header/ROM-data files and hashes. The synthesis view's
only extra file is the unchanged 10 ns OOC XDC.

Vivado `save_core` can add `spirit:format="long"` to address-space ranges. The
recipe deterministically removes this optional annotation and restores the
frozen address-space checksum, without changing any range value. A second,
read-only Vivado `open_core`/`check_integrity` verifies the normalized package.
The internal `coreCreationDateTime` is fixed to the frozen export's date; actual
build timestamps remain in `build_manifest.json` outside deterministic identity.
No further save operation is performed on the sealed release.

## Reproduce

Use clean, absent output directories. The recipe refuses to overwrite them.
The input lock is already established; **do not regenerate it for a release**.

```powershell
python fpga/ip/cnn_v1_2_writecredit/build_ip.py build --output E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05
python fpga/ip/cnn_v1_2_writecredit/build_ip.py build --output E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_rebuild_06
python fpga/ip/cnn_v1_2_writecredit/build_ip.py compare --primary E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05 --rebuild E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_rebuild_06 --report E:/HLS/kv260_three_module_v1_2_phase4/phase4g/deterministic_rebuild.json
python fpga/ip/cnn_v1_2_writecredit/run_ooc.py --ip E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ip_primary_05 --output E:/HLS/kv260_three_module_v1_2_phase4/phase4g/ooc_05
```

Change only the output names when rerunning, since the recorded release paths
will already exist. `build_manifest.json` separates deterministic `identity`
from its timestamp, generated path and execution paths. The identity includes
base, generator, overlay, recipe, input-lock, ABI, driver, final payload, raw
component and raw/canonical source-manifest SHA-256. `source_manifest_sha256`
means canonical JSON identity; `source_manifest_file_sha256` means file bytes.
The rebuild compares the entire original payload and the two audit manifests
byte-for-byte. Build manifests may differ only in execution fields.

The launcher supplies `PROCESSOR_ARCHITECTURE=AMD64` only if missing, then loads
the local 2025.2 settings. This handles the desktop execution environment where
Vivado's loader otherwise silently exits before initialization.

## Gates and stopping point

`PACKAGED_IP_GATE_PASS` covers input protection, exact three-file patch, Vivado
packaging/integrity, exact external ABI, and synthesis/simulation source identity.
It does not claim functional simulation or synthesis by itself. OOC synthesis
uses the exact packaged synthesis fileset, records the actual compile order,
resources, timing estimate and all three writer hierarchy entries, and verifies
the sealed package remains unchanged. LUT/FF/BRAM/URAM/DSP totals come from actual
Vivado utilization output, not from HLS estimates.

Recorded CNN OOC result: **100 MHz synthesis PASS**, LUT **20,210**, FF
**17,498**, BRAM **62.5 tiles** (29 RAMB36 + 67 RAMB18), URAM **18**, DSP **82**.
The setup estimate is **+3.212 ns** and pre-route hold estimate **+0.038 ns**.
Vivado warns that OOC `ap_clk` has no `HD.CLK_SRC`, so its clock delay/skew estimate
is limited; these are synthesis estimates rather than implementation signoff.

`metrics.tsv` is retained as a raw diagnostic counter file. Its broad `REF_NAME`
patterns do not restrict matches to `IS_PRIMITIVE`; its LUT 24,894 and DSP 738
counts therefore include hierarchy/macro matches and must not be used as physical
resource totals. `ooc_summary.json` takes its final resource values from named
`report_utilization` rows. `resource_counter_audit.json` records both sets of
values and their provenance. The clock/setup/hold fields in `metrics.tsv` come
from actual clock/timing objects and remain valid for their stated estimate scope.

Formal functional sanity and isolated V1.2 catalog/BD/output-product/system
synthesis gates are described in `fpga/reports/v1_2_phase4g_implementable_cnn_ip.md`.
The release becomes `IMPLEMENTABLE_CNN_IP_READY` only after all those gates pass.
No implementation, route, bitstream/XSA, 8/100-frame run, hardware test or Git
write is performed by these scripts.

All generated IP payloads, OOC checkpoints, logs and simulation data live under
the external `E:/HLS/.../phase4g` evidence directory. They are not repository
sources or upload candidates.
