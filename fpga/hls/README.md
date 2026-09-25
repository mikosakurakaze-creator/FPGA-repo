# HLS implementation

The V1 correctness-first CNN top is `zero_dce_cnn_top` in
`zero_dce_cnn_top.cpp`, with the public types and buffer sizes in
`zero_dce_cnn_top.h`. It implements the 14 quantized convolutions and writes
the signed Q14 `A_low` tensor through an AXI4 master DDR pointer.

The top consumes the already downsampled `[1,3,60,106]` RGB NCHW Q14 tensor.
Weights, biases, per-output-channel fractional-bit values, and the Q15 Tanh
LUT are also read from packed DDR arrays. The external feature workspace is
used for two working buffers and six skip buffers.

The full pointer/control contract is frozen in
`configs/zero_dce_pp_hls_interface.json`; the rationale and timing/ownership
rules are in `docs/zero_dce_pp_hls_cnn_contract.md`.

Run `python deployment/export_hls_cnn_package.py` in the configured Python
environment to pack the downsampled input, generated integer arrays, and
golden output for C simulation or a PS loader. The generated package stays
under ignored `outputs/`. `tb_zero_dce_cnn.cpp` compares every `A_low` scalar
with the golden; `run_hls.tcl` is the Vitis HLS C simulation and synthesis
entry point. `evaluation/hls_native/ap_int.h` is used only for the native
g++ numerical check.

The native C++ testbench matched all 19,080 output scalars. This repository
does not contain Vitis HLS C-simulation, synthesis, RTL co-simulation,
Vivado timing, or board results yet. The source has no AXI4
Stream output; the canonical V1 transport is m_axi DDR write. A stream adapter
can be added at integration time without changing the Q14 tensor contract.
