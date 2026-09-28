# Zero-DCE++ CNN HLS contract

The repository contains a tiled V1 HLS top at
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
array of 1,221,120 signed INT16 elements (2,442,240 bytes), containing the
six 32-channel ReLU skip tensors from blocks 1 through 6. Values in it use
different fractional-bit counts at different layers, so the workspace name
does not imply a fixed Q14 scale. The `a_low_q14` DDR buffer is valid after
`ap_done` and must be invalidated in the PS cache before reading it. Flush
input and model arrays from the PS cache before asserting start. No overlap
between invocations is assumed in V1. Physical DDR addresses and the
generated AXI-Lite register offsets are assigned during system integration.

At each start, the top copies the packed weights, biases, per-channel scales,
and Tanh LUT into on-chip memories. It reads an 8x16 output tile and its
one-pixel halo into a local source tile, performs depthwise and pointwise
convolution on local tiles, then writes the completed output tile to the
appropriate skip slot or the final A_low DDR buffer. Skip concatenation and
its required Q-format conversion happen during tile loading. DDR access is
therefore outside the MAC loops. The rightmost and bottom tiles are clipped to
the 106x60 image, and out-of-image halo samples are zero. All seven blocks
remain sequential, so a skip slot is complete before a later block reads it.

This schedule reduces the external workspace by 1,628,160 bytes. It preserves
the AXI pointer list and A_low format. Six generated AXI masters are used:
`gmem8` for weights and scales, `gmem32` for biases, and one each for the
input, LUT, output, and workspace. Integration must connect all six masters
to accessible DDR. Vitis HLS inferred bursts for the model arrays and the
contiguous tile rows. It did not infer a single burst across noncontiguous
rows or conditional halo handling; bursts may be split to the configured
maximum of 64 beats.

The old direct-DDR implementation estimated 40.443 ns for a 10 ns target.
Vitis 2025.2 HLS synthesis of the tiled implementation estimated 8.313 ns
(120.30 MHz) for the same target on `xc7z020clg400-1`, with all loop
constraints satisfied. It estimated 58 BRAM18K, 16 DSP, 11,187 FF, and
16,495 LUT. These are HLS estimates. Vivado placement and routing, DDR
integration, actual frame latency, and board performance still need checking.

## Verification status

The Python integer prototype and its seven tests validate the packed numerical
rules, including Q14 `A_low` conversion. The tiled implementation matched all
19,080 output scalars against the existing golden in native C++ and Vitis
2025.2 C simulation, with zero mismatches. The previous direct-DDR
implementation estimated 40.443 ns and 4 BRAM18K, 11 DSP, 7,439 FF, and
16,720 LUT. The tiled implementation estimated 8.313 ns and 58 BRAM18K,
16 DSP, 11,187 FF, and 16,495 LUT. RTL co-simulation and hardware timing
have not been run.

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
