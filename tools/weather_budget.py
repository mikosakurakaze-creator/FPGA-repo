#!/usr/bin/env python3
"""Estimate weather C8/C16 compute, tile geometry, and activation references."""

import argparse
import json
import math


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def tile_pixels(length, core, halo):
    covered = 0
    largest = 0
    for start in range(0, length, core):
        end = min(length, start + core)
        extent = min(length, end + halo) - max(0, start - halo)
        covered += extent
        largest = max(largest, extent)
    return covered, largest


def tile_extents(length, core, halo):
    extents = []
    for start in range(0, length, core):
        end = min(length, start + core)
        extents.append(min(length, end + halo) - max(0, start - halo))
    return extents


def valid_axis_taps(length, kernel, padding):
    total = 0
    for output_position in range(length):
        for kernel_position in range(kernel):
            input_position = output_position + kernel_position - padding
            if 0 <= input_position < length:
                total += 1
    return total


def current_kernel_accesses(height, width, channels, blocks, core, halo):
    """Count source-level INT16 activation references in the current C++ kernel."""
    reads = 0
    writes = 0
    valid_macs = 0
    processed_pixels = 0

    def add_convolution(tile_h, tile_w, input_channels, output_channels, kernel, groups):
        nonlocal reads, writes, valid_macs
        input_per_group = input_channels // groups
        valid_spatial_taps = (
            valid_axis_taps(tile_h, kernel, kernel // 2)
            * valid_axis_taps(tile_w, kernel, kernel // 2)
        )
        products = valid_spatial_taps * output_channels * input_per_group
        reads += products
        writes += tile_h * tile_w * output_channels
        valid_macs += products

    y_extents = tile_extents(height, core, halo)
    x_extents = tile_extents(width, core, halo)
    for tile_h in y_extents:
        for tile_w in x_extents:
            pixels = tile_h * tile_w
            processed_pixels += pixels
            add_convolution(tile_h, tile_w, 3, channels, 3, 1)
            # Stem ReLU.
            reads += channels * pixels
            writes += channels * pixels
            for _ in range(blocks):
                add_convolution(tile_h, tile_w, channels, channels, 3, channels)
                # Depthwise ReLU.
                reads += channels * pixels
                writes += channels * pixels
                add_convolution(tile_h, tile_w, channels, channels, 1, 1)
                # Residual add reads both operands and writes the skip tensor.
                reads += 2 * channels * pixels
                writes += channels * pixels
                # Block output ReLU.
                reads += channels * pixels
                writes += channels * pixels
            add_convolution(tile_h, tile_w, channels, 3, 1, 1)
            # Final input + tail residual, then output write.
            reads += 2 * 3 * pixels
            writes += 3 * pixels

    return {
        "processed_tile_pixels": processed_pixels,
        "valid_macs": valid_macs,
        "activation_read_elements_int16": reads,
        "activation_write_elements_int16": writes,
        "activation_read_bytes": reads * 2,
        "activation_write_bytes": writes * 2,
        "total_activation_reference_bytes": (reads + writes) * 2,
        "scope": (
            "Source-level activation array references in the current HLS C++; "
            "not measured DDR transactions. Excludes constants, AXI overhead, "
            "burst coalescing, and cache/interconnect effects."
        ),
    }


def estimate(height, width, channels, blocks, core, halo, fps, clock_mhz=100, current_dsp=37):
    macs_per_pixel = 27 * channels + blocks * (9 * channels + channels * channels) + 3 * channels
    parameter_weights = macs_per_pixel
    parameter_biases = channels + blocks * 2 * channels + 3

    tiled_height_pixels, largest_tile_height = tile_pixels(height, core, halo)
    tiled_width_pixels, largest_tile_width = tile_pixels(width, core, halo)
    tile_count = math.ceil(height / core) * math.ceil(width / core)
    frame_pixels = height * width
    frame_bytes = frame_pixels * 3 * 2
    tiled_frame_macs = tiled_height_pixels * tiled_width_pixels * macs_per_pixel
    # The experimental frame top computes the 1x1 tail only for output cores.
    fused_frame_macs = tiled_frame_macs - (tiled_height_pixels * tiled_width_pixels - frame_pixels) * 3 * channels
    minimum_frame_io = frame_bytes * 2
    largest_tile_pixels = largest_tile_height * largest_tile_width
    one_feature_plane = largest_tile_pixels * channels * 2
    current_access = current_kernel_accesses(height, width, channels, blocks, core, halo)
    ideal_mac_lanes = tiled_frame_macs * fps / (clock_mhz * 1e6)
    ideal_frame_seconds = tiled_frame_macs / (current_dsp * clock_mhz * 1e6)
    tile_input_bytes = current_access["processed_tile_pixels"] * 3 * 2
    tile_output_bytes = tile_input_bytes
    core_output_bytes = frame_pixels * 3 * 2
    optimized_external_bytes = tile_input_bytes + core_output_bytes
    current_activation_bytes = current_access["total_activation_reference_bytes"]
    staged_tile_ip_bytes = (
        tile_input_bytes       # source frame rows read by tile gather
        + tile_input_bytes     # gather writes the compact input buffer
        + tile_input_bytes     # IP reads the input buffer
        + tile_output_bytes    # IP writes the compact output buffer
        + core_output_bytes   # crop/scatter need only read the output core
        + core_output_bytes    # cropped core is written to output frame
    )

    return {
        "assumptions": {
            "input_output": "RGB NCHW contiguous signed INT16 Q14, same shape",
            "weights": "INT8 per-output-channel scales; INT32 biases and accumulators",
            "mac_count": "one multiply-accumulate is one MAC",
            "traffic_scope": "separate minimum I/O, tile-staging, and logical source-reference scenarios",
            "feature_memory_scope": "three live full tile feature planes; estimate only, not BRAM allocation",
        },
        "configuration": {
            "height": height,
            "width": width,
            "channels": channels,
            "residual_blocks": blocks,
            "core": core,
            "halo": halo,
            "fps": fps,
            "clock_mhz": clock_mhz,
            "comparison_mac_lanes": current_dsp,
        },
        "network_estimate": {
            "parameters_including_bias": parameter_weights + parameter_biases,
            "weight_int8_bytes": parameter_weights,
            "bias_int32_bytes": parameter_biases * 4,
            "weight_frac_bytes": parameter_biases,
            "macs_per_pixel": macs_per_pixel,
            "whole_frame_gmac": frame_pixels * macs_per_pixel / 1e9,
            "tiled_gmac": tiled_frame_macs / 1e9,
            "fused_core_only_tail_gmac": fused_frame_macs / 1e9,
            "fused_ideal_mac_lanes_at_clock": fused_frame_macs * fps / (clock_mhz * 1e6),
            "fused_ideal_minimum_mac_lanes_for_target": math.ceil(fused_frame_macs * fps / (clock_mhz * 1e6)),
            "tiled_required_gmac_per_second": tiled_frame_macs * fps / 1e9,
            "ideal_mac_lanes_at_clock": ideal_mac_lanes,
            "ideal_minimum_mac_lanes_for_target": math.ceil(ideal_mac_lanes),
            "comparison_mac_lanes": current_dsp,
            "comparison_ideal_gmac_per_second": current_dsp * clock_mhz / 1000,
            "comparison_ideal_frame_seconds": ideal_frame_seconds,
            "comparison_ideal_fps": 1 / ideal_frame_seconds,
            "target_workload_divided_by_comparison_capacity": ideal_mac_lanes / current_dsp,
            "compute_scope": (
                "Hypothetical one MAC per selected lane per clock, 100% utilization. "
                "DSP count is not effective MAC lanes: LUT multipliers, packing, "
                "non-MAC DSP use and scheduling can change the relationship. "
                "This is not a hard bound on the delivered IP."
            ),
        },
        "current_kernel_activation_traffic": current_access,
        "external_traffic_scenarios": {
            "fused_frame_top_ideal": {
                "description": (
                    "Target for a frame-level top that gathers tile rows directly "
                    "into on-chip windows, keeps intermediate activations on-chip, "
                    "and writes only core output pixels."
                ),
                "bytes_per_frame": optimized_external_bytes,
                "mbytes_per_second_at_target": optimized_external_bytes * fps / 1e6,
                "mib_per_second_at_target": optimized_external_bytes * fps / (1024 * 1024),
                "excludes": "DMA descriptors, alignment padding, input conversion, cache maintenance, and protocol overhead",
            },
            "existing_tile_abi_with_ddr_staging": {
                "description": (
                    "Keeps A's contiguous tile ABI and assumes DDR staging for "
                    "gathered input and full-tile output before core scatter; "
                    "intermediate activations are on-chip in the hypothetical optimized core."
                ),
                "bytes_per_frame": staged_tile_ip_bytes,
                "mbytes_per_second_at_target": staged_tile_ip_bytes * fps / 1e6,
                "mib_per_second_at_target": staged_tile_ip_bytes * fps / (1024 * 1024),
                "excludes": "DMA descriptors, alignment padding, input conversion, cache maintenance, and protocol overhead",
            },
            "current_source_reference_model": {
                "description": (
                    "Every source-level activation array reference in the current "
                    "DDR-scratch C++ is treated as an external transfer."
                ),
                "bytes_per_frame": current_activation_bytes,
                "gbytes_per_second_at_target": current_activation_bytes * fps / 1e9,
                "mbytes_per_second_at_target": current_activation_bytes * fps / 1e6,
                "excludes": "actual cache/burst coalescing and interconnect behavior; this is not a measurement",
            },
            "source_reference_to_fused_ideal_ratio_not_a_measured_speedup": (
                current_activation_bytes / optimized_external_bytes
                if optimized_external_bytes else None
            ),
        },
        "frame_memory": {
            "one_frame_buffer_bytes": frame_bytes,
            "input_plus_output_bytes": frame_bytes * 2,
            "double_buffered_input_output_bytes": frame_bytes * 4,
            "minimum_accelerator_bytes_per_frame": minimum_frame_io,
            "minimum_accelerator_mbytes_per_second": minimum_frame_io * fps / 1e6,
            "minimum_accelerator_mib_per_second": minimum_frame_io * fps / (1024 * 1024),
        },
        "tiling": {
            "tiles_y": math.ceil(height / core),
            "tiles_x": math.ceil(width / core),
            "tile_count": tile_count,
            "largest_input_tile_height": largest_tile_height,
            "largest_input_tile_width": largest_tile_width,
            "largest_tile_pixels": largest_tile_pixels,
            "one_int16_feature_plane_bytes": one_feature_plane,
            "three_int16_feature_planes_bytes_estimate": one_feature_plane * 3,
        },
        "limits": [
            "No HLS, synthesis, timing, bandwidth, or board performance is inferred.",
            "Logical activation references are not physical DDR transactions; system traces are required.",
            "External traffic scenarios exclude capture/display, cache effects, and protocol overhead.",
            "Feature storage estimate does not account for a particular line-buffer architecture.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--height", type=positive_int, default=720)
    parser.add_argument("--width", type=positive_int, default=1272)
    parser.add_argument("--channels", type=positive_int, choices=(8, 16), default=8)
    parser.add_argument("--blocks", type=positive_int, default=5)
    parser.add_argument("--core", type=positive_int, default=128)
    parser.add_argument("--halo", type=int, default=6)
    parser.add_argument("--fps", type=positive_int, default=30)
    parser.add_argument("--clock-mhz", type=positive_int, default=100)
    parser.add_argument("--mac-lanes", "--current-dsp", dest="current_dsp", type=positive_int, default=37,
                        help="hypothetical MAC lanes, not inferred from physical DSP count")
    parser.add_argument("--output", help="optional JSON output path")
    args = parser.parse_args()
    if args.halo < 0:
        parser.error("--halo must be non-negative")

    result = estimate(
        args.height, args.width, args.channels, args.blocks, args.core, args.halo,
        args.fps, args.clock_mhz, args.current_dsp
    )
    rendered = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
