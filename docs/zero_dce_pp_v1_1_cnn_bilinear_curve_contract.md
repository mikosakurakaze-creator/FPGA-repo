# Zero-DCE++ V1.1 CNN/Bilinear/Curve Integration Contract

This contract defines the V1.1 handoff between the existing CNN HLS top and
the DDR-buffered Bilinear and Curve modules. The handoff is zero-copy at the
module boundary: CNN writes the low-resolution parameter tensor to DDR and
Bilinear reads that same buffer. This is a DDR memory-mapped connection, not
an AXI4-Stream connection.

## Pipeline

```text
downsampled image Q14
        |
        v
CNN zero_dce_cnn_top
        |  m_axi write: A_low_q14
        v
DDR_A_LOW_Q14
        |  Bilinear m_axi read
        v
DDR_A_FULL_Q14
        |  Curve m_axi read
        v
Curve output buffer
```

One frame must keep the same buffer identity through each handoff. A later
implementation may use ping-pong buffers, but it must preserve the tensor
format and the completion ordering defined here.

## CNN to Bilinear

The CNN top is `zero_dce_cnn_top` in `fpga/hls/zero_dce_cnn_top.cpp`.

| Item | Contract |
|---|---|
| Tensor | `A_low_q14` |
| Shape | `[1, 3, 60, 106]` |
| Layout | C-contiguous planar NCHW, channel order R, G, B |
| Element type | signed INT16 two's complement |
| Fixed point | Q14, real value `raw / 16384` |
| Row padding | none |
| Byte order | little-endian |
| Elements | 19,080 |
| Bytes | 38,160 |
| DDR transport | CNN `m_axi` write, Bilinear `m_axi` read |

For an element at channel `c`, row `y`, and column `x`, the element index is
`((c * 60 + y) * 106 + x)` and the byte offset is twice that index.

The CNN caller must provide the already downsampled input in the same RGB
planar Q14 convention. The CNN does not crop, resize, or perform Bilinear
interpolation. Its `ap_ctrl_hs` `ap_done` event is the release condition for
Bilinear: Bilinear must not read `DDR_A_LOW_Q14` before `ap_done` is asserted.

The CNN output pointer is the existing `a_low_q14` AXI-Lite pointer. The
physical value of `DDR_A_LOW_Q14` is assigned by the Vivado address map or the
PS driver; this contract does not invent a fixed physical address.

## Bilinear to Curve

Bilinear reads all 38,160 bytes from `DDR_A_LOW_Q14` and produces the complete
parameter tensor in a separate buffer named `DDR_A_FULL_Q14`.

| Item | Contract |
|---|---|
| Tensor | `A_full_q14` |
| Shape | `[1, 3, 720, 1272]` |
| Layout | C-contiguous planar NCHW, channel order R, G, B |
| Element type | signed INT16 two's complement |
| Fixed point | Q14, real value `raw / 16384` |
| Row padding | none unless the integrated module explicitly documents a stride |
| Elements | 2,747,520 |
| Bytes | 5,495,040 |
| DDR transport | Bilinear write, Curve read |

Bilinear must signal completion before Curve reads `DDR_A_FULL_Q14`. The
`align_corners=True` integer interpolation rule is part of the numerical
contract: horizontal and vertical interpolation use the frozen Q14 rule,
nearest-even rounding, and INT16 saturation.

Curve receives the full-resolution parameter tensor, not `A_low`. The Curve
arithmetic uses Q15 intermediates. If the Curve top accepts Q14 at its
boundary, it must convert explicitly to Q15 before the first multiplication;
it must not reinterpret Q14 bits as Q15. The eight curve iterations, clamp
range, rounding, and final UINT8 conversion remain unchanged from the frozen
integer rule.

## Control and ownership

1. The producer of the downsampled image and model arrays flushes any PS cache
   lines before starting CNN.
2. The caller writes CNN pointer registers and asserts `ap_start` through the
   AXI4-Lite control interface.
3. CNN owns `DDR_A_LOW_Q14` until `ap_done`.
4. Bilinear owns `DDR_A_LOW_Q14` after CNN completion and owns
   `DDR_A_FULL_Q14` while producing the full-resolution tensor.
5. Curve reads `DDR_A_FULL_Q14` only after Bilinear completion and owns its
   output buffer until its completion event.
6. Buffers must not overlap. If the PS reads a completed buffer, it must
   invalidate the corresponding cache range first.
7. A single-buffer V1.1 invocation must finish before that buffer is reused.

The CNN implementation currently exposes AXI4 master bundles for input,
model arrays, output, and workspace, plus AXI4-Lite control. It has no AXI4
Stream output. The downstream modules may use separate master ports or an
AXI interconnect, but their DDR accesses must observe the ownership ordering
above.

## Acceptance checks

- CNN `A_low_q14` matches the fixed Q14 golden payload byte-for-byte.
- Bilinear consumes exactly 38,160 bytes and produces exactly 5,495,040
  bytes with the stated layout.
- Curve receives the same frame's `A_full_q14`; no stale or partially written
  tensor is accepted.
- The integrated design reports completion in the order
  `cnn_ap_done -> bilinear_done -> curve_done`.
- Vivado timing and board behavior are reported from the integrated V1.1
  implementation; HLS estimates alone do not establish hardware timing.

## Out of scope

This contract does not change the CNN's 14 convolution layers, quantization,
rounding, activation placement, Tanh LUT, or enhancement formula. It also
does not define physical DDR addresses, AXI-Lite register offsets generated by
Vivado, or an AXI4-Stream adapter. Those values belong to the system address
map and must be recorded when the integrated design is exported.
