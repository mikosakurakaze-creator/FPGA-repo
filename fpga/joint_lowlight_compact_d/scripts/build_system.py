"""Build the locked six-core KV260 design in a new external ASCII directory.

No Git mutations and no board operations. Every tool invocation has its own
immutable log/result; implementation and export require successful prior gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

from run_checks import vendor_runtime

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BASE = "3c9e41a35fc08d44ba0552ce6916a421f98f94d7"
D_REF = "d8880cce7241628f5472a36802b1791e85935e27"
D_FILE = "compact_d_fpga/board/k26_compact_d_20261025/compact_d_ip.zip"
D_SHA = "7d276942544f3785bde9267484da6d08bbae819cd46b8bb8e7214ea8a5603bc4"
FUSION_SHA = "7ece7f03c2d9aca56e5a9284dea1f507832e52ac51daa603d5c6ce3eac65dedc"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n", encoding="utf-8", newline="\n")


def locked(ref, relative):
    return subprocess.check_output(["git", "show", ref+":"+relative], cwd=REPO)


def unpack(archive, destination):
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP CRC failure")
        for name in z.namelist():
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or ":" in name or "\\" in name:
                raise ValueError("Unsafe archive path: "+name)
        z.extractall(destination)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--stage", required=True, choices=["prepare", "adapter", "create", "synth", "implement", "coverage", "export"])
    p.add_argument("--attempt", type=int, default=1)
    p.add_argument("--reuse-adapter", type=Path, help="Reuse an independently recorded successful export, checking all identities")
    p.add_argument("--fusion", type=Path, default=Path("D:/weather_builds/joint_fusion_package08_20261029/package/joint_fusion_ip.zip"))
    p.add_argument("--vivado", type=Path, default=Path("D:/vivado/2025.2/Vivado"))
    p.add_argument("--vitis", type=Path, default=Path("D:/vivado/2025.2/Vitis"))
    a = p.parse_args()
    out = a.out.resolve()
    if not re.fullmatch(r"[A-Za-z0-9_:/\\.\-]+", str(out)):
        raise ValueError("External build directory must be ASCII without spaces")
    if a.stage == "prepare":
        out.mkdir(parents=True, exist_ok=False)
        (out/"reports").mkdir()
        (out/"source").mkdir()
    tag = a.stage+("_attempt"+str(a.attempt) if a.attempt != 1 else "")
    result_path = out/(tag+"_result.json")
    if result_path.exists():
        raise ValueError("Stage already attempted; preserve evidence and use a new build")
    result = {"stage": a.stage, "pass": False, "board_operations": 0, "baseline": BASE, "steps": []}
    result["runner_sha256"] = sha(Path(__file__))

    def execute(label, command, env=None, desktop=False):
        log = out/(label+".log")
        print("JOINT_STAGE="+label+" LOG="+str(log), flush=True)
        start = time.perf_counter()
        command = [x.as_posix() if isinstance(x, Path) else str(x) for x in command]
        if desktop:
            command = [sys.executable, "-E", str(out/"run_windows_desktop.py"), "--", *command]
        with log.open("xb") as f:
            proc = subprocess.run(command, cwd=out, env=env, stdout=f, stderr=subprocess.STDOUT)
        result["steps"].append({"command": command, "exit_code": proc.returncode,
                                "seconds": time.perf_counter()-start, "log_sha256": sha(log)})
        content = log.read_text(errors="replace")
        if proc.returncode or re.search(r"(?mi)^\s*(ERROR|FATAL):|fatal error:", content):
            raise RuntimeError(label+" failed: "+content[-2500:])
        return content

    try:
        if a.stage == "prepare":
            relative = "fpga/joint_lowlight_compact_d/"
            bundle = out/"lowlight_frozen_ip.zip"
            bundle.write_bytes(locked(BASE, relative+"delivery/lowlight_frozen_ip_20261028.zip"))
            meta = json.loads(locked(BASE, relative+"delivery/lowlight_frozen_ip_20261028.json"))
            if sha(bundle) != meta["archive_sha256"]:
                raise ValueError("Lowlight archive identity mismatch")
            unpack(bundle, out)
            old_lock = json.loads(locked(BASE, relative+"reports/resource_frozen_inputs.json"))
            expected = {k.replace("\\", "/"): v for k, v in old_lock["frozen_input_files"].items()
                        if k.replace("\\", "/").split("/")[1] in ("cnn", "bilinear", "curve")}
            if set(expected) != set(meta["files"]):
                raise ValueError("Frozen file set mismatch")
            for name, digest in expected.items():
                if sha(out/name) != digest or meta["files"][name]["sha256"] != digest:
                    raise ValueError("Frozen file identity mismatch: "+name)
            blob = locked(D_REF, D_FILE)
            if hashlib.sha256(blob).hexdigest() != D_SHA:
                raise ValueError("D IP identity mismatch")
            (out/"compact_d_ip.zip").write_bytes(blob)
            unpack(out/"compact_d_ip.zip", out/"ip/compact_d")
            if sha(a.fusion) != FUSION_SHA:
                raise ValueError("Fusion package identity mismatch")
            shutil.copy2(a.fusion, out/"joint_fusion_ip.zip")
            unpack(out/"joint_fusion_ip.zip", out/"ip/fusion")
            for name in ("joint_adapters.cpp", "joint_adapters.hpp"):
                (out/"source"/name).write_bytes(locked(BASE, relative+"hls/"+name))
            (out/"four_core_seed.tcl").write_bytes(locked(BASE, relative+"reports/resource_joint_system_recreate.tcl"))
            (out/"run_windows_desktop.py").write_bytes(locked(D_REF, "tools/run_windows_desktop.py"))
            shutil.copy2(ROOT/"scripts/system_build.tcl", out/"system_build.tcl")
            if a.reuse_adapter:
                receipt_path = a.reuse_adapter/"adapter_result.json"
                receipt = json.loads(receipt_path.read_text())
                old_ip = a.reuse_adapter/"prepare/hls/impl/ip"
                if not receipt["pass"] or receipt["baseline"] != BASE or sha(old_ip/"component.xml") != receipt["component_sha256"]:
                    raise ValueError("Reused adapter receipt/component mismatch")
                for name, digest in receipt["ip_zips"].items():
                    if sha(old_ip/name) != digest:
                        raise ValueError("Reused adapter ZIP mismatch")
                for name in ("joint_adapters.cpp", "joint_adapters.hpp"):
                    if sha(a.reuse_adapter/"source"/name) != sha(out/"source"/name):
                        raise ValueError("Reused adapter source mismatch")
                shutil.copytree(old_ip, out/"prepare/hls/impl/ip")
                reused = {"stage": "adapter", "pass": True, "board_operations": 0, "baseline": BASE,
                          "verification": "Reuse of successfully rebuilt locked-source IP; no new synthesis claim",
                          "source_result": receipt_path.as_posix(), "source_result_sha256": sha(receipt_path),
                          "component_sha256": receipt["component_sha256"], "ip_zips": receipt["ip_zips"]}
                save(out/"adapter_result.json", reused)
                save(out/"gates.json", {"adapter": "adapter_result.json"})
            manifest = {"baseline": BASE, "d_ref": D_REF, "lowlight_files": len(expected),
                        "source_files": {f.relative_to(out).as_posix(): sha(f)
                                         for f in out.rglob("*") if f.is_file() and f.name != "gates.json"}}
            save(out/"inputs.json", manifest)
            result["lowlight_exact_files"] = len(expected)
        else:
            inputs = json.loads((out/"inputs.json").read_text(encoding="utf-8"))
            for name, digest in inputs["source_files"].items():
                if sha(out/name) != digest:
                    raise ValueError("Build input changed: "+name)
            result["inputs_sha256"] = sha(out/"inputs.json")
            if a.stage == "adapter":
                cfg = out/"prepare.cfg"
                cfg.write_text("\n".join(["part=xck26-sfvc784-2LV-c", "[hls]", "flow_target=vivado", "clock=10",
                    "syn.top=joint_rgb8_prepare", "syn.file="+(out/"source/joint_adapters.cpp").as_posix(),
                    "package.output.format=ip_catalog"])+"\n", encoding="ascii")
                cmd = out/"adapter.cmd"
                cmd.write_text('@echo off\nsetlocal\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
                    'set "PATH='+str(a.vivado/'gnuwin/bin')+';%PATH%"\n'
                    'call "'+str(a.vitis/'settings64.bat')+'"\nif errorlevel 1 exit /b %errorlevel%\n'
                    'call "'+str(a.vitis/'bin/v++.bat')+'" -c --mode hls --config "'+str(cfg)+
                    '" --work_dir "'+str(out/'prepare')+'"\nexit /b %errorlevel%\n', encoding="ascii")
                execute(tag, [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", cmd], desktop=True)
                package = out/"prepare/hls/impl/ip"
                if not (package/"component.xml").is_file():
                    raise RuntimeError("Adapter export missing")
                result["component_sha256"] = sha(package/"component.xml")
                result["ip_zips"] = {f.name: sha(f) for f in package.glob("*.zip")}
            else:
                if a.stage == "export":
                    acceptance=json.loads((out/"acceptance.json").read_text())
                    if not acceptance["pass"] or sha(out/"joint_routed.dcp") != acceptance["checkpoint_sha256"]:
                        raise ValueError("Missing/stale routed acceptance")
                    for name,digest in acceptance["bound_files"].items():
                        if sha(Path(name)) != digest:
                            raise ValueError("Accepted evidence changed: "+name)
                    result["acceptance_sha256"]=sha(out/"acceptance.json")
                required = {"create": "adapter", "synth": "create", "implement": "synth", "coverage": "implement", "export": "coverage"}[a.stage]
                gates = json.loads((out/"gates.json").read_text()) if (out/"gates.json").exists() else {}
                prior_path = out/gates.get(required, required+"_result.json")
                if not json.loads(prior_path.read_text())["pass"]:
                    raise ValueError("Prior gate not passed: "+required)
                if a.stage == "create":
                    project = out/("project" if a.attempt == 1 else "project_attempt"+str(a.attempt))/"joint_system.xpr"
                else:
                    create_result = json.loads((out/gates.get("create", "create_result.json")).read_text())
                    project = Path(create_result["project"])
                result["project"] = project.as_posix()
                if a.stage == "coverage":
                    result["checkpoint_sha256"] = sha(out/"joint_routed.dcp")
                stage_script = out/(tag+"_build.tcl")
                shutil.copy2(ROOT/"scripts/system_build.tcl", stage_script)
                result["script_sha256"] = sha(stage_script)
                runtime_parent = out/(tag+"_runtime")
                runtime_parent.mkdir()
                exe, env = vendor_runtime(runtime_parent, a.vivado)
                log = execute(tag+"_console", [exe, "-mode", "batch", "-log", out/(tag+"_vivado.log"),
                    "-journal", out/(tag+"_vivado.jou"), "-source", stage_script,
                    "-tclargs", out, a.stage, project], env, desktop=True)
                if "JOINT_SYSTEM_"+a.stage.upper()+"_PASS" not in log.splitlines():
                    raise RuntimeError("Missing complete stage marker")
                result["reports"] = {f.name: sha(f) for f in (out/"reports").glob("*") if f.is_file()}
        result["pass"] = True
        gates = json.loads((out/"gates.json").read_text()) if (out/"gates.json").exists() else {}
        gates[a.stage] = result_path.name
        save(out/"gates.json", gates)
    except Exception as e:
        result["error"] = str(e)
        raise
    finally:
        save(result_path, result)
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
