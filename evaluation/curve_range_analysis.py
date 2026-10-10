"""Measure FP32 Curve reference and intermediate ranges without changing HLS code."""

import argparse
import json
from pathlib import Path

import numpy as np


NAMES = [
    "model_input",
    "parameters_fullres",
    *(f"enhancement_iter_{i:02d}" for i in range(1, 9)),
    "enhanced",
]
SIGNALS = ("x", "x_squared", "x_squared_minus_x", "a_times_delta")


def stats(array: np.ndarray) -> dict:
    minimum = float(np.min(array))
    maximum = float(np.max(array))
    return {
        "count": int(array.size),
        "min": minimum,
        "max": maximum,
        "max_abs": max(abs(minimum), abs(maximum)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir", type=Path)
    args = parser.parse_args()
    required = [args.reference_dir / f"{name}.npy" for name in NAMES]
    required.append(args.reference_dir / "metadata.json")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        parser.error("missing reference files:\n" + "\n".join(missing))

    metadata = json.loads((args.reference_dir / "metadata.json").read_text(encoding="utf-8"))
    shape = tuple(metadata["input"]["model_input_size_nchw"])
    arrays = {}
    for name in NAMES:
        array = np.load(args.reference_dir / f"{name}.npy", mmap_mode="r", allow_pickle=False)
        if array.dtype != np.dtype("float32") or array.shape != shape:
            parser.error(f"{name}.npy is not FP32 with expected shape {shape}")
        if not np.isfinite(array).all():
            parser.error(f"{name}.npy contains non-finite values")
        arrays[name] = array

    result = {
        "reference_dir": str(args.reference_dir),
        "shape_nchw": list(shape),
        "reference_arrays": {name: stats(array) for name, array in arrays.items()},
        "rounds": [],
    }
    x = np.array(arrays["model_input"], copy=True)
    a = arrays["parameters_fullres"]
    global_ranges = {}
    for round_number in range(1, 9):
        squared = np.multiply(x, x, dtype=np.float32)
        delta = np.subtract(squared, x, dtype=np.float32)
        term = np.multiply(a, delta, dtype=np.float32)
        signals = dict(zip(SIGNALS, (x, squared, delta, term)))
        round_ranges = {name: stats(array) for name, array in signals.items()}
        for name, values in round_ranges.items():
            if name not in global_ranges:
                global_ranges[name] = values.copy()
            else:
                overall = global_ranges[name]
                overall["count"] += values["count"]
                overall["min"] = min(overall["min"], values["min"])
                overall["max"] = max(overall["max"], values["max"])
                overall["max_abs"] = max(abs(overall["min"]), abs(overall["max"]))

        x = np.add(x, term, dtype=np.float32)
        reference = arrays[f"enhancement_iter_{round_number:02d}"]
        difference = np.abs(x.astype(np.float64) - reference.astype(np.float64))
        result["rounds"].append({
            "round": round_number,
            "signals_before_update": round_ranges,
            "max_abs_error_vs_reference": float(np.max(difference)),
            "mean_abs_error_vs_reference": float(np.mean(difference)),
        })

    final_difference = np.abs(x.astype(np.float64) - arrays["enhanced"].astype(np.float64))
    result["global_signals_before_update"] = global_ranges
    result["final_max_abs_error_vs_reference"] = float(np.max(final_difference))
    result["final_mean_abs_error_vs_reference"] = float(np.mean(final_difference))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
