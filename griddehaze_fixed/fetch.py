"""Fetch and verify the exact official outdoor source/checkpoint; no moving refs.

Downloaded upstream files stay outside the source distribution. The pinned tree
does not provide a license; this tool records that fact without granting rights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

COMMIT = "481399129614c3e7c8e892b5d52d60173131dda0"
UPSTREAM = "https://github.com/proteus1991/GridDehazeNet"
RAW = f"https://raw.githubusercontent.com/proteus1991/GridDehazeNet/{COMMIT}"
WEIGHT_NAME = "outdoor_haze_best_3_6"
WEIGHT_SHA256 = "80a8f3aad5fd0ed744f39bd60bda802087fbb48b2fa2ce86261ac443a4dba396"
FILES = {
    "model.py": (5417, "6ae3d8d5e22a1274df60e255f63735dc8a775993bad1732a9d66b63282bd482e"),
    "residual_dense_block.py": (1499, "f0aea1d55c0f91d056a43dfee5996985a60644d15ce5a0a257f1441661058213"),
    WEIGHT_NAME: (3889347, WEIGHT_SHA256),
    "README.md": (4922, "35073fb75ea5b82f31fbc8ebfcB306a6433fb125ebeb07b2289cb93402d196d2".lower()),
    "test.py": (3160, "038c25351d684e76df98d9debeeFA34bdc4f4e8261b54c99aba055414c33ad17".lower()),
    "val_data.py": (1502, "16aad94ebe35380b2e2b9f1a7dc70f815661712ef7a09b5226563f6561807d64"),
}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source(source_dir: str | Path) -> dict:
    """Reject any missing, modified, or accidentally substituted source file."""
    root = Path(source_dir)
    records = {}
    for name, (length, expected) in FILES.items():
        path = root / name
        if not path.is_file():
            raise ValueError(f"Missing pinned upstream file: {path}")
        actual = sha256(path)
        if path.stat().st_size != length or actual != expected:
            raise ValueError(f"Pinned upstream identity mismatch: {name}; sha256={actual}")
        records[name] = {"bytes": length, "sha256": actual, "url": f"{RAW}/{name}"}
    return records


def fetch(source_dir: str | Path) -> dict:
    root = Path(source_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, (length, expected) in FILES.items():
        target = root / name
        if target.exists():
            if target.stat().st_size != length or sha256(target) != expected:
                raise ValueError(f"Existing upstream file differs; preserve and inspect: {target}")
            continue
        request = urllib.request.Request(f"{RAW}/{name}", headers={"User-Agent": "griddehaze-fixed-a-v1"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if len(data) != length or actual != expected:
            raise ValueError(f"Downloaded upstream identity mismatch: {name}; sha256={actual}")
        # Exclusive creation prevents overwriting a concurrently created file.
        with target.open("xb") as handle:
            handle.write(data)
    records = verify_source(root)
    report = {
        "upstream": UPSTREAM, "commit": COMMIT, "files": records,
        "license": {"status": "no_license_file_in_pinned_upstream_tree",
                    "redistribution_permission": "not_established",
                    "action": "obtain_upstream_permission_before_redistribution"},
    }
    (root / "provenance.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    arguments = parser.parse_args()
    report = fetch(arguments.source_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
