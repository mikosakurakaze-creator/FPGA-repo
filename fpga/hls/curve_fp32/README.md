# Curve FP32 baseline (stage 1)

`curve_fp32` processes one NCHW float32 element per call. It reuses the same parameter for eight rounds and writes all intermediate values to `rounds[0..7]`. There are no HLS optimization pragmas. The top function does not parse `.npy`.

The exporter checks every required reference file before writing, validates float32 shape/layout against `metadata.json`, and writes little-endian contiguous NCHW `.f32` files. `manifest.json` retains the original metadata and raw format. These generated files belong under `outputs/` and are not intended for Git.

From the repository root, with Python plus NumPy and a C++17 compiler:

```powershell
python fpga/hls/curve_fp32/export_raw.py outputs/zero_dce_pp/reference outputs/zero_dce_pp/curve_fp32_raw
g++ -std=c++17 -O2 -ffp-contract=off fpga/hls/curve_fp32/curve.cpp fpga/hls/curve_fp32/tb_curve.cpp -o outputs/zero_dce_pp/curve_fp32_tb.exe
./outputs/zero_dce_pp/curve_fp32_tb.exe outputs/zero_dce_pp/curve_fp32_raw
```

The testbench compares every round and the final output with the exported software references, reporting maximum and mean absolute errors. The final maximum must be at most `1e-6`. This is a C/C++ simulation check; HLS synthesis, RTL cosimulation, fixed point, and performance evaluation are outside this stage.
