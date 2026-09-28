import json
import math
import re
from pathlib import Path

from deployment.export_hls_cnn_package import LAYER_NAMES


ROOT = Path(__file__).resolve().parents[1]


def test_hls_contract_matches_q14_a_low_contract():
    hls = json.loads(
        (ROOT / "configs" / "zero_dce_pp_hls_interface.json").read_text(
            encoding="utf-8"
        )
    )
    a_low = json.loads(
        (ROOT / "configs" / "zero_dce_pp_a_low_interface.json").read_text(
            encoding="utf-8"
        )
    )
    assert hls["top_function"] == "zero_dce_cnn_top"
    assert hls["input"]["shape_nchw"] == [1, 3, 60, 106]
    assert hls["output"]["shape_nchw"] == a_low["shape_nchw"]
    assert hls["output"]["fractional_bits"] == a_low["fractional_bits"] == 14
    assert hls["output"]["elements"] == hls["input"]["elements"] == 19080
    assert hls["output"]["bytes"] == a_low["frame_size_bytes"] == 38160
    assert hls["output"]["transport"] == "m_axi DDR write"


def test_hls_source_declares_ddr_top_and_workspace_size():
    source = (ROOT / "fpga" / "hls" / "zero_dce_cnn_top.cpp").read_text(
        encoding="utf-8"
    )
    header = (ROOT / "fpga" / "hls" / "zero_dce_cnn_top.h").read_text(
        encoding="utf-8"
    )
    assert 'extern "C" void zero_dce_cnn_top' in header
    assert "port=a_low_q14" in source
    assert "port=workspace_int16" in source
    assert "depth=1221120" in source
    assert "load_source_tile" in source
    assert "compute_depth_tile" in source
    assert "compute_point_tile" in source
    assert "store_output_tile" in source
    assert "round_shift_even" in source
    interface = json.loads(
        (ROOT / "configs" / "zero_dce_pp_hls_interface.json").read_text(
            encoding="utf-8"
        )
    )
    for bundle, ports in interface["memory_map"]["axi_bundles"].items():
        for port in ports:
            assert re.search(
                rf"#pragma HLS INTERFACE m_axi port={port} .* bundle={bundle} ",
                source,
            )


def test_hls_workspace_layout_contains_six_skip_slots():
    spatial = 60 * 106
    skip = 32 * spatial
    expected = 6 * skip
    hls = json.loads(
        (ROOT / "configs" / "zero_dce_pp_hls_interface.json").read_text(
            encoding="utf-8"
        )
    )
    assert hls["workspace"]["elements"] == expected
    assert hls["workspace"]["bytes"] == expected * 2


def test_hls_layer_table_matches_frozen_integer_rules():
    source = (ROOT / "fpga" / "hls" / "zero_dce_cnn_top.cpp").read_text(
        encoding="utf-8"
    )
    table = source.split("kZeroDceLayers[14] = {", 1)[1].split("};", 1)[0]
    rows = [
        tuple(int(value) for value in match.split(","))
        for match in re.findall(r"\{([\d, ]+)\}", table)
    ]
    rules = json.loads(
        (ROOT / "configs" / "zero_dce_pp_integer_rules.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(rows) == len(LAYER_NAMES) == 14
    weight_offset = bias_offset = 0
    for name, row in zip(LAYER_NAMES, rows):
        spec = rules[name]
        output_channels, weight_input_channels, kernel_h, kernel_w = spec[
            "weight_shape_oihw"
        ]
        groups = spec["groups"]
        input_channels = weight_input_channels * groups
        assert row == (
            input_channels,
            output_channels,
            groups,
            spec["input_frac"],
            spec["output_frac"],
            kernel_h,
            kernel_w,
            spec["padding"][0],
            spec["padding"][1],
            weight_offset,
            bias_offset,
            bias_offset,
        )
        weight_offset += math.prod(spec["weight_shape_oihw"])
        bias_offset += output_channels
    assert weight_offset == 10075
    assert bias_offset == 486
