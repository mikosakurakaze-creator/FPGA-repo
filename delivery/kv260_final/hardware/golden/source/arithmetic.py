"""Exact integer emulation of the audited V1 cast points.

Inputs to ``bilinear_pixel_raw`` and ``curve_pixel_raw`` are already signed
INT16 Q14 raw values. They must not be quantized again at the module boundary.
Python integers are unbounded; the tested V1 dimensions and CNN layer bounds
fit the corresponding HLS source types. This is a reference skeleton, not a
replacement for a complete CNN or a performance-oriented whole-frame model.
"""

from __future__ import annotations

import math
import struct
from fractions import Fraction
from typing import Sequence

Q14 = 1 << 14
Q32 = 1 << 32
FIXED16_MIN = -(1 << 15)
FIXED16_MAX = (1 << 15) - 1


def saturate_signed(value: int, bits: int) -> int:
    if bits < 2:
        raise ValueError("signed width must be at least 2")
    return min(max(int(value), -(1 << (bits - 1))), (1 << (bits - 1)) - 1)


def nearest_even_shift(value: int, shift: int) -> int:
    """WZH round_shift_even: signed nearest, midpoint to even integer."""
    value = int(value)
    if shift <= 0:
        return value * (1 << -shift)
    magnitude = abs(value)
    quotient, remainder = divmod(magnitude, 1 << shift)
    half = 1 << (shift - 1)
    if remainder > half or (remainder == half and quotient & 1):
        quotient += 1
    return -quotient if value < 0 else quotient


def ap_rnd_shift(value: int, shift: int) -> int:
    """AMD AP_RND on a binary fixed-point cast: nearest, midpoint to +inf.

    This matches the Vitis 2025.2 ``ap_fixed_base.h`` quantization_adjust:
    AP_RND increments whenever the first discarded bit is 1. For negative
    values the retained arithmetic-shift result is the floor, so ties rise
    toward positive infinity. No saturation is done in this function.
    """
    value = int(value)
    if shift <= 0:
        return value << -shift
    return (value + (1 << (shift - 1))) >> shift


def _check_int16_raw(value: int) -> int:
    value = int(value)
    if not FIXED16_MIN <= value <= FIXED16_MAX:
        raise ValueError("expected a signed INT16 raw value")
    return value


def decode_q14_le(payload: bytes) -> list[int]:
    """Decode little-endian signed Q14 bytes to raw integers, no requantize."""
    if len(payload) % 2:
        raise ValueError("Q14 payload has an odd byte count")
    return [raw for (raw,) in struct.iter_unpack("<h", payload)]


def encode_q14_le(values: Sequence[int]) -> bytes:
    """Encode already-quantized signed Q14 raw values, no requantize."""
    return b"".join(struct.pack("<h", _check_int16_raw(v)) for v in values)


def raw_q14_to_real(raw: int) -> float:
    return _check_int16_raw(raw) / Q14


def quantize_fixed16(value: float | Fraction) -> int:
    """Mimic ``ap_fixed<16,2,AP_RND,AP_SAT>(finite_fp_value)``.

    A Python float is interpreted as its exact binary value. Pass a
    ``Fraction`` for a specified exact rational source. FP32 data should first
    be loaded as FP32; conversion to Python float preserves that exact value.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NaN and Inf are not valid V1 numeric inputs")
        rational = Fraction.from_float(value)
    else:
        rational = Fraction(value)
    numerator = rational.numerator * Q14
    denominator = rational.denominator
    rounded = (2 * numerator + denominator) // (2 * denominator)
    return saturate_signed(rounded, 16)


def cnn_requantize_int16(
    accumulator_raw: int, input_frac: int, weight_frac: int, output_frac: int
) -> int:
    """One WZH convolution channel: INT32 accumulator -> INT16 output."""
    if not -(1 << 31) <= accumulator_raw <= (1 << 31) - 1:
        raise ValueError("CNN accumulator is outside signed INT32")
    shift = input_frac + weight_frac - output_frac
    return saturate_signed(nearest_even_shift(accumulator_raw, shift), 16)


def cnn_rescale_int16(value_raw: int, old_frac: int, new_frac: int) -> int:
    """WZH ``rescale_q16`` for activations and skip branches."""
    return saturate_signed(nearest_even_shift(_check_int16_raw(value_raw),
                                              old_frac - new_frac), 16)


def cnn_tanh_q15_to_q14(feature_raw_q16: int, lut_raw_q15: Sequence[int]) -> int:
    """WZH final Q16 -> Q8 LUT index -> Q15 -> signed Q14 boundary."""
    if len(lut_raw_q15) != 4097:
        raise ValueError("Tanh LUT must have 4097 signed INT16 entries")
    q8_index = max(-2048, min(2048, nearest_even_shift(
        _check_int16_raw(feature_raw_q16), 8)))
    tanh_raw_q15 = _check_int16_raw(lut_raw_q15[q8_index + 2048])
    return saturate_signed(nearest_even_shift(tanh_raw_q15, 1), 16)


def _source_coordinate_raw(output_index: int, input_size: int) -> tuple[int, int, int, int]:
    """Return coord Q32, neighbors and fractional weight Q32.

    coord_t / coord_t returns unsigned <80,48> with F=32 and integer division
    discards remainder. The cast to ratio_t <33,1> retains those 32 bits. The
    unsigned integer * ratio_t expression has F=32 and is exact here.
    """
    if input_size < 1 or output_index < 0 or output_index >= input_size * 12:
        raise ValueError("invalid V1 source/output size or output index")
    output_size = input_size * 12
    ratio_raw = 0 if output_size == 1 else ((input_size - 1) * Q32) // (output_size - 1)
    coord_raw = output_index * ratio_raw
    last_raw = (input_size - 1) * Q32
    if output_index == output_size - 1 or coord_raw > last_raw:
        coord_raw = last_raw
    lower = coord_raw // Q32
    upper = min(lower + 1, input_size - 1)
    weight_raw = coord_raw - lower * Q32
    return coord_raw, lower, upper, weight_raw


def bilinear_pixel_raw(
    low_nchw_raw: Sequence[int], input_height: int, input_width: int,
    channel: int, output_y: int, output_x: int,
) -> int:
    """One exact V1 ``bilinear_fixed16_buffered`` output scalar in Q14 raw.

    The two-row cache changes accesses only; this uses the same four source
    scalars. It reproduces ratio truncation, F=32 coordinates/weights, exact
    F=46 horizontal arithmetic, AP_RND F=78 -> F=60 vertical products, exact
    F=60 sum, then AP_RND/AP_SAT F=60 -> F=14.
    """
    if input_height < 1 or not 1 <= input_width <= 128 or not 0 <= channel < 3:
        raise ValueError("outside the V1 bilinear top's admitted dimensions")
    if len(low_nchw_raw) != 3 * input_height * input_width:
        raise ValueError("low-resolution NCHW buffer size mismatch")
    _, y0, y1, wy = _source_coordinate_raw(output_y, input_height)
    _, x0, x1, wx = _source_coordinate_raw(output_x, input_width)
    one_minus_wx = Q32 - wx
    one_minus_wy = Q32 - wy

    def at(y: int, x: int) -> int:
        return _check_int16_raw(low_nchw_raw[(channel * input_height + y) * input_width + x])

    v00, v01, v10, v11 = at(y0, x0), at(y0, x1), at(y1, x0), at(y1, x1)
    top_raw_q46 = one_minus_wx * v00 + wx * v01
    bottom_raw_q46 = one_minus_wx * v10 + wx * v11
    upper_raw_q60 = ap_rnd_shift(one_minus_wy * top_raw_q46, 18)
    lower_raw_q60 = ap_rnd_shift(wy * bottom_raw_q46, 18)
    result_raw_q60 = upper_raw_q60 + lower_raw_q60
    return saturate_signed(ap_rnd_shift(result_raw_q60, 46), 16)


def curve_pixel_raw(input_q14_raw: int, parameter_q14_raw: int) -> int:
    """One exact V1 ``curve_image_fixed16`` output scalar after eight rounds."""
    x = _check_int16_raw(input_q14_raw)
    parameter = _check_int16_raw(parameter_q14_raw)
    for _ in range(8):
        square_q28 = x * x
        delta_q28 = square_q28 - (x << 14)
        term_q42 = parameter * delta_q28
        updated_q42 = (x << 28) + term_q42
        x = saturate_signed(ap_rnd_shift(updated_q42, 28), 16)
    return x
