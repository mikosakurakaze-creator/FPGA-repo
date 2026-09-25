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
with the golden; `run_hls.tcl` is the Vitis 2025.2 C simulation and synthesis
entry point. From the repository root on Windows, run:

```powershell
& "D:\vivado\2025.2\Vitis\bin\vitis-run.bat" --mode hls --tcl fpga/hls/run_hls.tcl
```

The script stages source and generated test data in a unique directory under
`TEMP`, because Vitis HLS rejects source paths containing spaces. Set
`ZERO_DCE_HLS_BUILD_ROOT` to another writable path without spaces if needed.
Set `ZERO_DCE_HLS_CSIM_ONLY=1` to stop after C simulation; otherwise synthesis
starts only after C simulation passes. The script prints the build directory,
which contains the component and reports. `evaluation/hls_native/ap_int.h` is
used only for the native g++ numerical check.

The native C++ testbench and Vitis 2025.2 C simulation matched all 19,080
output scalars with zero raw error. HLS synthesis completed for
`xc7z020clg400-1`: estimated 40.443 ns against a 10 ns target, with 4 BRAM18K,
11 DSP, 7,439 FF, and 16,720 LUT estimated. Loop II constraints were not all
met. These are HLS estimates; RTL co-simulation, Vivado timing, and board
results remain unverified. The source has no AXI4
Stream output; the canonical V1 transport is m_axi DDR write. A stream adapter
can be added at integration time without changing the Q14 tensor contract.
