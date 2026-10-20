#!/usr/bin/env python3
"""Build and verify the experimental frame core; no vendor/board results implied."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
PINNED = {
    "weather_kernel_reference.cpp": "eb48f45cd25e884ff12e1fc8ec0562814595ac62aa29fc289d2e7c254053b349",
    "weather_kernel.h": "a678c4616a189bd8f9d2ccc4dcb4b183be1ca92f98d69eeffef69bb23813a47f",
    "params_derain.h": "d980ec138fe9fed6b08e90465199bb381369472fb652c4ec2b85c597b8e578f6",
    "params_dehaze.h": "19841d80f598738954d1b8efaa9288c203a14460312ca51e966a017322d0f186",
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=shutil.which("g++"))
    parser.add_argument("--delivery", type=Path, required=True, help="A-group a_compute directory (read only)")
    parser.add_argument("--output", type=Path, required=True, help="New run directory; will not overwrite a run")
    parser.add_argument("--full-frame", action="store_true")
    args = parser.parse_args()
    if not args.cxx:
        parser.error("pass --cxx /path/to/g++")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "pass": False,
              "scope": "portable host C++ only; not Vitis CSim, RTL, routed timing or board performance",
              "steps": [], "golden_nodes": [], "source_sha256": {}, "fixture_sha256": {}}
    env = os.environ.copy()
    compiler = Path(args.cxx).resolve()
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")

    def run(name, command, marker=None, expected_code=0):
        start = time.perf_counter()
        proc = subprocess.run([str(v) for v in command], env=env, capture_output=True,
                              text=True, errors="replace", timeout=240)
        log = out / (name + ".log")
        log.write_text(proc.stdout + proc.stderr, encoding="utf-8")
        passed = proc.returncode == expected_code and (marker is None or marker in proc.stdout)
        report["steps"].append({"name": name, "command": [str(v) for v in command],
            "return_code": proc.returncode, "host_seconds": time.perf_counter() - start,
            "log": log.name, "log_sha256": sha(log), "pass": passed})
        if not passed:
            raise RuntimeError(name + " failed; see " + str(log))
        print(name + " PASS", flush=True)
        return proc.stdout

    try:
        for filename, expected in PINNED.items():
            if sha(ROOT / "src" / filename) != expected:
                raise ValueError("pinned reference/parameters changed: " + filename)
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and path.suffix in (".cpp", ".h", ".py", ".cfg"):
                report["source_sha256"][path.relative_to(ROOT).as_posix()] = sha(path)
        delivery = args.delivery.resolve()
        manifest_path = delivery.parents[1] / "DELIVERY_MANIFEST.json"
        entries = {item["path"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8"))["files"]}
        report["a_delivery_manifest_sha256"] = sha(manifest_path)

        def verify_fixture(path):
            entry = entries[path.relative_to(manifest_path.parent).as_posix()]
            if path.stat().st_size != entry["bytes"] or sha(path) != entry["sha256"]:
                raise ValueError("A manifest mismatch: " + str(path))
            report["fixture_sha256"][path.relative_to(delivery).as_posix()] = sha(path)

        run("compiler", [compiler, "--version"])
        exe = out / ("test_weather_frame.exe" if os.name == "nt" else "test_weather_frame")
        command = [compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-Wno-unknown-pragmas", "-Wno-unused-label", "-I" + str(ROOT / "src"),
                   ROOT / "src/weather_frame.cpp", ROOT / "src/weather_kernel_reference.cpp",
                   ROOT / "tests/test_weather_frame.cpp", "-o", exe]
        if os.name == "nt":
            command += ["-static"]
        run("build", command)
        report["executable_sha256"] = sha(exe)
        # Compile the synthesis-selected source path and standalone vendor TB
        # using a host compiler. This proves neither HLS legality nor RTL timing.
        tb_exe = out / ("hls_tb_host.exe" if os.name == "nt" else "hls_tb_host")
        tb_command = [compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror",
                      "-Wno-unknown-pragmas", "-Wno-unused-label", "-D__SYNTHESIS__", "-DWEATHER_PORTABLE_SYNTH_TEST",
                      "-I" + str(ROOT / "src"), ROOT / "src/weather_frame.cpp",
                      ROOT / "hls/tb_weather_frame.cpp", "-o", tb_exe]
        if os.name == "nt":
            tb_command += ["-static"]
        run("hls_tb_host_build", tb_command)
        report["hls_tb_host_executable_sha256"] = sha(tb_exe)
        text = run("selftest", [exe, "selftest"], "HOST_SUITE_PASS")
        report["synthetic_30_node_cases"] = text.count("ALL_30_NODES_EXACT")
        report["synthetic_frame_cases"] = text.count("FRAME_EXACT")
        report["invalid_argument_cases"] = 11
        for task, name in enumerate(("derain", "dehaze")):
            fixture = delivery / "evidence/hls/trace_20261020" / name / "fixtures"
            for endpoint in ("input", "output"):
                verify_fixture(fixture / ("official_" + endpoint + ".bin"))
            run(name + "_official", [exe,"fixture",task,96,96,fixture/"official_input.bin",fixture/"official_output.bin"], "OFFICIAL_GOLDEN_EXACT")
            run(name + "_hls_tb_host_96", [tb_exe,task,96,96,fixture/"official_input.bin",
                fixture/"official_output.bin",out/(name+"_tb96_actual.bin")], "WEATHER_FRAME_GOLDEN_PASS")
            small = delivery / "evidence/hls/rtl_depth_fix_20261020" / name / "fixtures"
            for endpoint in ("input", "output"):
                verify_fixture(small / ("cosim_" + endpoint + ".bin"))
            run(name + "_hls_tb_host_8", [tb_exe,task,8,8,small/"cosim_input.bin",
                small/"cosim_output.bin",out/(name+"_tb8_actual.bin")], "WEATHER_FRAME_GOLDEN_PASS")
            for size, ref in ((96,fixture/"official_output.bin"),(8,small/"cosim_output.bin")):
                if (out/(name+"_tb"+str(size)+"_actual.bin")).read_bytes() != ref.read_bytes():
                    raise ValueError("standalone TB actual file mismatch")
            actual = out / (name + "_trace")
            actual.mkdir()
            run(name + "_trace", [exe,"trace_fixture",task,96,96,fixture/"official_input.bin",actual], "ALL_30_NODES_EXACT")
            expected = fixture / "reference_nodes"
            names = sorted(path.name for path in expected.glob("*.bin"))
            if len(names) != 30 or names != sorted(path.name for path in actual.glob("*.bin")):
                raise ValueError("exactly 30 Golden nodes required")
            for filename in names:
                ref, got = expected/filename, actual/filename
                verify_fixture(ref)
                equal = ref.read_bytes() == got.read_bytes()
                report["golden_nodes"].append({"task": name,"node": filename[:-4],"pass": equal,
                    "elements": ref.stat().st_size//2,"expected_sha256": sha(ref),"actual_sha256": sha(got)})
                if not equal:
                    raise ValueError("official node mismatch: " + name + "/" + filename)
            # A 1-LSB corruption must fail the same official-output comparator.
            corrupt = out / (name + "_corrupt.bin")
            data = bytearray((fixture/"official_output.bin").read_bytes()); data[0] ^= 1
            corrupt.write_bytes(data)
            run(name + "_negative_control", [exe,"fixture",task,96,96,fixture/"official_input.bin",corrupt], expected_code=2)
            if args.full_frame:
                for width in (1272,1280):
                    run(name + "_720x" + str(width), [exe,"reference",task,720,width,0,128], "FRAME_EXACT")
        report["pass"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        print(str(exc), file=sys.stderr)
    finally:
        report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (out/"verification.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["pass"] else 1

if __name__ == "__main__":
    sys.exit(main())
