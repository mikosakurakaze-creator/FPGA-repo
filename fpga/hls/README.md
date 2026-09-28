# HLS implementation

The tiled V1 CNN top is `zero_dce_cnn_top` in
`zero_dce_cnn_top.cpp`, with the public types and buffer sizes in
`zero_dce_cnn_top.h`. It implements the 14 quantized convolutions and writes
the signed Q14 `A_low` tensor through an AXI4 master DDR pointer.

The top consumes the already downsampled `[1,3,60,106]` RGB NCHW Q14 tensor.
Weights, biases, per-output-channel fractional-bit values, and the Q15 Tanh
LUT are copied once per invocation from packed DDR arrays to on-chip memory.
The external feature workspace holds six skip tensors. Each 8x16 output tile
is computed from a local source tile with a one-pixel halo, so convolution
MACs do not access DDR. The output remains an AXI4 master DDR write.

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

The tiled top matched all 19,080 output scalars with zero raw error in the
native C++ testbench and Vitis 2025.2 C simulation. Vitis HLS estimated
8.313 ns against a 10 ns target, with 58 BRAM18K, 16 DSP, 11,187 FF, and
16,495 LUT; all loop constraints were satisfied. The earlier direct-DDR
version estimated 40.443 ns. This revision exposes six AXI masters
(`gmem8`, `gmem32`, `gmem_input`, `gmem_lut`, `gmem_output`, and
`gmem_workspace`); connect all six to DDR at integration.
RTL co-simulation, Vivado timing, and board results remain unverified. The
source has no AXI4
Stream output; the canonical V1 transport is m_axi DDR write. A stream adapter
can be added at integration time without changing the Q14 tensor contract.
