"""Validate the reference tensors and export flat NCHW float32 raw binaries."""

import argparse
import json
from pathlib import Path

import numpy as np


NAMES = [
    "model_input",
    "parameters_fullres",
    "enhanced",
    *(f"enhancement_iter_{index:02d}" for index in range(1, 9)),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    required = [args.reference_dir / f"{name}.npy" for name in NAMES]
    required.append(args.reference_dir / "metadata.json")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        parser.error("missing reference files:\n" + "\n".join(missing))

    metadata = json.loads((args.reference_dir / "metadata.json").read_text(encoding="utf-8"))
    arrays = {}
    for name in NAMES:
        array = np.load(args.reference_dir / f"{name}.npy", allow_pickle=False)
        expected = metadata["files"][f"{name}.npy"]
        if array.dtype != np.dtype("float32") or list(array.shape) != expected["shape"]:
            parser.error(f"{name}.npy dtype/shape differs from expected FP32 metadata")
        if expected["layout"] != "NCHW" or array.shape != tuple(metadata["input"]["model_input_size_nchw"]):
            parser.error(f"{name}.npy layout/shape is not the expected full-resolution NCHW tensor")
        arrays[name] = array

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, array in arrays.items():
        np.ascontiguousarray(array, dtype="<f4").tofile(args.output_dir / f"{name}.f32")

    manifest = {
        "source_metadata": metadata,
        "raw_format": {"dtype": "float32", "byte_order": "little", "layout": "NCHW", "shape": list(arrays["model_input"].shape)},
        "files": {f"{name}.f32": {"source": f"{name}.npy", "elements": int(array.size)} for name, array in arrays.items()},
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported {len(arrays)} tensors: shape {list(arrays['model_input'].shape)}, {arrays['model_input'].size} float32 elements each")


if __name__ == "__main__":
    main()
