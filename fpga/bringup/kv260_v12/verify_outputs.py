"""Full local file comparison against reviewed golden identities; no board access."""
from pathlib import Path
import argparse
import json
from prepare_payloads import ROOT, digest, load, read_assets


def verify(data_root, actual_dir):
    manifest = load(ROOT / "manifest.json")
    assets = read_assets(Path(data_root), manifest)
    actual_dir = Path(actual_dir)
    results = {}
    for ip, golden in [("cnn", "expected_a_low_q14.bin"),
                       ("bilinear", "expected_a_full_q14.bin"),
                       ("curve", "expected_enhanced_q14.bin")]:
        actual = (actual_dir / (ip + "_actual.bin")).read_bytes()
        expected = assets[golden]
        if actual != expected:
            raise ValueError("Full bit-exact mismatch: " + ip)
        results[ip] = dict(bit_exact="PASS", bytes=len(actual), sha256=digest(actual))
    return dict(status="LOCAL_OUTPUT_FILES_BIT_EXACT_PASS", outputs=results,
                board_operations=0, note="File comparison alone does not prove a new board run or guard/FPS result")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--actual-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.data_root, args.actual_dir), indent=2))
