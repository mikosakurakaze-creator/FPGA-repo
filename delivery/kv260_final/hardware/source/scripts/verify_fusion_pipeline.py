"""Bind burst/pipeline numerical, throughput and transport evidence to a build."""
import argparse, hashlib, json, re
from pathlib import Path
import xml.etree.ElementTree as ET

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument("--suite",required=True,type=Path)
    ap.add_argument("--build",required=True,type=Path)
    a=ap.parse_args();out=a.build/"fusion_pipeline_acceptance.json"
    if out.exists():raise ValueError("Preserve previous evidence")
    result={"pass":False,"board_operations":0,"whole_system_fps_verified":False,"bound_files":{},"frames":{}}
    def bind(p):
        result["bound_files"][p.resolve().as_posix()]=sha(p)
        return p.read_text(errors="replace")
    try:
        actual=a.build/"ip/fusion/src/joint_fusion.v";rtl_sha=sha(actual);bind(actual)
        inputs=json.loads(bind(a.build/"inputs.json"))
        if inputs["source_files"]["ip/fusion/src/joint_fusion.v"]!=rtl_sha:raise ValueError("Build RTL changed")
        folders={"regression":"rtl03","tail":"tail01","full":"full01","bandwidth":"bandwidth03",
                 "same_image":"same_image01","package":"package01","checkpoint":"verify02"}
        for key,name in folders.items():
            folder=a.suite/name;record=json.loads(bind(folder/"result.json"))
            if not record["pass"]:raise ValueError("Failed required evidence: "+key)
            source_map=record.get("source_sha256",record.get("sources",{}))
            digest=source_map.get("rtl/joint_fusion.v",source_map.get("joint_fusion.v"))
            if digest!=rtl_sha:raise ValueError("Different RTL in "+key)
            bind(folder/"joint_fusion.v")
            if sha(folder/"joint_fusion.v")!=rtl_sha:raise ValueError("Changed evidence RTL")
            for step in record["steps"]:
                rc=step.get("return_code",step.get("exit_code"))
                if rc!=0:raise ValueError("Nonzero vendor/simulator process: "+key)
                candidates=[p for p in folder.glob("*.log") if sha(p)==step["log_sha256"]]
                if len(candidates)!=1:raise ValueError("Missing/ambiguous execution log: "+key)
                text=bind(candidates[0])
                if key in ("full","bandwidth") and "FUSION_FRAME_METRICS" in text:
                    m=re.search(r"FUSION_FRAME_METRICS[^\n]*scalars=2747520 cycles=(\d+) ",text)
                    if m is None or int(m[1])>3333300:raise ValueError("33.333-ms fusion simulation budget failed")
                    result["frames"][key]={"cycles":int(m[1]),"clock_hz":99999001,"milliseconds":int(m[1])*1000/99999001}
            if key=="bandwidth" and record.get("read_div")!=2:raise ValueError("Constrained-bandwidth test absent")
            if key=="package" and record["ip_zip_sha256"]!=sha(a.build/"joint_fusion_ip.zip"):raise ValueError("Packaged IP differs")
            if key=="checkpoint":
                checkpoint=a.suite/"ooc01/ooc/fusion_ooc.dcp"
                if sha(checkpoint)!=record["checkpoint_sha256"]:raise ValueError("OOC checkpoint changed")
                result["ooc_checkpoint_sha256"]=sha(checkpoint)
            if key=="regression" and not record["success_line"].startswith("FUSION_RTL_PASS frames=10 invalid=9 scalars=655360"):
                raise ValueError("Incomplete regression")
        if set(result["frames"])!={"full","bandwidth"}:raise ValueError("Missing full-frame cycle evidence")
        audit=bind(a.build/"reports/fusion_transport_audit.txt").splitlines()
        expected=["joint_fusion_0/m_axi_gmem","curve_ddr_sc/S05_AXI","curve_ddr_sc/M00_AXI","zynq_ultra_ps_e_0/S_AXI_HP3_FPD"]
        if audit!=[n+" DATA_WIDTH=128" for n in expected]:raise ValueError("Fusion path is not consistently 128-bit")
        ns={"s":"http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
        component=a.build/"ip/fusion/component.xml";bind(component)
        root=ET.parse(component).getroot()
        bus=next(b for b in root.findall("s:busInterfaces/s:busInterface",ns) if b.find("s:name",ns).text=="m_axi_gmem")
        params={p.find("s:name",ns).text:p.find("s:value",ns).text for p in bus.findall("s:parameters/s:parameter",ns)}
        for k,v in {"DATA_WIDTH":"128","MAX_BURST_LENGTH":"64","NUM_READ_OUTSTANDING":"1","NUM_WRITE_OUTSTANDING":"1"}.items():
            if params.get(k)!=v:raise ValueError("IP transport contract mismatch: "+k)
        result.update(pass_=True,rtl_sha256=rtl_sha,simulation_only_fusion_budget_pass=True)
        result["pass"]=True;result.pop("pass_")
    except Exception as e:
        result["error"]=str(e);raise
    finally:
        out.write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result,indent=2))
if __name__=="__main__":main()
