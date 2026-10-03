"""Locked post-export build of the Phase 4E write-credit Vivado IP.

No HLS synthesis and no edits to frozen inputs. Only the three verified Verilog
modules are transformed, using the unchanged Phase 4E generator functions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = Path("E:/HLS/kv260_three_module_v1_2_phase4/cnn_r4_export/hls/impl/ip")
FROZEN = ROOT / "fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4"
OVERLAY = FROZEN.with_name("candidate_b_rowstream_r4_writecredit")
GENERATOR = ROOT / "fpga/perf/v1_2_phase4e/build_writecredit_candidate.py"
VIVADO = Path("E:/Xilinx/2025.2/Vivado/bin/vivado.bat")
S = "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"
X = "http://www.xilinx.com"
NS = {"s": S, "x": X}
ET.register_namespace("spirit", S)
ET.register_namespace("xilinx", X)
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
SYN = "xilinx_verilogsynthesis_view_fileset"
SIM = "xilinx_verilogbehavioralsimulation_view_fileset"
VLNV = "xilinx.com:hls:zero_dce_cnn_top:1.0"
PAYLOAD_DIRS = ("constraints", "doc", "drivers", "hdl", "misc", "xgui")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def payload(base: Path) -> dict[str, str]:
    paths = [base / "component.xml"]
    for dirname in PAYLOAD_DIRS:
        paths.extend(p for p in (base / dirname).rglob("*") if p.is_file())
    for name in ("sysgen_info.xml", "dfx_runtime.txt"):
        if (base / name).exists():
            paths.append(base / name)
    return {p.relative_to(base).as_posix(): sha(p) for p in sorted(paths)}


def inputs() -> dict:
    candidate = json.loads((OVERLAY / "candidate_manifest.json").read_text(encoding="utf-8"))
    records = candidate["overlays"]
    for r in records:
        assert sha(BASE / "hdl/verilog" / r["name"]) == r["frozen_sha256"], r["name"]
        assert sha(Path(r["frozen"])) == r["frozen_sha256"], r["name"]
        assert sha(OVERLAY / "rtl" / r["name"]) == r["candidate_sha256"], r["name"]
    cpp = {p.name: sha(p) for p in sorted(FROZEN.iterdir()) if p.is_file()}
    for path, expected in candidate["frozen_cpp"].items():
        assert sha(Path(path)) == expected, path
    files = payload(BASE)
    return {
        "schema": 1,
        "base_export_path": BASE.as_posix(),
        "base_payload": files,
        "base_r4_sha256": identity(files),
        "frozen_cpp": cpp,
        "generator_path": GENERATOR.relative_to(ROOT).as_posix(),
        "generator_sha256": sha(GENERATOR),
        "overlay_manifest_sha256": sha(OVERLAY / "candidate_manifest.json"),
        "overlays": records,
        "tool": "Vivado 2025.2",
        "core_revision": 2114810448,
        "vlnv": VLNV,
    }


def canonical(element) -> str:
    return ET.canonicalize(ET.tostring(element, encoding="unicode"), strip_text=True)


def abi(base: Path) -> dict:
    xml = ET.parse(base / "component.xml").getroot()
    tags = ("vendor", "library", "name", "version", "busInterfaces", "addressSpaces", "memoryMaps", "parameters")
    fields = {tag: canonical(xml.find("s:" + tag, NS)) for tag in tags if xml.find("s:" + tag, NS) is not None}
    for tag in ("ports", "modelParameters"):
        e = xml.find("s:model/s:" + tag, NS)
        if e is not None:
            fields["model/" + tag] = canonical(e)
    fields["drivers"] = {p.relative_to(base).as_posix(): sha(p) for p in sorted((base / "drivers").rglob("*")) if p.is_file()}
    fields["xgui"] = {p.relative_to(base).as_posix(): sha(p) for p in sorted((base / "xgui").rglob("*")) if p.is_file()}
    return fields


def revise_metadata(ip: Path, revision: int):
    path = ip / "component.xml"
    tree = ET.parse(path)
    xml = tree.getroot()
    views = xml.find("s:model/s:views", NS)
    groups = xml.find("s:fileSets", NS)
    for parent in (views, groups):
        for entry in list(parent):
            name = entry.findtext("s:name", namespaces=NS)
            if "vhdl" in name.lower():
                parent.remove(entry)
    xml.find("s:vendorExtensions/x:coreExtensions/x:coreRevision", NS).text = str(revision)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def normalize_package_abi(ip: Path):
    """Undo only Vivado save_core's optional format annotation.

    HLS export omits range/format; Vivado writes its default "long". Values and
    interpreted widths do not change. Restore the exact frozen subtree and its
    corresponding frozen checksum, then reopen/check without saving again.
    """
    base = ET.parse(BASE / "component.xml").getroot()
    tree = ET.parse(ip / "component.xml")
    xml = tree.getroot()
    original = base.find("s:addressSpaces", NS)
    packaged = xml.find("s:addressSpaces", NS)
    for rng in packaged.findall("s:addressSpace/s:range", NS):
        assert rng.attrib in ({}, {"{" + S + "}format": "long"}), rng.attrib
        rng.attrib.clear()
    assert canonical(packaged) == canonical(original), "Unexpected address space change"
    scopes = base.find("s:vendorExtensions/x:packagingInfo", NS)
    checksum = next(e for e in scopes if e.attrib.get("{" + X + "}scope") == "addressSpaces")
    final_scopes = xml.find("s:vendorExtensions/x:packagingInfo", NS)
    final = next(e for e in final_scopes if e.attrib.get("{" + X + "}scope") == "addressSpaces")
    final.attrib = dict(checksum.attrib)
    creation_path = "s:vendorExtensions/x:coreExtensions/x:coreCreationDateTime"
    xml.find(creation_path, NS).text = base.find(creation_path, NS).text
    tree.write(ip / "component.xml", encoding="utf-8", xml_declaration=True)


def run_vivado(script: Path, work: Path, stem: str):
    work.mkdir(parents=True, exist_ok=True)
    stdout = work / (stem + "_console.log")
    runner = work / (stem + ".cmd")
    runner.write_text('@echo off\nif not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"\n'
                      'call "E:\\Xilinx\\2025.2\\data\\settings64.bat"\n'
                      f'call "{VIVADO}" -mode batch -notrace -source "{script}" '
                      f'-log "{work / (stem + ".log")}" -journal "{work / (stem + ".jou")}"\n'
                      'exit /b %errorlevel%\n', encoding="utf-8")
    command = ["cmd.exe", "/d", "/c", str(runner)]
    with stdout.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=work, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Vivado {stem} failed ({result.returncode}); see {stdout}")
    return stdout


def audit(ip: Path, lock: dict) -> tuple[dict, dict]:
    final = payload(ip)
    patched = {"hdl/verilog/" + r["name"]: r["candidate_sha256"] for r in lock["overlays"]}
    changed = sorted(p for p in lock["base_payload"] if final.get(p) != lock["base_payload"][p])
    assert changed == sorted(["component.xml", *patched]), changed
    for name, expected in patched.items():
        assert final[name] == expected, name
    base_abi, final_abi = abi(BASE), abi(ip)
    assert base_abi == final_abi, "External ABI changed"
    xml = ET.parse(ip / "component.xml").getroot()
    filesets = {}
    for fs in xml.findall("s:fileSets/s:fileSet", NS):
        name = fs.findtext("s:name", namespaces=NS)
        entries = []
        for f in fs.findall("s:file", NS):
            rel = f.findtext("s:name", namespaces=NS)
            assert not Path(rel).is_absolute() and ".." not in Path(rel).parts, rel
            path = ip / rel
            assert path.is_file(), rel
            entries.append({"path": rel, "sha256": sha(path), "file_type": f.findtext("s:fileType", namespaces=NS)})
        filesets[name] = entries
    synth = {r["path"]: r["sha256"] for r in filesets[SYN] if r["path"].startswith("hdl/")}
    sim = {r["path"]: r["sha256"] for r in filesets[SIM] if r["path"].startswith("hdl/")}
    assert synth == sim, "Synthesis/simulation sources differ"
    assert not any("vhdl" in name.lower() for name in filesets), "Active old VHDL filegroup"
    active_views = []
    for view in xml.findall("s:model/s:views/s:view", NS):
        name = view.findtext("s:name", namespaces=NS)
        env = view.findtext("s:envIdentifier", namespaces=NS)
        group = view.findtext("s:fileSetRef/s:localName", namespaces=NS)
        active_views.append({"name": name, "environment": env, "fileset": group})
        assert "vhdl" not in name.lower() and "vhdl" not in (env or "").lower()
        if env and (env.endswith(":synthesis") or env.endswith(":simulation")):
            assert group in (SYN, SIM)
    for path, expected in patched.items():
        assert synth[path] == expected and sim[path] == expected
        assert sum(r["path"] == path for r in filesets[SYN]) == 1
        assert sum(r["path"] == path for r in filesets[SIM]) == 1
    for path in (ip / "hdl/verilog").glob("*.v"):
        assert path.relative_to(ip).as_posix() in synth, "Unreferenced Verilog shadow copy"
    driver = next((ip / "drivers").rglob("xzero_dce_cnn_top_hw.h"))
    buses = [e.findtext("s:name", namespaces=NS) for e in xml.findall("s:busInterfaces/s:busInterface", NS)]
    offsets = re.findall(r"#define\s+(XZERO_DCE_CNN_TOP_CONTROL_ADDR_\w+)\s+(0x[0-9a-fA-F]+)", driver.read_text())
    pointers = [name.removeprefix("XZERO_DCE_CNN_TOP_CONTROL_ADDR_").removesuffix("_DATA").lower()
                for name, _ in offsets if name.endswith("_DATA")]
    assert pointers == ["input_q14", "weights_int8", "bias_int32", "weight_frac", "tanh_lut_q15", "a_low_q14", "workspace_int16"]
    manifest = {"schema": 1, "top": "zero_dce_cnn_top", "vlnv": VLNV, "filesets": filesets,
                "active_views": active_views, "patched_rtl": patched}
    result = {
        "status": "PASS", "abi_sha256": identity(final_abi), "abi_equal": True,
        "driver_header": driver.relative_to(ip).as_posix(), "driver_header_sha256": sha(driver),
        "register_offsets": dict(offsets), "bus_interfaces": buses, "pointer_names": pointers,
        "rtl_changed": sorted(patched), "unchanged_payload_files": len(final) - 4,
        "synthesis_simulation_equal": True, "shared_hdl_files": len(synth),
        "active_vhdl_views": 0, "archival_vhdl_files": len(list((ip / "hdl/vhdl").glob("*"))),
        "shadow_copy_audit": "PASS: no old writer in any active model view/fileset/Verilog search path",
        "base_payload_sha256": lock["base_r4_sha256"], "patched_rtl": patched,
        "component_xml_sha256": sha(ip / "component.xml"), "source_manifest_sha256": identity(manifest),
    }
    return result, manifest


def build(output: Path):
    lock = json.loads((HERE / "input_lock.json").read_text(encoding="utf-8"))
    assert inputs() == lock, "Frozen input hash gate failed"
    assert not output.exists(), f"Refuse to overwrite: {output}"
    work = output.with_name(output.name + "_build")
    assert not work.exists(), f"Refuse to overwrite work: {work}"
    output.mkdir(parents=True)
    for rel in lock["base_payload"]:
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / rel, target)
    spec = importlib.util.spec_from_file_location("phase4e_writecredit", GENERATOR)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    transforms = (lambda t: gen.helper(t, "workspace"), lambda t: gen.helper(t, "output"), gen.caller)
    for record, transform in zip(lock["overlays"], transforms):
        target = output / "hdl/verilog" / record["name"]
        # Match Phase 4E's Windows write_text newline behavior exactly.
        target.write_text(transform(target.read_text()), encoding="utf-8")
        assert sha(target) == record["candidate_sha256"], "Generator output differs from verified overlay"
    revise_metadata(output, lock["core_revision"])
    work.mkdir(parents=True)
    script = work / "package.tcl"
    script.write_text(f'''set component {{{(output / 'component.xml').as_posix()}}}
ipx::open_core $component
set core [ipx::current_core]
if {{[get_property VLNV $core] ne {{{VLNV}}}}} {{error {{VLNV changed}}}}
ipx::update_checksums $core
ipx::check_integrity -quiet $core
ipx::save_core $core
puts {{PHASE4G_PACKAGE_PASS}}
exit
''', encoding="utf-8")
    run_vivado(script, work, "package")
    package_log = (work / "package_console.log").read_text(encoding="utf-8", errors="replace")
    assert "PHASE4G_PACKAGE_PASS" in package_log, "Vivado did not finish the package script"
    normalize_package_abi(output)
    verify = work / "verify_package.tcl"
    verify.write_text(f'''ipx::open_core {{{(output / 'component.xml').as_posix()}}}
ipx::check_integrity -quiet [ipx::current_core]
puts {{PHASE4G_NORMALIZED_PACKAGE_INTEGRITY_PASS}}
exit
''', encoding="utf-8")
    run_vivado(verify, work, "verify_package")
    verify_log = (work / "verify_package_console.log").read_text(encoding="utf-8", errors="replace")
    assert "PHASE4G_NORMALIZED_PACKAGE_INTEGRITY_PASS" in verify_log, "Vivado did not finish normalized integrity check"
    result, sources = audit(output, lock)
    version_match = re.search(r"Vivado v2025\.2[^\r\n]*", package_log)
    assert version_match, "Unexpected tool version"
    save(output / "abi_fileset_audit.json", result)
    save(output / "source_manifest.json", sources)
    stable = {"base_r4_sha256": lock["base_r4_sha256"], "generator_sha256": lock["generator_sha256"],
              "overlay_manifest_sha256": lock["overlay_manifest_sha256"], "patched_rtl": result["patched_rtl"],
              "abi_sha256": result["abi_sha256"], "component_xml_sha256": result["component_xml_sha256"],
              "source_manifest_sha256": result["source_manifest_sha256"],
              "source_manifest_file_sha256": sha(output / "source_manifest.json"),
              "driver_header_sha256": result["driver_header_sha256"], "tool_version": version_match.group(0),
              "build_recipe_sha256": sha(Path(__file__)),
              "input_lock_file_sha256": sha(HERE / "input_lock.json"),
              "final_payload_sha256": identity(payload(output)), "core_revision": lock["core_revision"]}
    build_manifest = {"schema": 1, "status": "PACKAGED_IP_GATE_PASS", "identity": stable,
                      "identity_sha256": identity(stable), "generated_ip_path": output.as_posix(),
                      "timestamp": datetime.now(timezone.utc).isoformat(),
                      "execution": {"package_work_path": work.as_posix(), "input_lock_path": (HERE / "input_lock.json").as_posix(),
                                    "vivado_path": VIVADO.as_posix()},
                      "determinism": "identity excludes timestamp and absolute output/work paths; component and source manifests are byte-stable"}
    save(output / "build_manifest.json", build_manifest)
    assert inputs() == lock, "Frozen inputs modified during build"
    print(json.dumps({"status": build_manifest["status"], "ip": output.as_posix(), "identity": build_manifest["identity_sha256"]}))


def compare(a: Path, b: Path, report: Path):
    first = json.loads((a / "build_manifest.json").read_text())
    second = json.loads((b / "build_manifest.json").read_text())
    assert first["identity"] == second["identity"], "Build identities differ"
    assert payload(a) == payload(b), "Package payload differs"
    for name in ("source_manifest.json", "abi_fileset_audit.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
    save(report, {"status": "PASS", "identity_sha256": first["identity_sha256"],
                  "primary": a.as_posix(), "rebuild": b.as_posix(), "compared_payload_files": len(payload(a)),
                  "component_xml_byte_equal": True, "source_manifest_byte_equal": True,
                  "driver_byte_equal": True, "all_rtl_byte_equal": True,
                  "excluded_execution_fields": ["timestamp", "generated_ip_path", "execution"]})
    print(json.dumps({"deterministic_rebuild": "PASS", "identity": first["identity_sha256"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lock")
    p = commands.add_parser("build"); p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("compare"); p.add_argument("--primary", type=Path, required=True); p.add_argument("--rebuild", type=Path, required=True); p.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "lock":
        path = HERE / "input_lock.json"
        assert not path.exists(), "Refuse to replace established input lock"
        save(path, inputs())
        print(json.dumps({"input_lock": path.as_posix(), "status": "PASS"}))
    elif args.command == "build":
        build(args.output.resolve())
    else:
        compare(args.primary, args.rebuild, args.report)


if __name__ == "__main__":
    main()
