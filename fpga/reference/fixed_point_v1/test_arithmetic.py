"""Small source-derived and Vitis HLS 2025.2 CSim-derived V1 checks."""

from __future__ import annotations

import unittest
import json
from fractions import Fraction
from pathlib import Path

try:
    from .arithmetic import (
        ap_rnd_shift, bilinear_pixel_raw, cnn_requantize_int16,
        cnn_rescale_int16, cnn_tanh_q15_to_q14,
        curve_pixel_raw, decode_q14_le, encode_q14_le, nearest_even_shift,
        quantize_fixed16, raw_q14_to_real, saturate_signed,
    )
except ImportError:  # permits unittest discover from this directory
    from arithmetic import (
        ap_rnd_shift, bilinear_pixel_raw, cnn_requantize_int16,
        cnn_rescale_int16, cnn_tanh_q15_to_q14,
        curve_pixel_raw, decode_q14_le, encode_q14_le, nearest_even_shift,
        quantize_fixed16, raw_q14_to_real, saturate_signed,
    )


LOW_2X3_NCHW = [
    -5760, -3000, -959, -4500, -2400, -1200,
    -4000, -2200, -1100, -3500, -1800, -1000,
    -4700, -2800, -1300, -3800, -2100, -1500,
]


class FixedPointV1Tests(unittest.TestCase):
    def test_protocol_json_structure(self) -> None:
        path = Path(__file__).resolve().parents[2] / "docs/v1_fixed_point_protocol.json"
        protocol = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(protocol["cnn_layers"]), 14)
        self.assertEqual(sum(len(layer["weight"]["fractional_bits_per_output_channel"])
                             for layer in protocol["cnn_layers"]), 486)
        self.assertEqual(protocol["cnn_output"]["external_format"]["fractional_bits"], 14)
        self.assertEqual(protocol["buffers"]["a_low"]["byte_count"], 38160)
        self.assertEqual(protocol["buffers"]["a_full"]["byte_count"], 5495040)
        self.assertEqual(protocol["bilinear"]["casts"][-1]["rounding"], "ap_rnd")
        self.assertEqual(protocol["curve"]["casts"][-1]["rounding"], "ap_rnd")

    def test_nearest_even_midpoint(self) -> None:
        # WZH round_shift_even(..., 1): +/-0.5 -> 0, +/-1.5 -> +/-2.
        self.assertEqual([nearest_even_shift(v, 1) for v in (1, 3, -1, -3)],
                         [0, 2, 0, -2])
        self.assertEqual([nearest_even_shift(v, 1) for v in (5, -5)], [2, -2])

    def test_ap_rnd_midpoint(self) -> None:
        # Confirmed by the vendor ap_fixed CSim oracle, including negative ties.
        self.assertEqual([ap_rnd_shift(v, 1) for v in (1, 3, -1, -3)],
                         [1, 2, 0, -1])
        self.assertEqual(quantize_fixed16(Fraction(1, 2 * 16384)), 1)
        self.assertEqual(quantize_fixed16(Fraction(-3, 2 * 16384)), -1)

    def test_saturation_boundaries(self) -> None:
        self.assertEqual(saturate_signed(32768, 16), 32767)
        self.assertEqual(saturate_signed(-32769, 16), -32768)
        self.assertEqual(quantize_fixed16(2.25), 32767)
        self.assertEqual(quantize_fixed16(-2.25), -32768)

    def test_signed_negative_rounding_and_shift_nonpositive(self) -> None:
        self.assertEqual(nearest_even_shift(-7, 2), -2)
        self.assertEqual(ap_rnd_shift(-6, 2), -1)
        self.assertEqual(nearest_even_shift(-3, 0), -3)
        self.assertEqual(nearest_even_shift(-3, -2), -12)
        self.assertEqual(cnn_requantize_int16(-3, 14, 1, 16), -6)

    def test_cnn_rescale_and_tanh_boundary(self) -> None:
        self.assertEqual(cnn_rescale_int16(-3, 14, 13), -2)
        lut = [0] * 4097
        lut[2048] = 3  # +1.5 Q14 LSB from Q15, nearest-even -> +2.
        self.assertEqual(cnn_tanh_q15_to_q14(0, lut), 2)
        lut[2048] = -3
        self.assertEqual(cnn_tanh_q15_to_q14(0, lut), -2)

    def test_raw_q14_decode_encode(self) -> None:
        raw = [0, 1, -1, -32768, 32767, -5760]
        payload = encode_q14_le(raw)
        self.assertEqual(decode_q14_le(payload), raw)
        self.assertEqual(payload[:6].hex(), "00000100ffff")
        self.assertEqual(raw_q14_to_real(-5760), -0.3515625)
        with self.assertRaises(ValueError):
            decode_q14_le(b"\x00")

    def test_wzh_q14_alow_known_vector(self) -> None:
        # First 16 genuine night_01 values from WZH commit 01580f0's exporter.
        # Full 38,160-byte vector SHA-256:
        # 31abdd23520d32efe75928ef394017bd2f515b2805144a85735eebc9481dddd1
        prefix = bytes.fromhex("eceea0efa0efdbef54f0ccf045f1bef1fbf1fbf182f1ccf017f0a0ef64efecee")
        expected = [-4372, -4192, -4192, -4133, -4012, -3892, -3771, -3650,
                    -3589, -3589, -3710, -3892, -4073, -4192, -4252, -4372]
        self.assertEqual(decode_q14_le(prefix), expected)
        self.assertEqual(encode_q14_le(expected), prefix)

    def test_bilinear_corner_preservation(self) -> None:
        for channel in range(3):
            for iy, oy in ((0, 0), (1, 23)):
                for ix, ox in ((0, 0), (2, 35)):
                    low_index = (channel * 2 + iy) * 3 + ix
                    self.assertEqual(
                        bilinear_pixel_raw(LOW_2X3_NCHW, 2, 3, channel, oy, ox),
                        LOW_2X3_NCHW[low_index],
                    )

    def test_bilinear_interior_vendor_csim(self) -> None:
        expected = [
            [-5549, -4060, -2641, -1260],
            [-3876, -2938, -1964, -1051],
            [-4553, -3480, -2405, -1528],
        ]
        points = [(1, 1), (7, 9), (12, 18), (22, 34)]
        for channel in range(3):
            for (oy, ox), raw in zip(points, expected[channel]):
                self.assertEqual(
                    bilinear_pixel_raw(LOW_2X3_NCHW, 2, 3, channel, oy, ox), raw
                )

    def test_curve_simple_known_input_vendor_csim(self) -> None:
        image = [0, 16384, 8192, 8192, 8192, 32767, -32768, 1]
        parameter = [-4096, -4096, 0, -4096, 4096, -4096, -4096, -5760]
        expected = [0, 16384, 8192, 14626, 1758, 17051, -32768, 1]
        self.assertEqual([curve_pixel_raw(x, a) for x, a in zip(image, parameter)],
                         expected)


if __name__ == "__main__":
    unittest.main()
