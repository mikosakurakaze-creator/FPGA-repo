# Zero-DCE++ CNN HLS contract

The repository now contains a correctness-first V1 HLS top at
`fpga/hls/zero_dce_cnn_top.cpp`. It implements the seven Zero-DCE++ encoder
blocks (14 convolutions), the three concatenations, ReLU placement, the Q15
Tanh LUT lookup, and the final Q15-to-Q14 conversion at the `A_low` boundary.
The official upstream network and enhancement formula are not changed.

## Top-level choice

The canonical top is `zero_dce_cnn_top`. It uses AXI4-Lite `ap_ctrl_hs` for
control and AXI4 master pointers for data. `A_low` is written directly to DDR
through the `a_low_q14` master pointer. There is deliberately no AXI4-Stream
port in this V1 top; a stream adapter can be added at the system boundary if
the Bilinear core later needs streaming.

The top consumes the already downsampled CNN input, not the full-resolution
camera frame. The upstream fixed-point downsampler must provide
`[1,3,60,106]` signed Q14 in RGB planar NCHW order. The output has the same
shape and layout. Each channel occupies `60*106*2 = 12,720` bytes and the
complete frame is 38,160 bytes.

## Data contract

The exact pointer names, element counts, memory layout, workspace size, cache
rule, and implementation status are frozen in
`configs/zero_dce_pp_hls_interface.json`.

The fixed `night_01` input and model arrays are packed by
`deployment/export_hls_cnn_package.py`:

- `input_q14.bin`: 19,080 signed Q14 values, the already downsampled CNN input;
- `weights_int8.bin`: 10,075 signed INT8 values, concatenated per-layer OIHW;
- `bias_int32.bin`: 486 signed INT32 values;
- `weight_frac.bin`: 486 signed values, one fractional-bit count per output
  channel;
- `tanh_lut_q15.bin`: 4,097 signed Q15 values for Q8 indices `-2048..2048`.
- `expected_a_low_q14.bin`: 19,080 signed Q14 comparison values; this is a
  golden testbench oracle and is not an IP input.

All raw files are little-endian and contain no headers or row padding. The
generated `manifest.json` records offsets and SHA-256 values. The files under
`outputs/` remain ignored; they are generated inputs for C simulation or a PS
loader, not repository source artifacts.

## Timing and ownership contract

One AXI-Lite start launches one complete CNN evaluation. The caller must keep
the input, model, LUT, output, and workspace allocations owned by the IP until
`ap_done`; none of these regions may overlap. `workspace_int16` is a scratch
array of 2,035,200 signed INT16 elements (4,070,400 bytes). Values in it use
different fractional-bit counts at different layers, so the workspace name
does not imply a fixed Q14 scale. The `a_low_q14` DDR buffer is valid after
`ap_done` and must be invalidated in the PS cache before reading it. Flush
input and model arrays from the PS cache before asserting start. No overlap
between invocations is assumed in V1. Physical DDR addresses and the
generated AXI-Lite register offsets are assigned during system integration.

The source pipelines simple copies, activation, and output loops. Convolution
MACs use a serial correctness-first schedule with a signed INT32 accumulator.
HLS synthesis reports unmet loop II constraints and a 40.443 ns clock estimate
for the 10 ns target. Vivado timing closure and board performance remain to be
measured.

## Verification status

The Python integer prototype and its seven tests validate the packed numerical
rules, including Q14 `A_low` conversion. A native g++ testbench using an
`ap_int` width shim compared all 19,080 output scalars against the Python
golden, with zero mismatches. Vitis 2025.2 C simulation also compared all
19,080 values with zero mismatches. Vitis 2025.2 HLS synthesis completed for
`xc7z020clg400-1`, estimating 40.443 ns against a 10 ns target and 4 BRAM18K,
11 DSP, 7,439 FF, and 16,720 LUT. The tool reported unmet loop II constraints.
These estimates do not establish Vivado timing closure or board performance;
RTL co-simulation and hardware timing have not been run.

To reproduce the native numerical check from the repository root after
generating the integer artifacts, run:

```text
python deployment/export_hls_cnn_package.py
g++ -std=c++14 -O2 -I evaluation/hls_native -I fpga/hls fpga/hls/zero_dce_cnn_top.cpp fpga/hls/tb_zero_dce_cnn.cpp -o outputs/zero_dce_pp/quantization/hls_cnn/native_cnn_test
outputs/zero_dce_pp/quantization/hls_cnn/native_cnn_test outputs/zero_dce_pp/quantization/hls_cnn
```

`evaluation/hls_native/ap_int.h` is only the native check's type shim. The
Vitis HLS project uses the vendor `ap_int.h`. With Vitis 2025.2 installed,
run `vitis-run --mode hls --tcl fpga/hls/run_hls.tcl` from the repository root.
The script stages inputs under a whitespace-free temporary path, runs 10 ns C
simulation, then attempts synthesis for `xc7z020clg400-1`. Set
`ZERO_DCE_HLS_BUILD_ROOT` to choose a writable staging root without spaces, or
`ZERO_DCE_HLS_CSIM_ONLY=1` to run only C simulation. The first hardware check
should compare the DDR `a_low_q14` payload byte-for-byte against the existing
Q14 golden payload.
