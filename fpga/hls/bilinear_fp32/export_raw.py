"""Export validated Bilinear reference arrays as flat NCHW little-endian FP32."""

import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    names = ("parameters_lowres", "parameters_fullres")
    needed = [args.reference_dir / "metadata.json"] + [
        args.reference_dir / f"{name}.npy" for name in names
    ]
    missing = [str(path) for path in needed if not path.is_file()]
    if missing:
        parser.error("missing reference files:\n" + "\n".join(missing))
    metadata = json.loads(needed[0].read_text(encoding="utf-8"))
    if metadata["execution"]["scale_factor"] != 12:
        parser.error("reference scale_factor is not 12")

    manifest = {"source_metadata": metadata, "files": {}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, shape in (("parameters_lowres", [1, 3, 60, 106]),
                        ("parameters_fullres", [1, 3, 720, 1272])):
        source = args.reference_dir / f"{name}.npy"
        array = np.load(source, allow_pickle=False)
        entry = metadata["files"][source.name]
        if (list(array.shape) != shape or list(array.shape) != entry["shape"]
                or array.dtype != np.dtype("float32") or entry["layout"] != "NCHW"):
            parser.error(f"unexpected shape, dtype, or layout: {source}")
        raw = args.output_dir / f"{name}.f32"
        np.ascontiguousarray(array, dtype="<f4").tofile(raw)
        manifest["files"][raw.name] = {
            "source": source.name, "shape": shape, "layout": "NCHW",
            "dtype": "float32", "byte_order": "little", "elements": int(array.size),
        }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("exported parameters_lowres [1,3,60,106] and parameters_fullres [1,3,720,1272]")


if __name__ == "__main__":
    main()
