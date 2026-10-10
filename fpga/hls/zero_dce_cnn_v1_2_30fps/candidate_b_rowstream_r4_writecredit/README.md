# Phase 4E isolated r4 write-retirement candidate

This is an **RTL scheduling overlay** for the frozen generated r4 CNN. It is
not a newly synthesized HLS IP or an implementation/bitstream release.

The frozen C++/header/testbench numerical reference is retained in the adjacent
`candidate_b_rowstream_r4` directory. The three byte-identical copies originally
created here are excluded from the Git release to avoid duplicate inputs.
Resynthesizing the frozen C++ alone does **not** reproduce the credit scheduling.
There is deliberately no runnable HLS configuration for this overlay.

Reproduce the overlay in a checkout where this candidate directory is absent with
`fpga/perf/v1_2_phase4e/build_writecredit_candidate.py`, using the frozen generated
RTL at `E:/HLS/cnn_v1_2_phase3b_r4/cnn_component/hls/syn/verilog`. The builder
refuses to overwrite an existing candidate and records input/output SHA256.

Only these generated modules differ:

- `rtl/zero_dce_cnn_top_row_axi_writer.v`: workspace row-send completion no
  longer waits for B; a two-credit counter independently retires logical rows.
- `rtl/zero_dce_cnn_top_row_axi_writer_2.v`: identical scheduling for A_low.
- `rtl/zero_dce_cnn_top_p_anonymous_namespace_output_writer.v`: completes each
  block only after both helper credit counts become zero.

Credits count accepted **HLS row requests**, not individual physical AXI bursts.
The unchanged m_axi adapter packs INT16 into AXI32, performs 4KB splitting and
returns one coalesced logical B per row. It may buffer data after helper send
completion, so only the block drain indicates all external AW/W/B are finished.
All original data pipelines, row addresses/order, adapter configuration, six
bundles and seven-pointer ABI are retained. The system memory boundary remains
READ_OUTSTANDING=WRITE_OUTSTANDING=2.

The independent writer RTL probe must pass before the single-frame system run.
Results and limitations are recorded in
`fpga/reports/v1_2_phase4e_write_retirement_optimization.md`.
