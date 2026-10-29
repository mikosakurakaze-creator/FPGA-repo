"""Check actual frozen packages without changing any branch or source file.

Use --ip-root <original joint build>/ip. The default only audits the discovered
local candidates and intentionally reports their different package identities.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASELINE="23b56b5458f54eb8c1d67f4f71a742f6a348268d"
D_REF="d8880cce7241628f5472a36802b1791e85935e27"
D_FILE="compact_d_fpga/board/k26_compact_d_20261025/compact_d_ip.zip"
D_SHA="7d276942544f3785bde9267484da6d08bbae819cd46b8bb8e7214ea8a5603bc4"
REPO=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--ip-root",type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    raw=subprocess.check_output(["git","show",BASELINE+":fpga/joint_lowlight_compact_d/reports/resource_frozen_inputs.json"],cwd=REPO)
    lock=json.loads(raw)
    packages=({name:a.ip_root/name for name in ("cnn","bilinear","curve")} if a.ip_root else {
        "cnn":Path("D:/weather_builds/lowlight01/cnn_writecredit"),
        "bilinear":Path("D:/weather_builds/lowlight01/bilinear/component/hls/impl/ip"),
        "curve":Path("D:/weather_builds/lowlight01/curve/component/hls/impl/ip"),
    })
    report={"date":"2026-10-29","baseline":BASELINE,"frozen_manifest_sha256":hashlib.sha256(raw).hexdigest(),
            "packages":{},"exact_frozen_packages":True,"board_operations":0}
    for name,root in packages.items():
        expected={k.replace("\\","/").removeprefix("ip/"+name+"/"):v
                  for k,v in lock["frozen_input_files"].items()
                  if k.replace("\\","/").startswith("ip/"+name+"/")}
        if not expected:raise ValueError("Empty package lock: "+name)
        same=[];missing=[];changed=[]
        for relative,want in expected.items():
            f=root/relative
            if not f.is_file():missing.append(relative)
            elif hashlib.sha256(f.read_bytes()).hexdigest()!=want:changed.append(relative)
            else:same.append(relative)
        payload=[n for n in expected if n.startswith(("hdl/","drivers/","constraints/","xgui/"))]
        payload_same=all(n in same for n in payload)
        exact=not missing and not changed
        report["packages"][name]={"root":str(root),"frozen_file_count":len(expected),"matching_files":len(same),
            "hdl_driver_constraints_xgui_match":payload_same,"matching_payload_files":len(payload) if payload_same else None,
            "changed":changed,"missing":missing,"exact_identity":exact,
            "expected_component_sha256":expected["component.xml"]}
        report["exact_frozen_packages"] &= exact
    blob=subprocess.check_output(["git","show",D_REF+":"+D_FILE],cwd=REPO)
    report["compact_d"]={"ref":D_REF,"path":D_FILE,"bytes":len(blob),"sha256":hashlib.sha256(blob).hexdigest()}
    if report["compact_d"]["sha256"]!=D_SHA:raise ValueError("Compact D package hash mismatch")
    report["can_build_frozen_system"]=report["exact_frozen_packages"]
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["can_build_frozen_system"] else 2)


if __name__=="__main__":main()
