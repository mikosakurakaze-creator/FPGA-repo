# V1.2 Phase6 executed source recipe

This directory archives the eight Python/Tcl source files actually used for the
successful 2026-10-03 bitstream/XSA handoff. They were copied byte-for-byte from
`E:/HLS/kv260_three_module_v1_2_phase4/phase6/bitstream_xsa_01` during the release
Git audit. `source_manifest.json` records their original paths, sizes and SHA-256.
No build outputs, generated launchers, logs, backups or hardware binaries are
included. The release audit did not execute these scripts.

## Recorded execution order

1. `prepare.py`: verify Phase5 gate and frozen inputs, capture protection evidence.
2. `run_vivado.py bitstream`: launch `bitstream.tcl` from the existing routed run.
3. `audit_bitstream.py`: verify natural completion, routing, timing and DRC.
4. `run_vivado.py export_xsa`: launch `export_xsa.tcl` with the generated bitstream.
5. `audit_xsa.py`: check ZIP integrity, embedded bitstream, HWH and driver ABI.
6. `finalize_docs.py`: write the handoff/map/report/checkpoint from passing gates.
7. `audit_handoff.py`: verify the complete handoff and record its final gate.

The launcher generates its `.cmd` files and records natural process exit.
`prepare.py` supplies shared hashing and protection helpers. The recipe also uses
the committed Phase4G `run_integration.py` and Phase5 `analyze_implementation.py`.

## Prerequisites and replay boundary

These are the original executed sources, with their original fixed paths:
repository `E:/github/-`, tool settings `E:/Xilinx/2025.2`, and external inputs
under `E:/HLS/kv260_three_module_v1_2_phase4`. The Tcl files require the formal
Phase4G `integration_01/integration_config.tcl` and `project/v12_wc.xpr`, the sealed
CNN package/release gate, and the passing Phase5 evidence and routed checkpoint.

All scripts use their own directory as the evidence/output directory. A separately
authorized replay must copy only these eight source files into a clean external
evidence directory and restore the matching **pre-Phase6** input/project state.
Do not execute them directly from this Git directory. `bitstream.tcl` requires
`route_design Complete!`; the delivered project now has `write_bitstream Complete!`.
The protection snapshots also refer to the original Phase5 state. Renaming an
output directory alone does not make the completed project replayable. Several
steps refuse to overwrite existing evidence; document finalization writes the
four historical handoff files and requires separate review before any replay.

The original external runtime evidence remains the authority for the completed
run. This archive preserves the source recipe and does not claim a new execution
or a portable one-command build. Hardware binaries remain external and are
identified by path, size and SHA-256 in the
[handoff](../../docs/v1_2_hardware_handoff.md) and
[Phase6 report](../../reports/vivado_three_module_v1_2_bitstream_xsa.md).

BOARD_30FPS remains **NOT_TESTED**. Further builds, simulations, PS development
and board validation require a separate task from Master.
