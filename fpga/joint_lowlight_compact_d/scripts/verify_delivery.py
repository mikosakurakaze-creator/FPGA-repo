"""Reopen a local delivery ZIP and verify payload identities independently."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("Preserve the earlier verification")
    result = {"pass": False, "zip": args.zip.resolve().as_posix(), "board_operations": 0}
    try:
        zip_sha = digest(args.zip.read_bytes())
        side = args.zip.with_suffix(".zip.sha256").read_text().strip().split("  ", 1)
        assert side == [zip_sha, args.zip.name], "ZIP checksum side file differs"
        with zipfile.ZipFile(args.zip) as archive:
            assert archive.testzip() is None, "ZIP CRC error"
            names = archive.namelist()
            assert len(names) == len(set(n.casefold() for n in names)), "Duplicate ZIP member"
            assert all(not Path(n).is_absolute() and ".." not in Path(n).parts and ":" not in n and "\\" not in n for n in names)
            checksums = {}
            for line in archive.read("SHA256SUMS").decode("ascii").splitlines():
                sha, name = line.split("  ", 1)
                assert name not in checksums
                checksums[name] = sha
            assert set(checksums) == set(names) - {"SHA256SUMS"}, "Incomplete checksum inventory"
            for name, sha in checksums.items():
                assert digest(archive.read(name)) == sha, "Payload checksum differs: " + name
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["status"] == "HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED" and not manifest["fps_claim"]
            assert set(manifest["files"]) == set(names) - {"manifest.json", "SHA256SUMS"}
            for name, spec in manifest["files"].items():
                payload = archive.read(name)
                assert len(payload) == spec["bytes"] and digest(payload) == spec["sha256"], name
            with zipfile.ZipFile(io.BytesIO(archive.read("joint_system.xsa"))) as xsa:
                assert xsa.testzip() is None
                bits = [n for n in xsa.namelist() if n.endswith(".bit")]
                assert len(bits) == 1 and xsa.read(bits[0]) == archive.read("joint_system.bit")
                hwhs = [n for n in xsa.namelist() if n.endswith(".hwh") and xsa.read(n) == archive.read("joint_system.hwh")]
                assert len(hwhs) == 1, "Canonical HWH differs from XSA"
            bit = archive.read("joint_system.bit")
            offset = 2 + int.from_bytes(bit[:2], "big")
            assert bit[offset:offset+2] == b"\x00\x01"
            offset += 2
            for tag in b"abcde":
                assert bit[offset] == tag
                offset += 1
                size = 4 if tag == ord("e") else 2
                length = int.from_bytes(bit[offset:offset+size], "big")
                offset += size
                value = bit[offset:offset+length]
                assert len(value) == length
                offset += length
            assert offset == len(bit) and len(value) > 0 and len(value) % 4 == 0
            expected = bytearray(len(value))
            for byte in range(4):
                expected[byte::4] = value[3-byte::4]
            assert archive.read("joint_system.bit.bin") == expected, "BIN byte order/configuration differs"
            addresses = json.loads(archive.read("address_map.json"))["cores"]
            assert len(addresses) == 6 and addresses["fusion"]["revision"] == 3
            assert len({v["base"] for v in addresses.values()}) == 6
            registers = json.loads(archive.read("register_map.json"))["cores"]
            assert len(registers) == 6 and sum(len(v["registers"]) for v in registers.values()) == 91
            hwh = ET.fromstring(archive.read("joint_system.hwh"))
            fusion = next(m for m in hwh.iter("MODULE") if m.get("INSTANCE") == "joint_fusion_0")
            assert int(fusion.get("COREREVISION")) == 3
            pipeline = json.loads(archive.read("evidence/fusion_pipeline_acceptance.json"))
            assert pipeline["pass"] and not pipeline["whole_system_fps_verified"]
            rtl = archive.read("source/rtl/joint_fusion.v")
            assert digest(rtl) == pipeline["rtl_sha256"]
            with zipfile.ZipFile(io.BytesIO(archive.read("ip/joint_fusion_ip.zip"))) as ip:
                rtl_names = [n for n in ip.namelist() if n.endswith("joint_fusion.v")]
                assert len(rtl_names) == 1 and ip.read(rtl_names[0]) == rtl
            if "evidence/prepare_pipeline_acceptance.json" in names:
                prepare=json.loads(archive.read("evidence/prepare_pipeline_acceptance.json"))
                assert prepare["pass"] and prepare["simulation_only_prepare_budget_pass"]
                assert digest(archive.read("source/hls/joint_adapters.cpp"))==prepare["source_sha256"]
                prepare_cell=next(m for m in hwh.iter("MODULE") if m.get("INSTANCE")=="joint_rgb8_prepare_0")
                params={p.get("NAME"):p.get("VALUE") for p in prepare_cell.iter("PARAMETER")}
                for port in ("RGB","I","D","CNN"):
                    assert params["C_M_AXI_GMEM_"+port+"_DATA_WIDTH"]=="128"
            for name in ("runtime/pipeline_controller.py", "runtime/run_pipeline_pynq.py", "clock_reset.md"):
                assert archive.read(name)
            if "evidence/release_approval.json" in names:
                approval=json.loads(archive.read("evidence/release_approval.json"))
                lineage=json.loads(archive.read("evidence/timing_lineage.json"))
                physical=json.loads(archive.read("evidence/timing_margin_audit.json"))
                acceptance=json.loads(archive.read("evidence/acceptance.json"))
                assert approval["export_allowed"] and physical["pass"] and lineage["pass"] and acceptance["pass"]
                assert (approval["checkpoint_sha256"]==lineage["checkpoint_sha256"]==physical["checkpoint_sha256"]
                        ==acceptance["checkpoint_sha256"]==manifest["checkpoint_sha256"])
                assert approval["audit_sha256"]==lineage["margin_audit_sha256"]==digest(archive.read("evidence/timing_margin_audit.json"))
                assert approval["timing"]==physical["timing"]==acceptance["timing"]==manifest["timing"]
                original=archive.read("evidence/accepted_original_inputs.json")
                assert digest(original)==approval["source_inputs_sha256"]==lineage["source_inputs_sha256"]
                implemented=json.loads(archive.read("evidence/implemented_source_manifest.json"))
                for relative,sha in implemented["files"].items():
                    assert digest(archive.read("source/implemented_inputs/"+relative))==sha
                assert len(implemented["generated_smartconnect"])==132
                for row in implemented["generated_smartconnect"]:
                    assert digest(archive.read("source/generated_smartconnect/"+row["path"]))==row["after"]
                assert "reference_ip/compact_d_ip.zip" in names and "ip/compact_d_ip.zip" not in names
                result["accepted_fifo_release_identity_verified"]=True
            result.update(pass_=True, zip_sha256=zip_sha, files=len(names), build_id=manifest["build_id"],
                          timing=manifest["timing"], resources=manifest["resources"],
                          fusion_rtl_sha256=digest(rtl), fusion_revision=3, registers=91)
            result["pass"] = True
            result.pop("pass_")
    except Exception as exc:
        result["error"] = str(exc)
        raise
    finally:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
