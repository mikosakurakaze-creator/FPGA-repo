"""Collect genuine independent-core results; never label them a board package."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ("rtl","full","package","ooc","verify","dependency","out"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    result={"date":"2026-10-29","board_operations":0,"standalone_checks":{},
            "scope":"Independent fusion core only; joint-system status is recorded separately"}
    staged={}
    for stage in ("rtl","full","package","ooc","verify"):
        source=getattr(a,stage)/"result.json"
        r=json.loads(source.read_text())
        if r.get("stage")!=stage:raise ValueError("Wrong stage: "+str(source))
        if r.get("pass") is not True and stage!="ooc":raise ValueError("Unpassed result: "+str(source))
        if r["source_sha256"]["rtl/joint_fusion.v"]!=sha(ROOT/"rtl/joint_fusion.v"):
            raise ValueError("DUT changed since "+stage)
        if stage in ("rtl","full") and r["source_sha256"]["tests/tb_joint_fusion.sv"]!=sha(ROOT/"tests/tb_joint_fusion.sv"):
            raise ValueError("Testbench changed since "+stage)
        for step in r["steps"]:
            log=getattr(a,stage)/(step["name"]+".log")
            if sha(log)!=step["log_sha256"]:
                raise ValueError("Tool execution evidence changed")
            if step["return_code"]!=0:
                text=log.read_text(errors="replace")
                if (stage!="ooc" or "FUSION_OOC_SYNTHESIS_PASS" not in text.splitlines()
                        or "Abnormal program termination (EXCEPTION_ACCESS_VIOLATION)" not in text):
                    raise ValueError("Unexpected failed vendor execution")
        result["standalone_checks"][stage]={"result_path":str(source),"result_sha256":sha(source),"pass":r["pass"]}
        staged[stage+"_result.json"]=source.read_bytes()
    dep=json.loads(a.dependency.read_text())
    result["frozen_dependencies_available"]=dep["can_build_frozen_system"]
    staged["dependency_audit.json"]=a.dependency.read_bytes()
    verification=json.loads((a.verify/"result.json").read_text())
    if sha(a.ooc/"ooc/fusion_ooc.dcp")!=verification["checkpoint_sha256"]:
        raise ValueError("Independent verification refers to another checkpoint")
    result["ooc_artifact_verification"]={"checkpoint_sha256":verification["checkpoint_sha256"],
        "independent_reopen_pass":True,"synthesis_process_pass":result["standalone_checks"]["ooc"]["pass"],
        "note":"Synthesis wrote a checkpoint and reports, then failed during process shutdown; the failure is retained. A separate successful Vivado process reopened this exact checkpoint and regenerated the reports."}
    package=a.package/"package"
    zpath=package/"joint_fusion_ip.zip"
    pkg=json.loads((a.package/"result.json").read_text())
    if sha(zpath)!=pkg["ip_zip_sha256"]:raise ValueError("IP ZIP changed")
    component=package/"ip/component.xml"
    if sha(component)!=pkg["component_sha256"]:raise ValueError("Component changed")
    ns={"s":"http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
    tree=ET.parse(component).getroot()
    registers={r.find("s:name",ns).text:(int(r.find("s:addressOffset",ns).text,0),int(r.find("s:size",ns).text))
               for r in tree.findall(".//s:register",ns)}
    expected={"AP_CTRL":0,"GIE":4,"IER":8,"ISR":12,"AP_RETURN":16,
              "I_LOW":24,"I_HIGH":28,"L_LOW":36,"L_HIGH":40,"D_LOW":48,"D_HIGH":52,
              "O_LOW":60,"O_HIGH":64,"W_I":72,"W_L":80,"W_D":88,"COOKIE":96,
              "FRAME_ID":104,"COMPLETED_FRAME":112,"ACTIVE_FRAME":116}
    if registers!={name:(offset,32) for name,offset in expected.items()}:raise ValueError("Exported register ABI mismatch")
    params={p.find("s:name",ns).text:p.find("s:value",ns).text for p in tree.findall("./s:parameters/s:parameter",ns)}
    if params.get("SCALAR_COUNT")!="2747520":raise ValueError("Production size changed")
    buses={b.find("s:name",ns).text:b for b in tree.findall("./s:busInterfaces/s:busInterface",ns)}
    for name,required in {"s_axi_control":{"PROTOCOL":"AXI4LITE","DATA_WIDTH":"32","ADDR_WIDTH":"7"},
                          "m_axi_gmem":{"PROTOCOL":"AXI4","DATA_WIDTH":"32","ADDR_WIDTH":"64"}}.items():
        bp={p.find("s:name",ns).text:p.find("s:value",ns).text for p in buses[name].findall("s:parameters/s:parameter",ns)}
        if any(bp.get(k)!=v for k,v in required.items()):raise ValueError("Bus ABI mismatch")
    files={f.find("s:name",ns).text for f in tree.findall(".//s:file",ns) if f.find("s:fileType",ns) is not None and f.find("s:fileType",ns).text=="verilogSource"}
    if len(files)!=1:raise ValueError("Unexpected active RTL source set")
    rtl_member=next(iter(files))
    if sha(component.parent/rtl_member)!=sha(ROOT/"rtl/joint_fusion.v"):raise ValueError("Packaged RTL changed")
    with zipfile.ZipFile(zpath) as z:
        if z.testzip() is not None or z.read(rtl_member)!=(ROOT/"rtl/joint_fusion.v").read_bytes():
            raise ValueError("IP archive differs from verified RTL")
    result["ip_package"]={"path":str(zpath),"sha256":sha(zpath),"register_abi":expected,
                           "all_registers_bits":32,"packaged_rtl_matches_simulated_rtl":True}
    util=(a.verify/"verify/utilization.rpt").read_text()
    result["ooc_resources"]={k.replace("*",""):v for k,v in re.findall(
        r"\|\s*(CLB LUTs\*?|CLB Registers|DSPs|Block RAM Tile|URAM)\s*\|\s*([0-9,.]+)",util)}
    timing=(a.verify/"verify/timing.rpt").read_text()
    rows=timing.splitlines()
    for i,line in enumerate(rows):
        if "WNS(ns)" in line and "WHS(ns)" in line:
            for row in rows[i+1:i+6]:
                fields=row.split()
                if fields and re.fullmatch(r"-?\d+\.\d+",fields[0]):
                    result["ooc_timing_estimate"]={"WNS_ns":float(fields[0]),"WHS_ns":float(fields[4]),"system_route_signoff":False}
                    break
            break
    if "ooc_timing_estimate" not in result:raise ValueError("Missing actual timing summary")
    tested=subprocess.run([sys.executable,"-m","unittest","discover","-s",str(ROOT/"tests"),"-p","test_*.py","-v"],capture_output=True,text=True)
    if tested.returncode!=0:raise ValueError(tested.stderr)
    result["scheduler_tests"]={"pass":True,"output":tested.stdout+tested.stderr,
                              "controller_sha256":sha(ROOT/"runtime/controller.py"),
                              "tests_sha256":sha(ROOT/"tests/test_controller.py"),"real_mmio_or_board_test":False}
    a.out.mkdir(parents=True,exist_ok=True)
    for name,data in staged.items():(a.out/name).write_bytes(data)
    (a.out/"review.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
