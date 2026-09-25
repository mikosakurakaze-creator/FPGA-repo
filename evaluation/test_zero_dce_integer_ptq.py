"""Focused checks for the exported integer arithmetic rules."""

import hashlib
import json

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from deployment import zero_dce_integer_ptq as q


def test_signed_round_to_nearest_ties_to_even():
    values = torch.tensor([-7, -5, -3, -1, 1, 3, 5, 7], dtype=torch.int64)
    assert q.round_div(values, 2).tolist() == [-4, -2, -2, 0, 0, 2, 2, 4]
    assert [q.round_div(int(value), 2) for value in values] == q.round_div(values, 2).tolist()


def test_integer_downsample_matches_pytorch_to_q14_precision():
    rng = np.random.default_rng(31)
    rgb = rng.integers(0, 256, (144, 240, 3), dtype=np.uint8)
    original, reduced = q.integer_downsample(rgb, 12)
    reference = torch.from_numpy(rgb.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255
    expected = F.interpolate(reference, scale_factor=1 / 12, mode="bilinear")
    assert original.shape == (1, 3, 144, 240)
    assert reduced.shape == (1, 3, 12, 20)
    assert torch.max(torch.abs(reduced.float() / q.Q14 - expected)) <= 1 / q.Q14


def test_integer_upsample_align_corners_and_error_bound():
    low = torch.tensor([[[[0, 1000], [2000, 3000]]]], dtype=torch.int16)
    actual = q.upsample_align_corners(low, 7, 13)
    expected = F.interpolate(low.float(), size=(7, 13), mode="bilinear", align_corners=True)
    assert actual[0, 0, 0, 0] == 0
    assert actual[0, 0, -1, -1] == 3000
    assert torch.max(torch.abs(actual.float() - expected)) <= 1


def test_tanh_lookup_and_curve_fixed_points():
    lut = q.build_tanh_lut()
    values = torch.tensor([[[[-32768, 0, 32767]]]], dtype=torch.int16)
    result = q.tanh_integer(values, 15, lut)
    assert int(result[0, 0, 0, 1]) == 0
    assert int(result[0, 0, 0, 0]) < 0 < int(result[0, 0, 0, 2])

    image = torch.tensor([[[[0, q.Q14]]]], dtype=torch.int16)
    parameter = torch.tensor([[[[10000, -10000]]]], dtype=torch.int16)
    enhanced, steps = q.enhance_integer(image, parameter)
    assert enhanced.tolist() == [[[[0, q.Q15]]]]
    assert len(steps) == 8


def test_a_low_q15_to_q14_rounding():
    source = torch.tensor([-5, -3, -1, 0, 1, 3, 5], dtype=torch.int16)
    converted = q.clamp_int16(q.rescale(source, 15, 14))
    assert converted.tolist() == [-2, -2, 0, 0, 0, 2, 2]


def test_saved_integer_artifacts_reproduce_original_image():
    output = q.HERE / "outputs" / "zero_dce_pp" / "quantization" / "integer"
    project = q.DEFAULT_PROJECT
    rgb = np.asarray(Image.open(project / "data" / "test" / "night_01.jpg").convert("RGB"))
    with np.load(output / "integer_weights.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    config = json.loads((project / "configs" / "zero_dce_pp_integer_rules.json").read_text(encoding="utf-8"))
    lookup = np.load(output / "tanh_q15_lut.npy", allow_pickle=False)
    nodes, png, _, _ = q.run_integer(rgb, arrays, config, lookup)
    a_low = nodes["parameters_lowres"][0]
    assert nodes["parameters_lowres"][1] == 14
    assert list(a_low.shape) == [1, 3, 60, 106]
    saved_a_low = np.load(output / "night_01_parameters_integer_q14.npy", allow_pickle=False)
    assert np.array_equal(a_low.numpy(), saved_a_low)
    manifest = json.loads((output / "night_01_a_low_q14_manifest.json").read_text(encoding="utf-8"))
    interface = json.loads((project / "configs" / "zero_dce_pp_a_low_interface.json").read_text(encoding="utf-8"))
    raw = (output / manifest["binary_file"]).read_bytes()
    assert manifest["shape_nchw"] == [1, 3, 60, 106]
    assert manifest["shape_nchw"] == interface["shape_nchw"]
    assert manifest["channel_order"] == ["R", "G", "B"]
    assert manifest["channel_order"] == interface["channel_order"]
    assert manifest["fractional_bits"] == interface["fractional_bits"] == 14
    assert manifest["byte_order"] == interface["byte_order"] == "little-endian"
    assert len(raw) == manifest["byte_count"] == interface["frame_size_bytes"] == 38160
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    assert np.array_equal(np.frombuffer(raw, dtype="<i2").reshape(1, 3, 60, 106), saved_a_low)
    expected = np.load(output / "night_01_enhanced_integer_q15.npy", allow_pickle=False)
    assert np.array_equal(nodes["enhanced"][0].numpy(), expected)
    saved_png = np.asarray(Image.open(output / "night_01_integer.png"))
    assert np.array_equal(png[0].permute(1, 2, 0).numpy(), saved_png)


def test_every_exported_layer_input_produces_its_golden_output():
    output = q.HERE / "outputs" / "zero_dce_pp" / "quantization" / "integer"
    manifest = json.loads((output / "night_01_layer_io_manifest.json").read_text(encoding="utf-8"))
    config = json.loads((q.HERE / "configs" / "zero_dce_pp_integer_rules.json").read_text(encoding="utf-8"))
    with np.load(output / "integer_weights.npz", allow_pickle=False) as archive:
        weights = {name: archive[name] for name in archive.files}
    with np.load(output / "night_01_layer_io.npz", allow_pickle=False) as archive:
        assert len(manifest["layers"]) == 14
        assert len(archive.files) == 28
        for name, spec in manifest["layers"].items():
            input_array = archive[spec["input_key"]]
            expected = archive[spec["output_key"]]
            assert input_array.dtype == np.int16
            assert expected.dtype == np.int16
            assert hashlib.sha256(input_array.tobytes(order="C")).hexdigest() == \
                spec["input_sha256_c_bytes"]
            assert hashlib.sha256(expected.tobytes(order="C")).hexdigest() == \
                spec["output_sha256_c_bytes"]
            assert list(input_array.shape) == spec["input_shape_nchw"]
            assert list(expected.shape) == spec["output_shape_nchw"]
            assert spec["input_scale"] == 2.0 ** -spec["input_frac"]
            assert spec["output_scale"] == 2.0 ** -spec["output_frac"]
            assert spec["input_zero_point"] == spec["output_zero_point"] == 0
            actual, frac, _, _, quantized_input = q.conv_integer(
                torch.from_numpy(input_array.copy()), spec["input_frac"],
                name, weights, config)
            assert frac == spec["output_frac"]
            assert np.array_equal(quantized_input.numpy(), input_array)
            assert np.array_equal(actual.numpy(), expected), name
