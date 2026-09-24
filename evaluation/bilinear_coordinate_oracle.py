"""Check the installed PyTorch bilinear module against an independent scalar oracle."""

import argparse
import inspect
import json
import math
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as functional


def sample_bilinear(source, n, c, out_y, out_x, out_h, out_w):
    in_h, in_w = source.shape[-2:]
    y = 0.0 if out_h == 1 else out_y * (in_h - 1) / (out_h - 1)
    x = 0.0 if out_w == 1 else out_x * (in_w - 1) / (out_w - 1)
    y = min(max(y, 0.0), float(in_h - 1))
    x = min(max(x, 0.0), float(in_w - 1))
    y0, x0 = math.floor(y), math.floor(x)
    y1, x1 = min(y0 + 1, in_h - 1), min(x0 + 1, in_w - 1)
    wy, wx = y - y0, x - x0
    v00 = float(source[n, c, y0, x0])
    v01 = float(source[n, c, y0, x1])
    v10 = float(source[n, c, y1, x0])
    v11 = float(source[n, c, y1, x1])
    result = (
        (1.0 - wy) * ((1.0 - wx) * v00 + wx * v01)
        + wy * ((1.0 - wx) * v10 + wx * v11)
    )
    return result, {
        "source_yx": [y, x],
        "neighbors_yx": [[y0, x0], [y0, x1], [y1, x0], [y1, x1]],
        "weights_yx": [wy, wx],
        "neighbor_values": [v00, v01, v10, v11],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    torch.set_num_threads(1)
    metadata = json.loads((args.reference_dir / "metadata.json").read_text(encoding="utf-8"))
    expected_version = metadata["execution"]["pytorch_version"]
    if torch.__version__ != expected_version:
        raise RuntimeError(f"PyTorch version mismatch: {torch.__version__} != {expected_version}")
    if metadata["execution"]["device"] != "cpu":
        raise RuntimeError("reference was not generated on CPU")

    module12 = torch.nn.UpsamplingBilinear2d(scale_factor=12)
    module2 = torch.nn.UpsamplingBilinear2d(scale_factor=2)
    small = torch.tensor([[[[0.0, 10.0, 40.0], [100.0, 130.0, 200.0]]]], dtype=torch.float32)
    small_output = module2(small)
    small_np = small.detach().numpy()
    small_out_np = small_output.detach().numpy()
    scalar_small_errors = []
    for oy in range(small_output.shape[-2]):
        for ox in range(small_output.shape[-1]):
            hand, _ = sample_bilinear(small_np, 0, 0, oy, ox, *small_output.shape[-2:])
            scalar_small_errors.append(abs(hand - float(small_out_np[0, 0, oy, ox])))
    align_false = functional.interpolate(small, scale_factor=2, mode="bilinear", align_corners=False)
    corners = [
        [0, 0], [0, small_output.shape[-1] - 1],
        [small_output.shape[-2] - 1, 0],
        [small_output.shape[-2] - 1, small_output.shape[-1] - 1],
    ]
    corner_results = [
        {"output_yx": p, "value": float(small_out_np[0, 0, *p])}
        for p in corners
    ]
    small_examples = []
    for oy, ox in [(0, 0), (0, 1), (1, 2), (2, 3), (3, 5)]:
        hand, details = sample_bilinear(small_np, 0, 0, oy, ox, *small_output.shape[-2:])
        small_examples.append({
            "output_yx": [oy, ox], "hand": hand,
            "torch": float(small_out_np[0, 0, oy, ox]), **details,
        })

    low = np.load(args.reference_dir / "parameters_lowres.npy", mmap_mode="r")
    full = np.load(args.reference_dir / "parameters_fullres.npy", mmap_mode="r")
    if low.shape != (1, 3, 60, 106) or full.shape != (1, 3, 720, 1272):
        raise RuntimeError(f"unexpected reference shape: {low.shape} -> {full.shape}")
    if low.dtype != np.float32 or full.dtype != np.float32:
        raise RuntimeError(f"unexpected reference dtype: {low.dtype} -> {full.dtype}")
    torch_full = module12(torch.from_numpy(np.array(low, copy=True))).detach().numpy()
    full_diff = np.abs(torch_full.astype(np.float64) - full.astype(np.float64))
    anchors = [(0, 0, 0), (0, 0, 1271), (0, 719, 0), (0, 719, 1271),
               (1, 0, 0), (1, 719, 1271), (2, 0, 1271), (2, 719, 0)]
    rng = random.Random(20260924)
    picks = anchors + [(rng.randrange(3), rng.randrange(720), rng.randrange(1272)) for _ in range(64)]
    sample_rows = []
    for c, oy, ox in picks:
        hand, details = sample_bilinear(low, 0, c, oy, ox, 720, 1272)
        sample_rows.append({
            "channel_yx": [c, oy, ox], "hand_double": hand,
            "reference": float(full[0, c, oy, ox]),
            "torch": float(torch_full[0, c, oy, ox]),
            "abs_error_vs_reference": abs(hand - float(full[0, c, oy, ox])),
            **details,
        })

    record = {
        "python_torch": {"torch": torch.__version__, "numpy": np.__version__,
                         "device": "cpu", "num_threads": torch.get_num_threads()},
        "reference_metadata_version": expected_version,
        "module12": {"type": type(module12).__name__, "repr": repr(module12),
                     "size": module12.size, "scale_factor": module12.scale_factor,
                     "mode": module12.mode, "align_corners": module12.align_corners,
                     "recompute_scale_factor": module12.recompute_scale_factor,
                     "source_file": inspect.getsourcefile(type(module12)),
                     "constructor_line": inspect.getsourcelines(type(module12).__init__)[1],
                     "forward_line": inspect.getsourcelines(torch.nn.Upsample.forward)[1]},
        "small": {
            "scale_factor": 2, "input_shape": list(small.shape),
            "output_shape": list(small_output.shape),
            "input": small_np[0, 0].tolist(), "output": small_out_np[0, 0].tolist(),
            "max_abs_error_hand_vs_torch": max(scalar_small_errors),
            "max_abs_diff_align_false_vs_module": float((align_false - small_output).abs().max()),
            "corner_results": corner_results, "examples": small_examples,
        },
        "reference": {
            "scale_factor": 12, "low_shape": list(low.shape), "full_shape": list(full.shape),
            "dtype": str(low.dtype), "torch_full_max_abs_error": float(full_diff.max()),
            "torch_full_mean_abs_error": float(full_diff.mean()),
            "torch_full_equal_count": int(np.count_nonzero(torch_full == full)),
            "elements": int(full.size),
            "sample_seed": 20260924, "sample_count": len(sample_rows),
            "hand_sample_max_abs_error": max(row["abs_error_vs_reference"] for row in sample_rows),
            "hand_sample_mean_abs_error": sum(row["abs_error_vs_reference"] for row in sample_rows) / len(sample_rows),
            "samples": sample_rows,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "torch": record["python_torch"]["torch"],
        "align_corners": module12.align_corners,
        "small_max_abs_error": record["small"]["max_abs_error_hand_vs_torch"],
        "full_torch_max_abs_error": record["reference"]["torch_full_max_abs_error"],
        "sample_hand_max_abs_error": record["reference"]["hand_sample_max_abs_error"],
        "sample_count": len(sample_rows),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
