"""Assemble a fresh local hardware package only after actual route/export gates."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"runtime"))
from controller import BASES, SIZES
from run_pynq import CELLS
from accept_system import timing_summary, route_summary, ps_clock_proof, bus_skew_summary


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")


def utilization_summary(text):
    labels={"CLB LUTs":"LUT","CLB Registers":"FF","Block RAM Tile":"BRAM_tiles","URAM":"URAM","DSPs":"DSP"}
    resources={}
    for line in text.splitlines():
        cells=[v.strip() for v in line.split("|") if v.strip()]
        if len(cells)<6 or cells[0].rstrip("*") not in labels:continue
        used,available,percent=(float(cells[i].replace(",","")) for i in (1,4,5))
        if not 0<=used<=available or not 0<=percent<=100:raise ValueError("Invalid/exceeded routed resources")
        resources[labels[cells[0].rstrip("*")]]={"used":used,"available":available,"percent":percent}
    if len(resources)!=len(labels):raise ValueError("Incomplete routed utilization report")
    return resources


def bitstream_parts(data):
    if len(data)<16:raise ValueError("Truncated bitstream header")
    offset=2+int.from_bytes(data[:2],"big")
    if data[offset:offset+2]!=b"\x00\x01":raise ValueError("Invalid bitstream key header")
    offset+=2;fields={};payload=None
    for key in ("a","b","c","d","e"):
        if data[offset:offset+1]!=key.encode():raise ValueError("Invalid bitstream field sequence")
        offset+=1;size=4 if key=="e" else 2
        if offset+size>len(data):raise ValueError("Truncated bitstream field length")
        count=int.from_bytes(data[offset:offset+size],"big");offset+=size
        if count<=0 or offset+count>len(data):raise ValueError("Truncated/empty bitstream field")
        value=data[offset:offset+count];offset+=count
        if key=="e":payload=value
        else:fields[key]=value.rstrip(b"\0").decode("ascii")
    if offset!=len(data):raise ValueError("Unexpected trailing bitstream data")
    return fields,payload


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--build",required=True,type=Path)
    p.add_argument("--golden",required=True,type=Path)
    p.add_argument("--host",required=True,type=Path)
    p.add_argument("--fusion",required=True,type=Path)
    p.add_argument("--controller-tests",type=Path,help="Frozen host test suite; defaults to the previous pipeline suite")
    p.add_argument("--vivado",type=Path,default=Path("D:/vivado/2025.2/Vivado"))
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or out.with_suffix(".zip").exists():raise ValueError("Refusing to overwrite delivery")
    gates=json.loads((a.build/"gates.json").read_text())
    exported=json.loads((a.build/gates["export"]).read_text())
    acceptance=json.loads((a.build/"acceptance.json").read_text())
    if not exported["pass"] or not acceptance["pass"]:raise ValueError("Export/acceptance failed")
    if sha(a.build/"joint_routed.dcp")!=acceptance["checkpoint_sha256"]:
        raise ValueError("Accepted checkpoint changed")
    for name,digest in acceptance["bound_files"].items():
        if sha(Path(name))!=digest:raise ValueError("Accepted evidence changed: "+name)
    clock_proof=ps_clock_proof((a.build/"reports/export_unused_ps_clocks.txt").read_text(),
        (a.build/"reports/export_clock_check.rpt").read_text())
    timing=timing_summary((a.build/"reports/export_verified_timing.rpt").read_text(),clock_proof)
    route=route_summary((a.build/"reports/export_verified_route.rpt").read_text())
    bus_skew=bus_skew_summary((a.build/"reports/export_bus_skew.rpt").read_text())
    resources=utilization_summary((a.build/"reports/routed_utilization.rpt").read_text())
    out.mkdir(parents=True)
    def copy(source,relative):
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    copy(a.build/"export/joint_system.xsa","joint_system.xsa")
    with zipfile.ZipFile(out/"joint_system.xsa") as xsa:
        if xsa.testzip() is not None:raise ValueError("XSA CRC failure")
        if len(xsa.namelist())!=len(set(xsa.namelist())):raise ValueError("Duplicate XSA members")
        bits=[n for n in xsa.namelist() if n.lower().endswith(".bit")]
        hwhs=[n for n in xsa.namelist() if n.lower().endswith(".hwh")]
        if len(bits)!=1:raise ValueError("Ambiguous XSA embedded bit")
        embedded=xsa.read(bits[0])
        standalone=(a.build/"export/joint_system.bit").read_bytes()
        external_header,external_payload=bitstream_parts(standalone)
        embedded_header,embedded_payload=bitstream_parts(embedded)
        if (external_header["a"]!=embedded_header["a"] or
                external_header["b"]!=embedded_header["b"] or
                embedded_header["b"]!="xck26-sfvc784-2LV-c" or external_payload!=embedded_payload):
            raise ValueError("Standalone/XSA configuration or part mismatch")
        # write_hw_platform runs bitgen again, producing a new date/time header.
        # Publish the exact embedded bit as the canonical standalone artifact;
        # retain both original hashes and prove the configuration bytes agree.
        (out/"joint_system.bit").write_bytes(embedded)
        candidates=[]
        for name in hwhs:
            root=ET.fromstring(xsa.read(name))
            names={m.get("INSTANCE") for m in root.iter("MODULE")}
            if set(CELLS.values()).issubset(names):candidates.append(name)
        if len(candidates)!=1:raise ValueError("Ambiguous/missing six-core system HWH")
        (out/"joint_system.hwh").write_bytes(xsa.read(candidates[0]))
        (out/"evidence").mkdir(exist_ok=True)
        save(out/"evidence/bitstream_equivalence.json",{
            "standalone_source":(a.build/"export/joint_system.bit").resolve().as_posix(),
            "standalone_sha256":hashlib.sha256(standalone).hexdigest(),
            "standalone_header":external_header,"embedded_header":embedded_header,
            "canonical_bit_source":bits[0],"canonical_bit_sha256":sha(out/"joint_system.bit"),
            "configuration_bytes_equal":True,"configuration_bytes":len(embedded_payload),
            "configuration_sha256":hashlib.sha256(embedded_payload).hexdigest(),
            "canonical_hwh_source":candidates[0],"other_hwh_members":[n for n in hwhs if n!=candidates[0]]})
    hwh=ET.parse(out/"joint_system.hwh").getroot()
    modules={m.get("INSTANCE"):m for m in hwh.iter("MODULE")}
    address={}
    revisions={"cnn":2114810448,"bilinear":2114800369,"curve":2114799122,"d":2114844623,"fusion":3}
    expected_masters={
        "cnn":{"m_axi_gmem_input","m_axi_gmem8","m_axi_gmem32","m_axi_gmem_lut","m_axi_gmem_output","m_axi_gmem_workspace"},
        "bilinear":{"m_axi_gmem_input","m_axi_gmem_output"},
        "curve":{"m_axi_gmem_input","m_axi_gmem_parameter","m_axi_gmem_output"},
        "d":{"m_axi_gmem_in","m_axi_gmem_out"},
        "prepare":{"m_axi_gmem_rgb","m_axi_gmem_i","m_axi_gmem_d","m_axi_gmem_cnn"},
        "fusion":{"m_axi_gmem"}}
    ns={"s":"http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009",
        "x":"http://www.xilinx.com"}
    component=ET.parse(a.build/"prepare/hls/impl/ip/component.xml").getroot()
    revisions["prepare"]=int(component.find("./s:vendorExtensions/x:coreExtensions/x:coreRevision",ns).text)
    for key,cell in CELLS.items():
        module=modules.get(cell)
        if module is None:raise ValueError("Core absent from actual HWH: "+cell)
        if key in revisions and int(module.get("COREREVISION"))!=revisions[key]:
            raise ValueError("Core revision mismatch: "+cell)
        ports={p.get("NAME"):p for p in module.iter("PORT")}
        hz=199998001 if key=="d" else 99999001
        clock_net="zynq_ultra_ps_e_0_pl_clk"+("1" if key=="d" else "0")
        reset_net=("rst_ps_d" if key=="d" else "rst_ps_100m")+"_peripheral_aresetn"
        if int(ports["ap_clk"].get("CLKFREQUENCY"))!=hz or ports["ap_clk"].get("SIGNAME")!=clock_net:
            raise ValueError("Actual HWH clock mismatch: "+cell)
        if ports["ap_rst_n"].get("POLARITY")!="ACTIVE_LOW" or ports["ap_rst_n"].get("SIGNAME")!=reset_net:
            raise ValueError("Actual HWH reset mismatch: "+cell)
        mappings={(int(r.get("BASEVALUE"),16),int(r.get("HIGHVALUE"),16)) for r in hwh.iter("MEMRANGE")
            if r.get("INSTANCE")==cell and r.get("MEMTYPE")=="REGISTER"}
        if mappings!={(BASES[key],BASES[key]+0xFFFF)}:raise ValueError("Actual HWH address mismatch: "+cell)
        # Every accelerator master must have a real 2-GiB DDR LOW mapping.
        masters=[]
        for r in module.iter("MEMRANGE"):
            if r.get("MEMTYPE")=="MEMORY" and r.get("ADDRESSBLOCK","").endswith("DDR_LOW"):
                if int(r.get("BASEVALUE"),16)!=0 or int(r.get("HIGHVALUE"),16)!=0x7FFFFFFF:
                    raise ValueError("DDR LOW aperture mismatch")
                masters.append(r.get("MASTERBUSINTERFACE"))
        if set(masters)!=expected_masters[key]:raise ValueError("Missing/unexpected DDR LOW master mapping in HWH: "+cell)
        address[key]={"cell":cell,"base":f"0x{BASES[key]:08X}","range":65536,
            "vlnv":module.get("VLNV"),"revision":int(module.get("COREREVISION")),"ddr_low_masters":sorted(set(masters)),
            "clock_hz":hz,"clock_net":clock_net,"active_low_reset_net":reset_net}
    # Disjoint register apertures are also checked from actual extracted HWH.
    values=sorted(BASES.values())
    if any(b-a<65536 for a,b in zip(values,values[1:])):raise ValueError("Control apertures overlap")
    save(out/"address_map.json",{"cores":address,"buffer_bytes":SIZES,"frame_shape_nchw":[1,3,720,1272],
        "ddr_low_aperture_end_exclusive":"0x80000000","usable_allocation_end_exclusive":"0x7FF00000",
        "reset":{"source":"PS/pl_resetn0","active_low":True,"separate_synchronizers":["rst_ps_100m","rst_ps_d"]}})
    for file in (ROOT/"runtime").iterdir():
        if file.is_file() and file.suffix in (".py",".c"):copy(file,"runtime/"+file.name)
    for name in ("loading_order.md","fusion_contract.md","clock_coverage.md","fusion_pipeline_30fps.md","prepare_pipeline.md"):
        copy(ROOT/"docs"/name,"docs/"+name)
    copy(ROOT/"PIPELINE_CHANGE_REVIEW_20261101.md","docs/PIPELINE_CHANGE_REVIEW_20261101.md")
    copy(ROOT/"PREPARE_CHANGE_REVIEW_20261101.md","docs/PREPARE_CHANGE_REVIEW_20261101.md")
    for file in (a.build/"reports").iterdir():
        if file.is_file():copy(file,"reports/"+file.name)
    implementation=a.build/"project/joint_system.runs/impl_1"
    lineage_path=a.build/"timing_lineage.json"
    if lineage_path.exists():
        lineage=json.loads(lineage_path.read_text())
        margin=json.loads((a.build/"timing_margin_audit.json").read_text())
        if (not lineage["pass"] or not margin["pass"] or
                lineage["checkpoint_sha256"]!=acceptance["checkpoint_sha256"] or
                margin["checkpoint_sha256"]!=acceptance["checkpoint_sha256"] or
                sha(a.build/"timing_margin_audit.json")!=lineage["margin_audit_sha256"]):
            raise ValueError("Physical optimization lineage mismatch")
        for name,digest in margin["bound_files"].items():
            if sha(Path(name))!=digest:raise ValueError("Physical optimization evidence changed: "+name)
        implementation=(None if lineage.get("kind")=="targeted_fifo_rebuild" else
                        Path(lineage["parent_build"])/"project/joint_system.runs/impl_1")
        copy(lineage_path,"evidence/timing_lineage.json")
        copy(a.build/"timing_margin_audit.json","evidence/timing_margin_audit.json")
        for folder in ("physical_optimization","inherited_baseline"):
            for file in (a.build/folder).rglob("*"):
                if file.is_file():copy(file,"evidence/"+folder+"/"+file.relative_to(a.build/folder).as_posix())
        copy(ROOT/"docs/timing_margin_20261102.md","docs/timing_margin_20261102.md")
    if implementation is not None:
        copy(implementation/"runme.log","reports/implementation_runme.log")
        for name in ("system_wrapper_timing_summary_routed.rpt", "system_wrapper_route_status.rpt",
                     "system_wrapper_drc_routed.rpt", "system_wrapper_bus_skew_routed.rpt"):
            copy(implementation/name,"reports/pre_postroute_opt_"+name)
        for file in implementation.glob("*incremental_reuse*.rpt*"):
            if file.is_file():copy(file,"reports/"+file.name)
    else:
        copy(a.build/"release_approval.json","evidence/release_approval.json")
        copy(a.build/"accepted_original_inputs.json","evidence/accepted_original_inputs.json")
        original_inputs=json.loads((a.build/"accepted_original_inputs.json").read_text())
        implemented={}
        for relative,digest in original_inputs["source_files"].items():
            file=a.build/relative
            if sha(file)!=digest:raise ValueError("Implemented release source changed: "+relative)
            if file.suffix.lower() in (".v",".sv",".vh",".vhd",".tcl",".py",".xml",".cpp",".hpp",".json"):
                copy(file,"source/implemented_inputs/"+relative)
                implemented[relative]=digest
        generated=json.loads((Path(lineage["parent_build"])/"targeted_generated_sources.json").read_text())
        for row in generated:
            file=Path(lineage["parent_build"])/row["path"]
            if sha(file)!=row["after"]:raise ValueError("Implemented generated wrapper changed")
            copy(file,"source/generated_smartconnect/"+row["path"])
        save(out/"evidence/implemented_source_manifest.json",{"files":implemented,"generated_smartconnect":generated})
    for stage,name in gates.items():
        copy(a.build/name,"evidence/"+stage+"_result.json")
        record=json.loads((a.build/name).read_text());tag=name.removesuffix("_result.json")
        if record.get("steps"):
            log=a.build/(tag+(".log" if stage=="adapter" else "_console.log"))
            if len(record["steps"])!=1 or sha(log)!=record["steps"][0]["log_sha256"]:
                raise ValueError("Stage execution log identity mismatch: "+stage)
            copy(log,"evidence/"+log.name)
        if "script_sha256" in record:
            script=a.build/(tag+"_build.tcl")
            if sha(script)!=record["script_sha256"]:raise ValueError("Stage script identity mismatch: "+stage)
            copy(script,"evidence/"+script.name)
    copy(a.build/"acceptance.json","evidence/acceptance.json")
    copy(a.build/"fusion_pipeline_acceptance.json","evidence/fusion_pipeline_acceptance.json")
    copy(a.build/"prepare_pipeline_acceptance.json","evidence/prepare_pipeline_acceptance.json")
    copy(a.build/"inputs.json","evidence/inputs.json")
    copy(a.host/"result.json","evidence/same_image_hls_host.json")
    copy(a.host/"simulate_host.log","evidence/same_image_hls_host.log")
    copy(a.fusion/"result.json","evidence/same_image_fusion_rtl.json")
    copy(a.fusion/"simulate_rtl.log","evidence/same_image_fusion_rtl.log")
    copy(a.golden/"result.json","golden/manifest.json")
    golden_record=json.loads((a.golden/"result.json").read_text())
    golden_files=set(golden_record["files"])|set(golden_record["source_files"])
    golden_files.update("d_nodes/"+node["file"] for node in golden_record["d_nodes"])
    for relative in sorted(golden_files):copy(a.golden/relative,"golden/"+relative)
    for name in ("weights_int8.bin","bias_int32.bin","weight_frac.bin","tanh_lut_q15.bin"):
        copy(a.golden/"source"/name,"model/"+name)
    for src,name in (("lowlight_frozen_ip.zip","lowlight_frozen_ip.zip"),("compact_d_ip.zip","compact_d_ip.zip"),
                     ("joint_fusion_ip.zip","joint_fusion_ip.zip"),
                     ("prepare/hls/impl/ip/xilinx_com_hls_joint_rgb8_prepare_1_0.zip","joint_rgb8_prepare_ip.zip")):
        folder="reference_ip/" if implementation is None and name in ("lowlight_frozen_ip.zip","compact_d_ip.zip") else "ip/"
        copy(a.build/src,folder+name)
    # Include new source and all pipeline gates before hashing/final packaging.
    pipeline=json.loads((a.build/"fusion_pipeline_acceptance.json").read_text())
    for path in pipeline["bound_files"]:
        file=Path(path)
        if "fusion_pipeline_20261101" in file.parts:
            suite_root=next(parent for parent in file.parents if parent.name=="fusion_pipeline_20261101")
            relative=file.relative_to(suite_root)
            copy(file,"evidence/pipeline/"+relative.as_posix())
    prepare=json.loads((a.build/"prepare_pipeline_acceptance.json").read_text())
    for path,digest in prepare["bound_files"].items():
        file=Path(path)
        if sha(file)!=digest:raise ValueError("Prepare delivery evidence changed")
        if "prepare_pipeline_20261101" in file.parts:
            suite=next(parent for parent in file.parents if parent.name=="prepare_pipeline_20261101")
            copy(file,"evidence/prepare/"+file.relative_to(suite).as_posix())
    prepare_suite=next(parent for parent in Path(prepare["cosim_report"]).parents if parent.name=="prepare_pipeline_20261101")
    for name in ("cosim01","cosim02","cosim03"):
        folder=prepare_suite/name
        record=json.loads((folder/"result.json").read_text())
        if record["pass"]:raise ValueError("Expected preserved prepare failure changed")
        for file in [folder/"result.json",*folder.glob("*.log")]:
            copy(file,"evidence/prepare/"+file.relative_to(prepare_suite).as_posix())
    for file in (a.build/"source").iterdir():
        if file.suffix in (".cpp",".hpp"):copy(file,"source/hls/"+file.name)
    for folder in ("rtl","scripts"):
        for file in (ROOT/folder).iterdir():
            if file.is_file() and file.suffix in (".v",".py",".tcl"):
                copy(file,"source/"+folder+"/"+file.name)
    for file in (ROOT/"tests").iterdir():
        if file.is_file() and file.suffix in (".sv", ".py", ".cpp"):
            copy(file,"source/tests/"+file.name)
    suite_root=a.fusion.parent
    audit_path=suite_root/"source_evidence_audit01.json"
    audit=json.loads(audit_path.read_text(encoding="utf-8"))
    if not audit["pass"]:raise ValueError("Pipeline source/evidence audit failed")
    for path,digest in audit["bound_files"].items():
        file=Path(path)
        if sha(file)!=digest:raise ValueError("Pipeline audited evidence changed: "+path)
        if suite_root in file.parents:
            copy(file,"evidence/pipeline/"+file.relative_to(suite_root).as_posix())
    copy(audit_path,"evidence/pipeline/"+audit_path.name)
    host_suite=a.controller_tests or suite_root/"controller_tests02"
    host_record=json.loads((host_suite/"result.json").read_text(encoding="utf-8"))
    if not host_record["pass"] or host_record["exit_code"]!=0:
        raise ValueError("Pipeline entry host tests failed")
    if sha(host_suite/"tests.log")!=host_record["log_sha256"]:
        raise ValueError("Pipeline entry test log changed")
    for relative,digest in host_record["source_sha256"].items():
        file=host_suite/"source"/relative
        if sha(file)!=digest or sha(ROOT/relative)!=digest:
            raise ValueError("Pipeline entry tested source changed: "+relative)
        copy(file,"evidence/pipeline/controller_tests02/source/"+relative)
    for name in ("result.json","tests.log"):
        copy(host_suite/name,"evidence/pipeline/controller_tests02/"+name)
    from delivery_supplement import add_supplements
    add_supplements(out,a.build,embedded_payload,a.vivado)
    if implementation is None:
        with (out/"README.md").open("a",encoding="utf-8") as stream:
            stream.write("\n本包采用 2026-11-02 接受的六 FIFO 定向改进版；原约束 setup 0.391 ns、hold 0.100 ns。导出阶段没有重新综合、布局或优化。完整来源、实际 RTL 输入和 132 份 SmartConnect wrapper 分别见 evidence/timing_lineage.json、source/implemented_inputs/ 和 source/generated_smartconnect/。reference_ip/ 是算法版本来源的历史原包，不能代替已修改的实现输入；ip/ 中的 Prepare、融合包继续与实现一致。历史审核失败记录保留，最终独立审核为 evidence/timing_margin_audit.json。\n")
    build_id=hashlib.sha256((sha(a.build/"inputs.json")+acceptance["checkpoint_sha256"]).encode()).hexdigest()[:20]
    files={f.relative_to(out).as_posix():{"bytes":f.stat().st_size,"sha256":sha(f)}
           for f in sorted(out.rglob("*")) if f.is_file()}
    manifest={"status":"HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED","build_id":build_id,
        "date":date.today().isoformat(),"part":"xck26-sfvc784-2LV-c","board":"xilinx.com:kv260_som:part0:1.4",
        "vivado":"2025.2","timing":timing,"route":route,"bus_skew":bus_skew,"resources":resources,
        "resource_bottleneck":max(resources,key=lambda k:resources[k]["percent"]),"board_operations":0,"fps_claim":False,
        "embedded_bit_matches_external":True,"checkpoint_sha256":acceptance["checkpoint_sha256"],
        "validation_scope":"same-image locked model/fusion Golden plus full-frame burst prepare C/RTL comparison; no full six-core RTL or board numerical claim",
        "files":files}
    save(out/"manifest.json",manifest)
    checksums={f.relative_to(out).as_posix():sha(f) for f in sorted(out.rglob("*")) if f.is_file()}
    (out/"SHA256SUMS").write_text("".join(digest+"  "+name+"\n" for name,digest in checksums.items()),encoding="ascii",newline="\n")
    archive=out.with_suffix(".zip")
    with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in sorted(out.rglob("*")):
            if file.is_file():z.write(file,file.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError("Delivery ZIP CRC failure")
        for name,digest in checksums.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError("Delivery ZIP payload mismatch")
    archive.with_suffix(".zip.sha256").write_text(sha(archive)+"  "+archive.name+"\n",encoding="ascii")
    result={"pass":True,"package":out.as_posix(),"zip":archive.as_posix(),"zip_sha256":sha(archive),
            "zip_bytes":archive.stat().st_size,"manifest_sha256":sha(out/"manifest.json"),"build_id":build_id,
            "timing":timing,"route":route,"bus_skew":bus_skew,"resources":resources,"board_operations":0}
    save(out.parent/(out.name+"_result.json"),result)
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
