#!/usr/bin/env python3
"""Stage immutable frame-core HLS runs and require real vendor artifacts."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("prepare", "preflight", "csim", "synth", "cosim", "package")
SOURCES = ("src/weather_frame.cpp", "src/weather_frame.h", "src/weather_kernel.h",
           "src/params_derain.h", "src/params_dehaze.h", "hls/tb_weather_frame.cpp")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assess(stage, log, component, actual=None, expected=None):
    """Exit zero and requested pragmas alone never establish HLS success."""
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    reasons, artifacts = [], {}
    if re.search(r"(?mi)^\s*(ERROR|FATAL)(:|\s)|fatal error:", text):
        reasons.append("vendor error in log")
    if stage == "preflight":
        if not (re.search(r"(?i)vitis", text) and re.search(r"20\d\d\.\d", text)):
            reasons.append("nonempty Vitis version banner absent")
    if stage in ("csim", "cosim"):
        marker = "WEATHER_FRAME_GOLDEN_PASS" if stage == "csim" else "C/RTL co-simulation finished: PASS"
        if marker not in text:
            reasons.append("required simulation PASS marker absent")
        if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
            reasons.append("actual tensor absent or differs from Golden bytes")
        else:
            artifacts[str(actual)] = sha(actual)
    if stage == "synth":
        for path in component.rglob("*csynth.xml"):
            try:
                xml = ET.parse(path).getroot()
                if (xml.findtext("UserAssignments/TopModelName") == "weather_frame_top"
                        and xml.find("AreaEstimates/Resources") is not None):
                    artifacts[str(path)] = sha(path)
            except ET.ParseError:
                pass
        if not artifacts:
            reasons.append("frame top synthesis resource XML absent")
    if stage == "package":
        for path in component.rglob("*.zip"):
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    if any(n.endswith("component.xml") for n in archive.namelist()):
                        artifacts[str(path)] = sha(path)
        if not artifacts:
            reasons.append("exported IP ZIP with component.xml absent")
    return {"pass": not reasons, "reasons": reasons, "artifact_sha256": artifacts}


def invoke(name, command, folder, settings, timeout):
    command = [str(v) for v in command]
    env = os.environ.copy()
    if os.name == "nt":
        # Batch syntax has separate escaping rules. Restrict paths before quoting.
        for value in command + ([str(settings)] if settings else []):
            if any(c in value for c in '\r\n"&|<>^%!'):
                raise ValueError("unsupported batch metacharacter in argument")
        wrapper = folder / (name + ".cmd")
        lines = ["@echo off", "setlocal", 'set "PROCESSOR_ARCHITECTURE=AMD64"']
        if settings:
            lines += ['call "' + str(settings) + '"', "if errorlevel 1 exit /b %errorlevel%"]
        lines += ["call " + " ".join('"' + v + '"' for v in command), "exit /b %errorlevel%"]
        with wrapper.open("x", encoding="utf-8", newline="") as stream:
            stream.write("\r\n".join(lines) + "\r\n")
        argv = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "call", str(wrapper)]
    else:
        if settings:
            raise ValueError("source the vendor settings in the parent shell on Linux")
        argv = command
    log = folder / (name + ".log")
    print("Running " + name + ": " + str(log), flush=True)
    with log.open("xb") as stream:
        proc = subprocess.run(argv, cwd=folder, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, timeout=timeout)
    return log, {"command": command, "exit_code": proc.returncode,
                 "log": str(log), "log_sha256": sha(log)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--delivery", type=Path, required=True, help="read-only A a_compute directory")
    p.add_argument("--host-report", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True, help="new ASCII path without spaces")
    p.add_argument("--vitis-bin", type=Path)
    p.add_argument("--settings", type=Path)
    p.add_argument("--task", choices=("both", "derain", "dehaze"), default="both")
    p.add_argument("--through", choices=STAGES, default="preflight")
    p.add_argument("--part", default="xck26-sfvc784-2LV-c")
    p.add_argument("--clock-ns", type=float, default=10.0)
    p.add_argument("--stage-timeout", type=int, default=7200)
    a = p.parse_args()
    out = a.output.resolve()
    if not re.fullmatch(r"[A-Za-z0-9_:/\\.\-]+", str(out)):
        p.error("output path must use ASCII letters/digits, slash, colon, dot, underscore or hyphen")
    if not math.isfinite(a.clock_ns) or a.clock_ns <= 0 or a.stage_timeout <= 0:
        p.error("positive clock and timeout required")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.part):
        p.error("invalid part")
    out.mkdir(parents=True, exist_ok=False)
    report = {"pass": False, "requested_through": a.through, "completed_through": None,
              "scope": "HLS only; no routed timing or board claims", "steps": {},
              "started_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        host = json.loads(a.host_report.read_text(encoding="utf-8"))
        if host.get("pass") is not True:
            raise ValueError("passing host report required")
        # Bind all current experiment sources and scripts to the passing host run.
        current = {f.relative_to(ROOT).as_posix(): sha(f) for f in ROOT.rglob("*")
                   if f.is_file() and f.suffix in (".cpp", ".h", ".py", ".cfg")}
        if host.get("source_sha256") != current:
            raise ValueError("host report predates current experiment sources; rerun verify_host.py")
        report["host_report_sha256"] = sha(a.host_report)
        report["source_sha256"] = current
        delivery = a.delivery.resolve()
        manifest_path = delivery.parents[1] / "DELIVERY_MANIFEST.json"
        manifest = {v["path"]: v for v in json.loads(manifest_path.read_text(encoding="utf-8"))["files"]}
        report["a_manifest_sha256"] = sha(manifest_path)
        report["fixture_sha256"], report["config_sha256"] = {}, {}
        tasks = ("derain", "dehaze") if a.task == "both" else (a.task,)
        for task in tasks:
            folder = out / task
            folder.mkdir()
            for name in SOURCES:
                dest = folder / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, dest)
            for size, run in ((96, "trace_20261020"), (8, "rtl_depth_fix_20261020")):
                for endpoint in ("input", "output"):
                    name = ("official_" if size == 96 else "cosim_") + endpoint + ".bin"
                    fixture = delivery / "evidence/hls" / run / task / "fixtures" / name
                    entry = manifest[fixture.relative_to(manifest_path.parent).as_posix()]
                    if fixture.stat().st_size != 6 * size * size or entry["bytes"] != 6 * size * size or sha(fixture) != entry["sha256"]:
                        raise ValueError("A fixture size/hash mismatch: " + str(fixture))
                    shutil.copy2(fixture, folder / name)
                    report["fixture_sha256"][task + "/" + name] = sha(fixture)
            cpp, tb = folder / "src/weather_frame.cpp", folder / "hls/tb_weather_frame.cpp"
            task_id = str(("derain", "dehaze").index(task))
            def tb_args(prefix, size, stage):
                return " ".join([task_id, str(size), str(size),
                    (folder / (prefix + "input.bin")).as_posix(),
                    (folder / (prefix + "output.bin")).as_posix(),
                    (folder / (stage + "_actual.bin")).as_posix()])
            config = "\n".join(["part=" + a.part, "", "[hls]", "flow_target=vivado", "clock=" + str(a.clock_ns),
                "syn.file=" + cpp.as_posix(), "syn.file_cflags=" + cpp.as_posix() + ",-std=c++11",
                "tb.file=" + tb.as_posix(), "tb.file_cflags=" + tb.as_posix() + ",-std=c++11 -I" + (folder / "src").as_posix(),
                "syn.top=weather_frame_top", "csim.argv=" + tb_args("official_", 96, "csim"),
                "cosim.argv=" + tb_args("cosim_", 8, "cosim"), "cosim.rtl=verilog",
                "cosim.tool=xsim", "cosim.trace_level=none", "package.output.format=ip_catalog", ""])
            (folder / "hls_config.cfg").write_text(config, encoding="utf-8", newline="\n")
            report["config_sha256"][task] = sha(folder / "hls_config.cfg")
        report["completed_through"] = "prepare"
        if a.through != "prepare":
            if a.vitis_bin is None:
                raise ValueError("--vitis-bin required for execution")
            ext = ".bat" if os.name == "nt" else ""
            vr, vc = a.vitis_bin.resolve() / ("vitis-run" + ext), a.vitis_bin.resolve() / ("v++" + ext)
            settings = a.settings.resolve() if a.settings else None
            log, step = invoke("preflight", [vr, "--version"], out, settings, min(60, a.stage_timeout))
            step["validation"] = assess("preflight", log, out)
            step["pass"] = step["exit_code"] == 0 and step["validation"]["pass"]
            report["steps"]["preflight"] = step
            if not step["pass"]:
                raise RuntimeError("Vitis preflight failed: " + "; ".join(step["validation"]["reasons"]))
            report["completed_through"] = "preflight"
            for stage in STAGES[2:STAGES.index(a.through) + 1]:
                for task in tasks:
                    folder = out / task
                    args = ["-c", "--mode", "hls"] if stage == "synth" else ["--mode", "hls", "--" + stage]
                    args += ["--config", folder / "hls_config.cfg", "--work_dir", folder / "component"]
                    log, step = invoke(stage, [vc if stage == "synth" else vr] + args, folder, settings, a.stage_timeout)
                    actual = folder / (stage + "_actual.bin")
                    expected = folder / ("official_output.bin" if stage == "csim" else "cosim_output.bin")
                    step["validation"] = assess(stage, log, folder / "component", actual, expected)
                    step["pass"] = step["exit_code"] == 0 and step["validation"]["pass"]
                    report["steps"][task + "/" + stage] = step
                    if not step["pass"]:
                        raise RuntimeError(task + "/" + stage + " failed artifact verification")
                report["completed_through"] = stage
        report["pass"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        print(str(exc), file=sys.stderr)
    finally:
        report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (out / "run.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
