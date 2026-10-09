"""Prepare a bounded two-frame approval plan; never connects to hardware.

Input is the public single-frame reproduction plan and checked assets. No board runner
or UART/JTAG process is invoked. The output remains NOT_AUTHORIZED_NOT_EXECUTED.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


EXPECTED_SIZES = {
    "INPUT_Q14": 38160, "WEIGHTS_INT8": 10075, "BIAS_INT32": 1944,
    "WEIGHT_FRAC": 486, "TANH_LUT_Q15": 8194, "A_LOW_Q14": 38160,
    "WORKSPACE_INT16": 2442240, "A_FULL_Q14": 5495040,
    "MODEL_INPUT_Q14": 5495040, "ENHANCED_Q14": 5495040,
}
EXPECTED_AP = {"cnn": 0xA0020000, "bilinear": 0xA0000000, "curve": 0xA0010000}
EXPECTED_PLAN_SHA = "ab7ec6409049a90e4e0b0decc3a82915536f839adbf0df66d15933f4a22f159f"
EXPECTED_MAP_SHA = "6a5d709c0372b6891490dc520979fe6bcfcd1dcc2ad8bcc0bcd97a8b37a5c9b8"
EXPECTED_SCOPE_SHA = "12c318bf3add448c1e57704fdc67c8d1784d6850823b5b79e804fe802ce397c8"
SHARED = Path(__file__).resolve().parents[2] / "bringup" / "kv260_v12"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scope_digest(plan):
    scope = copy.deepcopy({k: plan[k] for k in ("frame", "scratch_candidate", "slots", "schedule")})
    for slot in scope["slots"].values():
        for role in ("source", "golden"):
            if slot.get(role):
                slot[role].pop("path", None)
                slot[role].pop("asset", None)
    return hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare(plan, manifest, assets, plan_sha, manifest_sha):
    require(scope_digest(plan) == EXPECTED_SCOPE_SHA,
            "Successful data/addresses/27 arguments changed; review a new scope explicitly")
    require(plan["frame"] == "night_01", "Unexpected input frame")
    slots = plan["slots"]
    require(set(slots) == set(EXPECTED_SIZES), "Unexpected buffers")
    lo = number(plan["scratch_candidate"]["start"])
    hi = number(plan["scratch_candidate"]["end_exclusive"])
    require((lo, hi) == (0x20000000, 0x24000000), "Unexpected diagnostic scratch")
    spans, files = [], []
    staging, chunks = 0, 0
    for name, slot in slots.items():
        size, address = slot["bytes"], number(slot["address"])
        require(size == EXPECTED_SIZES[name], "Wrong buffer size: " + name)
        require(address % 16 == 0, "Unaligned buffer: " + name)
        require(slot["guard_bytes"] == 64, "Unexpected guard size")
        before, after = number(slot["guard_before"]), number(slot["guard_after"])
        require(before == address - 64 and after == address + size, "Nonadjacent guard")
        for start, count in ((before, 64), (address, size), (after, 64)):
            require(lo <= start < start + count <= hi, "Buffer outside scratch")
            spans.append((start, start + count, name))
            staging += count
            chunks += (count + 65535) // 65536
        for role in ("source", "golden"):
            entry = slot.get(role)
            if entry:
                asset = entry.get("asset") or Path(entry["path"]).name
                raw = assets[asset]
                require(entry["bytes"] == size and len(raw) == size,
                        "Payload size mismatch: " + name)
                require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "Payload SHA mismatch: " + name)
                require(manifest["assets"][asset]["bytes"] == size
                        and manifest["assets"][asset]["sha256"] == entry["sha256"],
                        "Shared manifest identity changed: " + asset)
                files.append({"slot": name, "role": role, "bytes": size,
                              "sha256": entry["sha256"], "asset": asset})
    ordered = sorted(spans)
    require(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), "Overlapping regions")
    require(staging == plan["scratch_candidate"]["initial_DDR_staging_bytes"] == 19025659,
            "Unexpected staging-byte budget")
    require(chunks == 316, "Unexpected chunk budget")
    require([s["ip"] for s in plan["schedule"]] == ["cnn", "bilinear", "curve"],
            "Wrong stage order")
    args = 0
    for stage in plan["schedule"]:
        ip = stage["ip"]
        base = number(stage["AP_CTRL"])
        require(base == EXPECTED_AP[ip],
                "Wrong AP_CTRL address")
        require(stage["start"]["attempts"] == 1 and number(stage["start"]["value"]) == 1
                and number(stage["start"]["address"]) == base, "Unexpected start protocol")
        writes = stage["argument_writes"]
        require(stage["poll"]["max_reads"] == 100
                and stage["poll"]["nominal_deadline_ms"] == 5000
                and stage["poll"]["retry"] == 0, "Unexpected completion bound")
        args += len(writes)
    require(args == 27, "Unexpected argument count")
    require(len(manifest["regions"]) == 30 and len(files) == 9 and len(assets) == 9,
            "Unexpected shared payload/region set")
    frames = []
    for index, poison in enumerate((0xA5, 0x5A)):
        regions = []
        for original in manifest["regions"]:
            region = {k: v for k, v in original.items() if k != "hex"}
            slot = slots[region["slot"]]
            key = {"before": "guard_before", "after": "guard_after", "data": "address"}[region["kind"]]
            require(region["address"] == number(slot[key])
                    and region["bytes"] == (slot["bytes"] if region["kind"] == "data" else 64),
                    "Manifest region differs from exact frozen layout")
            if region["kind"] != "data":
                value = 0xD3 if region["kind"] == "before" else 0xE7
                raw = bytes([value]) * 64
                region["generated_byte"] = hex(value)
                require(bytes.fromhex(original["hex"]) == raw, "Unexpected guard pattern")
            elif slot["source"]:
                asset = slot["source"].get("asset") or Path(slot["source"]["path"]).name
                raw = assets[asset]
                region["asset"] = asset
            else:
                raw = bytes([poison]) * region["bytes"]
                region["generated_byte"] = hex(poison)
            raw_sha = hashlib.sha256(raw).hexdigest()
            if index == 0 or region["kind"] != "data" or slot["source"]:
                require(raw_sha == original["sha256"], "Original region payload identity mismatch")
            region["sha256"] = raw_sha
            regions.append(region)
        frames.append({"frame_index": index, "input_id": "night_01", "regions": regions,
                       "schedule": copy.deepcopy(plan["schedule"]),
                       "goldens": [f for f in files if f["role"] == "golden"]})
    result = {
        "schema_version": 1, "status": "HOST_PREPARED_NOT_AUTHORIZED_NOT_EXECUTED",
        "scope": "TWO_SERIAL_REPEAT_FRAMES_ONLY", "frames": frames,
        "frame_poison_bytes": ["0xA5", "0x5A"],
        "source_plan_sha256": plan_sha, "shared_manifest_sha256": manifest_sha,
        "scope_identity_sha256": EXPECTED_SCOPE_SHA,
        "historical_single_frame_plan_sha256": EXPECTED_PLAN_SHA,
        "historical_register_map_sha256": EXPECTED_MAP_SHA,
        "scratch": {"start": hex(lo), "end_exclusive": hex(hi),
                    "ownership": "REQUIRES_NEW_EXPLICIT_DEDICATION_AND_OVERWRITE_PERMISSION",
                    "regions": [{"start": hex(a), "end_exclusive": hex(b), "slot": n}
                                for a, b, n in ordered]},
        "payloads": files,
        "budgets": {"DDR_SET_bytes": staging * 2, "DDR_SET_chunks": chunks * 2,
                    "parameter_SET": args * 2, "AP_START_by_ip": dict.fromkeys(EXPECTED_AP, 2),
                    "CSR_SET_bytes": (args + 3) * 4 * 2, "total_SET": (chunks + args + 3) * 2,
                    "core_GET_cap": 884 * 2, "PS_GET_cap": 177 * 2, "CONFIG_read_cap": 8 * 2,
                    "poll_reads_per_start": 100, "deadline_ms_per_start": 5000,
                    "complete_output_comparisons": 6, "stage_guard_comparisons": 120,
                    "initial_guard_readbacks": 40, "UART_dcache_read_only_commands": 1},
        "cache": {"required_fresh_state": "OFF", "writes": 0, "MMU": "NOT_ASSESSED"},
        "forbidden": ["program", "reset", "psu_init", "GPIO_WRITE", "PMU_WRITE",
                      "clock_write", "isolation_write", "cache_write", "MMU_write",
                      "storage_write", "auto_restart", "retry", "rollback"],
        "frame_barrier": "All three full bit-exact outputs and all guards must pass before restaging",
        "runner": "NEW_BOUNDED_ADAPTER_REQUIRES_HOST_OFFLINE_REVIEW; spent execute_once is never replayed",
        "BOARD_MULTI_FRAME": "NOT_TESTED", "BOARD_30FPS": "NOT_TESTED",
        "board_operations_this_tool": 0,
    }
    audit_two_frame_budget(result)
    return result


def audit_two_frame_budget(candidate):
    """Offline candidate audit only; not an execution-budget enforcement claim."""
    require(len(candidate["frames"]) == 2, "Frame budget exceeded")
    starts = dict.fromkeys(EXPECTED_AP, 0)
    parameters = staging = chunks = 0
    for i, frame in enumerate(candidate["frames"]):
        require(frame["frame_index"] == i and len(frame["regions"]) == 30, "Wrong frame/region count")
        for region in frame["regions"]:
            staging += region["bytes"]
            chunks += (region["bytes"] + 65535) // 65536
        require([s["ip"] for s in frame["schedule"]] == list(EXPECTED_AP), "Stage budget exceeded")
        for stage in frame["schedule"]:
            require(stage["start"]["attempts"] == 1, "Start budget exceeded")
            starts[stage["ip"]] += stage["start"]["attempts"]
            parameters += len(stage["argument_writes"])
    actual = {"DDR_SET_bytes": staging, "DDR_SET_chunks": chunks, "parameter_SET": parameters,
              "AP_START_by_ip": starts, "CSR_SET_bytes": (parameters + sum(starts.values())) * 4,
              "total_SET": chunks + parameters + sum(starts.values())}
    for key, value in actual.items():
        require(candidate["budgets"][key] == value, "Declared budget differs from exact frame plan: " + key)
    require(staging == 38051318 and chunks == 632 and parameters == 54
            and starts == dict.fromkeys(EXPECTED_AP, 2), "Frozen two-frame budget changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single-frame-plan", type=Path, default=SHARED / "single_frame_plan.json")
    parser.add_argument("--manifest", type=Path, default=SHARED / "manifest.json")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Refusing to overwrite an existing approval plan")
    plan = json.loads(args.single_frame_plan.read_text(encoding="utf-8-sig"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    spec = importlib.util.spec_from_file_location("shared_payloads", SHARED / "prepare_payloads.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assets = helper.read_assets(args.data_root, manifest)
    result = prepare(plan, manifest, assets, digest(args.single_frame_plan), digest(args.manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("HOST_ONLY_TWO_FRAME_PLAN_SAVED; NOT_AUTHORIZED; BOARD_OPERATIONS=0")


if __name__ == "__main__":
    main()
