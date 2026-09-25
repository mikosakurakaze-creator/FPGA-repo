"""Pack the generated integer model arrays for zero_dce_cnn_top.

The output directory is intentionally ignored by Git. The HLS top consumes
the downsampled Q14 input and four model arrays. This script also includes the
expected Q14 output so C simulation can compare every scalar.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


LAYER_NAMES = [
    "e_conv1.depth_conv", "e_conv1.point_conv",
    "e_conv2.depth_conv", "e_conv2.point_conv",
    "e_conv3.depth_conv", "e_conv3.point_conv",
    "e_conv4.depth_conv", "e_conv4.point_conv",
    "e_conv5.depth_conv", "e_conv5.point_conv",
    "e_conv6.depth_conv", "e_conv6.point_conv",
    "e_conv7.depth_conv", "e_conv7.point_conv",
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integer-dir",
        type=Path,
        default=Path("outputs/zero_dce_pp/quantization/integer"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/zero_dce_pp/quantization/hls_cnn"),
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("configs/zero_dce_pp_integer_rules.json"),
    )
    args = parser.parse_args()
    rules = json.loads(args.rules.read_text(encoding="utf-8"))
    archive = np.load(args.integer_dir / "integer_weights.npz", allow_pickle=False)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    packed_weights = []
    packed_bias = []
    packed_frac = []
    layers = {}
    weight_offset = bias_offset = frac_offset = 0
    for name in LAYER_NAMES:
        spec = rules[name]
        weights = np.asarray(archive[name + ".weight_int8"], dtype=np.int8)
        bias = np.asarray(archive[name + ".bias_int32"], dtype=np.int32)
        fractions = np.asarray(spec["weight_frac_per_output_channel"], dtype=np.int8)
        if tuple(weights.shape) != tuple(spec["weight_shape_oihw"]):
            raise ValueError("weight shape differs from frozen rules: " + name)
        if bias.shape != fractions.shape or bias.size != weights.shape[0]:
            raise ValueError("bias/fraction channel count differs: " + name)
        packed_weights.append(weights.reshape(-1))
        packed_bias.append(bias.reshape(-1))
        packed_frac.append(fractions.reshape(-1))
        layers[name] = {
            "weight_offset": weight_offset,
            "weight_elements": int(weights.size),
            "bias_offset": bias_offset,
            "output_channels": int(bias.size),
            "weight_frac_offset": frac_offset,
            "input_frac": spec["input_frac"],
            "output_frac": spec["output_frac"],
            "groups": spec["groups"],
            "weight_shape_oihw": spec["weight_shape_oihw"],
        }
        weight_offset += weights.size
        bias_offset += bias.size
        frac_offset += fractions.size

    vectors = np.load(
        args.integer_dir / "night_01_integer_test_vectors.npz", allow_pickle=False
    )
    input_q14 = np.asarray(vectors["input_downsampled"], dtype="<i2")
    expected_q14 = np.asarray(
        np.load(
            args.integer_dir / "night_01_parameters_integer_q14.npy",
            allow_pickle=False,
        ),
        dtype="<i2",
    )
    if input_q14.shape != (1, 3, 60, 106):
        raise ValueError("CNN input must have shape [1,3,60,106]")
    if expected_q14.shape != (1, 3, 60, 106):
        raise ValueError("A_low reference must have shape [1,3,60,106]")
    golden_bytes = (
        args.integer_dir / "night_01_a_low_q14_nchw_le.bin"
    ).read_bytes()
    if expected_q14.tobytes(order="C") != golden_bytes:
        raise ValueError("A_low .npy and DDR golden payload disagree")

    arrays = {
        "input_q14.bin": input_q14,
        "weights_int8.bin": np.concatenate(packed_weights).astype("<i1", copy=False),
        "bias_int32.bin": np.concatenate(packed_bias).astype("<i4", copy=False),
        "weight_frac.bin": np.concatenate(packed_frac).astype("<i1", copy=False),
        "tanh_lut_q15.bin": np.asarray(
            np.load(args.integer_dir / "tanh_q15_lut.npy", allow_pickle=False),
            dtype="<i2",
        ),
        "expected_a_low_q14.bin": expected_q14,
    }
    expected_counts = {
        "input_q14.bin": 19080,
        "weights_int8.bin": 10075,
        "bias_int32.bin": 486,
        "weight_frac.bin": 486,
        "tanh_lut_q15.bin": 4097,
        "expected_a_low_q14.bin": 19080,
    }
    for filename, expected_count in expected_counts.items():
        if arrays[filename].size != expected_count:
            raise ValueError("unexpected element count in " + filename)
    manifest = {
        "schema_version": 1,
        "top_function": "zero_dce_cnn_top",
        "source_interface": "configs/zero_dce_pp_hls_interface.json",
        "arrays": {},
        "layers": layers,
        "notes": [
            "All files are raw little-endian arrays with no header or padding.",
            "The HLS top expects pointers to the first element of each array.",
            "expected_a_low_q14.bin is a comparison oracle, not an IP input.",
            "Generated artifacts are local and ignored by Git.",
        ],
    }
    for filename, array in arrays.items():
        data = array.tobytes(order="C")
        (args.output_dir / filename).write_bytes(data)
        manifest["arrays"][filename] = {
            "dtype": str(array.dtype),
            "elements": int(array.size),
            "bytes": len(data),
            "sha256": sha256(data),
        }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
