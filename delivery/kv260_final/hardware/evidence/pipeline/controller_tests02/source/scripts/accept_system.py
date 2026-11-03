"""Fail-closed acceptance of actual routed reports and same-image verification."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


PS_CLOCK_NAMES={"EMIOENET0MDIOMDC","EMIOENET1MDIOMDC","EMIOENET2MDIOMDC","EMIOENET3MDIOMDC",
                "EMIOSDIO0CLKOUT","EMIOSDIO1CLKOUT","EMIOSPI0SCLKO","EMIOSPI1SCLKO"}
PS_CLOCK_PINS={"system_i/zynq_ultra_ps_e_0/inst/PS8_i/"+name for name in PS_CLOCK_NAMES}


def ps_clock_proof(proof_text,check_text):
    pins=[]
    for line in proof_text.splitlines():
        if not line.startswith("PIN "):continue
        m=re.fullmatch(r"PIN (\S+) REF=PS8 DIR=OUT INPUT_LOADS=0 TOP_PORTS=0 CLOCKS=0 NETS=.*",line)
        if m is None:raise ValueError("Unused-PS proof has an active/unknown clock output")
        pins.append(m[1])
    if len(pins)!=8 or set(pins)!=PS_CLOCK_PINS or "CHECKED_UNUSED_PS_OUTPUTS=8" not in proof_text.splitlines():
        raise ValueError("Incomplete/changed unused PS output proof")
    section=re.search(r"There are (\d+) register/latch pins with no clock[^\n]*\n(.*?)(?=\n\s*2\. checking constant_clock)",check_text,re.S)
    if section is None:raise ValueError("Detailed no_clock evidence missing")
    reported=[v.strip() for v in section[2].splitlines() if v.strip().startswith("system_i/")]
    count=int(section[1])
    if count not in (0,8) or len(reported)!=count or (count and set(reported)!=PS_CLOCK_PINS):
        raise ValueError("Active/unknown unclocked pins in detailed report")
    return {"verified_unused_ps_outputs":sorted(pins),"reported_no_clock_pins":sorted(reported)}


def timing_summary(text,unused_ps_proof=None):
    pos=text.find("WNS(ns)")
    if pos<0:raise ValueError("Timing table missing")
    fields=None
    for line in text[pos:].splitlines()[1:8]:
        row=line.split()
        if len(row)>=10 and all(re.fullmatch(r"-?\d+(?:\.\d+)?", v) for v in row):
            fields=list(map(float,row));break
    if fields is None:raise ValueError("Timing numbers missing")
    if fields[0]<0 or fields[1]!=0 or fields[4]<0 or fields[5]!=0 or fields[8]<0 or fields[9]!=0:
        raise ValueError("Routed setup/hold/pulse-width timing failed")
    checks={}
    for key in ("no_clock","constant_clock","unconstrained_internal_endpoints","multiple_clock"):
        match=re.search(r"checking "+key+r"\s+\((\d+)\)",text)
        if match is None:raise ValueError("Timing coverage missing: "+key)
        checks[key]=int(match[1])
        if checks[key]:
            if (key=="no_clock" and checks[key]==8 and unused_ps_proof is not None and
                    set(unused_ps_proof["reported_no_clock_pins"])==PS_CLOCK_PINS and
                    set(unused_ps_proof["verified_unused_ps_outputs"])==PS_CLOCK_PINS):
                continue
            raise ValueError("Timing coverage failure: "+key+"="+match[1])
    checks["active_unclocked_pins"]=0
    checks["classified_unused_ps_no_clock_outputs"]=checks["no_clock"]
    checks["verified_unloaded_ps_clock_outputs"]=len(unused_ps_proof["verified_unused_ps_outputs"]) if unused_ps_proof else 0
    return {"WNS_ns":fields[0],"WHS_ns":fields[4],"WPWS_ns":fields[8],"coverage":checks}


def route_summary(text):
    counts={}
    for key in ("routable nets","fully routed nets","nets with routing errors"):
        match=re.search(r"# of "+key+r"\.+\s*:\s*(\d+)",text)
        if match is None:raise ValueError("Route coverage missing: "+key)
        counts[key]=int(match[1])
    if counts["routable nets"]<=0 or counts["routable nets"]!=counts["fully routed nets"] or counts["nets with routing errors"]:
        raise ValueError("Incomplete/failed routing")
    return counts


def bus_skew_summary(text):
    section=re.search(r"1\. Bus Skew Report Summary\s*\n-+\s*\n(.*?)(?=\n2\. Bus Skew Report Per Constraint\s*\n-+)",text,re.S)
    if section is None:raise ValueError("Bus skew summary missing")
    ids=[int(v) for v in re.findall(r"^\s*(\d+)\s+\d+\s+",section[1],re.M)]
    number=r"(-?\d+(?:\.\d+)?)"
    rows=[tuple(map(float,row)) for row in re.findall(
        r"^\s*(?:Slow|Fast)\s+"+number+r"\s+"+number+r"\s+"+number+r"\s*$",section[1],re.M)]
    if not ids or ids!=list(range(1,len(ids)+1)) or len(rows)!=len(ids):
        raise ValueError("Incomplete bus skew constraint coverage")
    if any(requirement<=0 or actual<0 or slack<0 for requirement,actual,slack in rows):
        raise ValueError("Bus skew constraint failed")
    return {"constraints":len(rows),"worst_slack_ns":min(row[2] for row in rows),"violations":0}


def critical_rows(text, severities):
    bad=[]
    for line in text.splitlines():
        if "|" not in line:
            # Vivado report_cdc uses whitespace columns; report_drc uses pipes.
            row=re.match(r"^\s*(?:\d+\s+)?(?:CDC|[A-Z][A-Z0-9]*)-\d+\s+"
                         r"(Critical Warning|Critical|Error|Warning|Info)\b\s*(.*)$",line,re.I)
            if row is None or row[1].lower() not in severities:continue
            count=re.match(r"^(\d+)(?:\s|$)",row[2])
            if count is None or int(count[1]):bad.append(line.strip())
            continue
        fields=[v.strip() for v in line.split("|") if v.strip()]
        if not any(v.lower() in severities for v in fields):continue
        if not any(re.fullmatch(r"(?:CDC|[A-Z]+)-\d+", v) for v in fields):continue
        numbers=[int(v) for v in fields if v.isdecimal()]
        if not numbers or any(numbers):bad.append(line.strip())
    return bad


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--build",required=True,type=Path)
    p.add_argument("--host",required=True,type=Path)
    p.add_argument("--fusion",required=True,type=Path)
    p.add_argument("--golden",required=True,type=Path)
    a=p.parse_args();out=a.build/"acceptance.json"
    if out.exists():raise ValueError("Preserve previous acceptance; use a new audit filename/build for retry")
    result={"pass":False,"board_operations":0,"bound_files":{}}
    def bind(path):
        path=path.resolve();result["bound_files"][path.as_posix()]=sha(path)
        return path.read_text(errors="replace")
    try:
        result["stage_index_sha256_at_acceptance"]=sha(a.build/"gates.json")
        gates=json.loads((a.build/"gates.json").read_text())
        for stage in ("prepare","adapter","create","synth","implement","coverage"):
            record=json.loads(bind(a.build/gates[stage]))
            if not record["pass"]:raise ValueError("Required hardware stage failed: "+stage)
        # A modified fusion requires proof bound to the exact integrated RTL.
        pipeline=json.loads(bind(a.build/"fusion_pipeline_acceptance.json"))
        if not pipeline["pass"] or not pipeline["simulation_only_fusion_budget_pass"]:
            raise ValueError("Fusion throughput/transport gate failed")
        for path,digest in pipeline["bound_files"].items():
            if sha(Path(path))!=digest:raise ValueError("Pipeline evidence changed: "+path)
            result["bound_files"][path]=digest
        prepare=json.loads(bind(a.build/"prepare_pipeline_acceptance.json"))
        if not prepare["pass"] or not prepare["simulation_only_prepare_budget_pass"]:
            raise ValueError("Prepare numeric/RTL/transport gate failed")
        if sha(a.build/"source/joint_adapters.cpp")!=prepare["source_sha256"]:
            raise ValueError("Integrated prepare source changed")
        for path,digest in prepare["bound_files"].items():
            if sha(Path(path))!=digest:raise ValueError("Prepare evidence changed: "+path)
            result["bound_files"][path]=digest
        if sha(a.fusion/"joint_fusion.v")!=pipeline["rtl_sha256"]:
            raise ValueError("Numerical RTL differs from integrated pipeline RTL")
        result["checkpoint_sha256"]=sha(a.build/"joint_routed.dcp")
        if record["checkpoint_sha256"]!=result["checkpoint_sha256"]:raise ValueError("Clock proof checkpoint changed")
        result["unused_ps_clock_proof"]=ps_clock_proof(bind(a.build/"reports/routed_unused_ps_clocks.txt"),
            bind(a.build/"reports/routed_clock_check.rpt"))
        timing=bind(a.build/"reports/routed_timing.rpt")
        result["timing"]=timing_summary(timing,result["unused_ps_clock_proof"])
        result["route"]=route_summary(bind(a.build/"reports/route_status.rpt"))
        result["bus_skew"]=bus_skew_summary(bind(a.build/"reports/routed_bus_skew.rpt"))
        for name,severities in (("routed_drc.rpt",{"error","critical warning"}),("routed_cdc.rpt",{"critical","error"})):
            text=bind(a.build/"reports"/name)
            expected="Report DRC" if name=="routed_drc.rpt" else "CDC Report"
            if expected not in text:raise ValueError("Missing report structure: "+name)
            rows=critical_rows(text,severities)
            if rows:raise ValueError("Unresolved "+name+": "+"; ".join(rows[:5]))
        for folder,stage in ((a.host,"host"),(a.fusion,"fusion")):
            record=json.loads(bind(folder/"result.json"))
            if not record["pass"] or record["stage"]!=stage:raise ValueError("Numerical gate failed: "+stage)
            log_names=("compile.log","simulate_host.log" if stage=="host" else "simulate_rtl.log")
            if len(record["steps"])!=len(log_names):raise ValueError("Unexpected numerical process count")
            for step,log_name in zip(record["steps"],log_names):
                if step["exit_code"]!=0:raise ValueError("Nonzero numerical process exit")
                log_path=folder/log_name
                if sha(log_path)!=step["log_sha256"]:raise ValueError("Numerical execution log changed")
                bind(log_path)
            for name,digest in record["sources"].items():
                if sha(folder/name)!=digest:raise ValueError("Numerical source identity changed: "+name)
                result["bound_files"][(folder/name).resolve().as_posix()]=digest
        golden=json.loads(bind(a.golden/"result.json"))
        if not golden["pass"] or golden["shape"]!=[1,3,720,1272]:raise ValueError("Wrong Golden shape/state")
        if golden["historical_cnn_mismatches"]!=0:raise ValueError("CNN historical identity gate failed")
        if len(golden["d_nodes"])!=22:raise ValueError("Incomplete same-image D node evidence")
        for node in golden["d_nodes"]:
            path=a.golden/"d_nodes"/node["file"]
            if sha(path)!=node["sha256"]:raise ValueError("D node Golden changed: "+node["id"])
            result["bound_files"][path.resolve().as_posix()]=node["sha256"]
        if (golden["d_nodes"][0]["sha256"]!=golden["files"]["d_input.i16"]["sha256"] or
                golden["d_nodes"][-1]["sha256"]!=golden["files"]["d_output.i16"]["sha256"]):
            raise ValueError("D node input/output identity mismatch")
        for name,digest in golden["source_files"].items():
            path=a.golden/name
            if sha(path)!=digest:raise ValueError("Golden source identity changed: "+name)
            result["bound_files"][path.resolve().as_posix()]=digest
        for name,spec in golden["files"].items():
            path=a.golden/name
            if sha(path)!=spec["sha256"]:raise ValueError("Golden identity changed: "+name)
            result["bound_files"][path.resolve().as_posix()]=spec["sha256"]
        expected_golden=sha(a.golden/"result.json")
        for folder in (a.host,a.fusion):
            if json.loads((folder/"result.json").read_text())["golden_result_sha256"]!=expected_golden:
                raise ValueError("Numerical tests used a different Golden")
        result["pass"]=True
        result["status"]="ROUTED_HARDWARE_AND_NUMERICAL_GATES_PASS_BOARD_NOT_TESTED"
    except Exception as e:
        result["error"]=str(e);raise
    finally:
        out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
        print(json.dumps(result,indent=2))


if __name__=="__main__":main()
