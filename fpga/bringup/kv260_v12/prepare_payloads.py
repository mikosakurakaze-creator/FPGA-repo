"""Prepare checked local files only. This module has no board transport."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_layout(plan, regions):
    begin = int(plan["scratch_candidate"]["start"], 16)
    end = int(plan["scratch_candidate"]["end_exclusive"], 16)
    if end - begin != 64 * 1024 * 1024 or len(regions) != 30:
        raise ValueError("Frozen scratch/layout identity mismatch")
    previous = begin
    for r in sorted(regions, key=lambda x: x["address"]):
        a, n = r["address"], r["bytes"]
        if n <= 0 or a < previous or a + n > end:
            raise ValueError("Overlapping or out-of-range buffer/guard")
        previous = a + n
        slot = plan["slots"][r["slot"]]
        key = {"before": "guard_before", "after": "guard_after", "data": "address"}[r["kind"]]
        expected_n = slot["bytes"] if r["kind"] == "data" else slot["guard_bytes"]
        if a != int(slot[key], 16) or n != expected_n:
            raise ValueError("Region differs from frozen slot")
    if sum(r["bytes"] for r in regions) != 19025659:
        raise ValueError("Staging byte budget mismatch")


def tcl_word(value):
    text = str(value).replace("\\", "\\\\")
    for char in ('"', "$", "[", "]"):
        text = text.replace(char, "\\" + char)
    return '"' + text.replace("\n", "\\n").replace("\r", "\\r") + '"'


def tcl_value(value):
    if isinstance(value, dict):
        return "[dict create " + " ".join(tcl_word(k) + " " + tcl_value(v) for k, v in value.items()) + "]"
    if isinstance(value, list):
        return "[list " + " ".join(tcl_value(x) for x in value) + "]"
    return tcl_word(value)


def read_assets(data_root, manifest):
    assets = {}
    for name, rec in manifest["assets"].items():
        supplied = data_root / name
        if supplied.is_file():
            raw = supplied.read_bytes()
        elif "included_hex" in rec:
            raw = bytes.fromhex((ROOT / rec["included_hex"]).read_text(encoding="ascii"))
        else:
            raise FileNotFoundError("Obtain separately distributed asset: " + name)
        if len(raw) != rec["bytes"] or digest(raw) != rec["sha256"]:
            raise ValueError("Asset length/SHA mismatch: " + name)
        assets[name] = raw
    return assets


def prepare(data_root, output):
    manifest = load(ROOT / "manifest.json")
    plan = load(ROOT / "single_frame_plan.json")
    validate_layout(plan, manifest["regions"])
    for name, rec in manifest["libraries"].items():
        raw = (ROOT / name).read_bytes()
        if len(raw) != rec["bytes"] or digest(raw) != rec["sha256"]:
            raise ValueError("Reviewed library changed: " + name)
    assets = read_assets(Path(data_root), manifest)
    out = Path(output).resolve()
    if out.exists():
        raise FileExistsError("Choose a new output directory; never overwrite a previous attempt")
    out.mkdir(parents=True)
    data_dir = out / "data"
    data_dir.mkdir()
    for name, raw in assets.items():
        (data_dir / name).write_bytes(raw)
    slots = {}
    for name, s in plan["slots"].items():
        slots[name] = dict(address=int(s["address"], 16), bytes=s["bytes"],
                           golden=(data_dir / s["golden"]["asset"]).as_posix() if s["golden"] else "")
    regions = []
    for r in manifest["regions"]:
        s = plan["slots"][r["slot"]]
        if r["kind"] != "data":
            raw = bytes.fromhex(r["hex"])
        elif s["source"]:
            raw = assets[s["source"]["asset"]]
        else:
            raw = bytes([0xA5]) * r["bytes"]
        if len(raw) != r["bytes"] or digest(raw) != r["sha256"]:
            raise ValueError("Frozen staging payload mismatch: " + r["name"])
        p = out / (r["name"] + ".bin")
        p.write_bytes(raw)
        regions.append({k: v for k, v in r.items() if k != "hex"} | {"file": p.as_posix()})
    policy = dict(regions=regions, slots=slots, stages=plan["schedule"])
    (out / "core_policy.tcl").write_text(
        "# Host-prepared core policy only; not a live transport whitelist or board authorization.\n"
        "set sf_core_policy " + tcl_value(policy) + "\n", encoding="utf-8")
    receipt = dict(status="HOST_PREPARED_BOARD_NOT_AUTHORIZED", regions=30,
                   staging_bytes=19025659, board_operations=0,
                   sources={n: digest(v) for n, v in assets.items()},
                   policy_sha256=digest((out / "core_policy.tcl").read_bytes()))
    (out / "preparation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.data_root, args.output), indent=2))
