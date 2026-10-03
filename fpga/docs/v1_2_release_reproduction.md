# V1.2 release source and reproduction boundary

Release Git audit: 2026-10-03 (Asia/Shanghai). The authoritative current state is
the [Phase6 checkpoint](../reports/v1_2_phase4_checkpoint.md). A quick team-facing
summary is available in [v1_2_status_for_team.md](v1_2_status_for_team.md).

## Sources retained for the final release

- [Formal CNN recipe](../ip/cnn_v1_2_writecredit/README.md): deterministic package
  build, locked inputs and OOC recipe. Frozen r4 C++/config/testbench and their
  three include/header dependencies remain as the original numeric inputs.
- [Write-credit candidate](../hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4_writecredit/README.md):
  verified three-module RTL overlay and its manifest. Duplicate C++/header/TB
  copies are excluded; the recipe reads the adjacent frozen r4 inputs.
- Phase4E/F scripts: the final write-retirement and eight-frame validators.
  Selected Phase4B DDR protocol/model and system-TB source preparation scripts
  are retained because the final validators depend on those successful inputs.
  They preserve the original three-module BFM, goldens, buffers and PL wrapper;
  portable Verilator, aborted runs and obsolete netlist attempts are excluded.
- [Phase4G gate](../perf/v1_2_phase4g/README.md): same-source package audit, sanity,
  integration and report recipes; formal create/synth Tcl scripts and the saved
  V1.2 `system.bd` design input. Original create/synth/simulation-preparation Tcl
  scripts remain only as inputs to the shared harness/export preparation.
- Phase5 implementation runner/analyzer/report recipe and its final Tcl script.
- [Phase6 executed recipe](../perf/v1_2_phase6/README.md): the eight original
  Python/Tcl sources, byte-identical provenance manifest and replay limitations.
- Formal Phase4E/F/G/5/6 reports, current checkpoint, hardware handoff and
  machine-readable register/DDR map. Historical pre-write-credit synthesis
  reports are excluded; current synthesis evidence is in Phase4G.

## Required external inputs

This Git release preserves the reviewed source recipes and design inputs. It is
**not a self-contained build from an empty clone**. Keep or separately transfer
the following external inputs with their recorded hashes:

- Vivado/Vitis 2025.2 and the K26/100MHz device/tool configuration.
- The 305-file frozen r4 HLS IP export under
  `E:/HLS/kv260_three_module_v1_2_phase4/cnn_r4_export/hls/impl/ip`, plus the three
  original generated writer RTL files referenced by `input_lock.json`. The
  write-credit behavior comes from the verified post-export overlay; rerunning
  HLS from C++ alone does not recreate that scheduling.
- Frozen CNN parameters/data, unchanged Bilinear/Curve IPs, the original shared
  RTL harness inputs and golden/buffer metadata under the documented external
  Phase4 directories. Goldens, temporary hex and runtime copies stay outside Git.
- The protected original/fresh PS XCI used by the Phase4G comparison gate to
  confirm the explicitly serialized MIO22 input type. These tool-generated audit
  references are not committed; the gate needs the documented local inputs.
- Existing sealed formal package, release gates, Phase5 routed checkpoint and
  pre-Phase6 snapshots when replaying the historical Phase6 recipe. Phase6 keeps
  its original fixed paths and cannot be replayed merely by choosing a new
  output directory after the project already completed bitstream generation.

The scoped `.gitattributes` rules preserve the reviewed files' exact bytes,
including mixed/CRLF endings. This keeps frozen input and evidence SHA-256 values
valid across Git staging and checkout without changing the original sources.

## Verification performed for this Git release

Only Git inspection, source/dependency review, Python syntax and JSON parsing,
credential/artifact screening, staged-byte/hash comparisons, and read-only
verification of existing release evidence/artifact hashes were performed.
The scoped file inclusion/exclusion lists and Git audit records remain locally
under ignored `outputs/v1_2_release_git_audit/`.

No HLS/Vivado build, implementation, bitstream generation, system TB, performance
optimization, PS development or board test was rerun in this Git release task.
The existing bitstream/XSA are identified by path, size and SHA-256 in the
[hardware handoff](v1_2_hardware_handoff.md); their binaries are not in Git.
**BOARD_30FPS = NOT_TESTED**. Further execution awaits Master.
