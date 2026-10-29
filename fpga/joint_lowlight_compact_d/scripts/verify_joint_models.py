"""Check actual locked HLS C sources and actual fusion RTL against new Golden."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from run_checks import ivl_runtime
from build_system import locked, BASE, D_REF

ROOT = Path(__file__).resolve().parents[1]


def sha(f):
    return hashlib.sha256(Path(f).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--golden",required=True,type=Path)
    p.add_argument("--stage",required=True,choices=["host","fusion"])
    p.add_argument("--d-package",type=Path,default=Path("D:/weather_builds/compact_d_numeric01/package"))
    p.add_argument("--vitis",type=Path,default=Path("D:/vivado/2025.2/Vitis"))
    a=p.parse_args()
    out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    result={"stage":a.stage,"pass":False,"board_operations":0,"steps":[]}
    def execute(label,command,desktop=False):
        print("JOINT_VERIFY="+label,flush=True)
        start=time.perf_counter()
        command=[x.as_posix() if isinstance(x,Path) else str(x) for x in command]
        if desktop:
            command=[sys.executable,"-E",str(out/"run_windows_desktop.py"),"--",*command]
        with (out/(label+".log")).open("xb") as f:
            proc=subprocess.run(command,cwd=out,stdout=f,stderr=subprocess.STDOUT)
        result["steps"].append({"command":command,"exit_code":proc.returncode,
            "seconds":time.perf_counter()-start,"log_sha256":sha(out/(label+".log"))})
        text=(out/(label+".log")).read_text(errors="replace")
        if proc.returncode:raise RuntimeError(label+" failed: "+text[-2000:])
        return text
    try:
        golden=json.loads((a.golden/"result.json").read_text())
        if not golden["pass"]:raise ValueError("Golden generation failed")
        for name,spec in golden["files"].items():
            if sha(a.golden/name)!=spec["sha256"]:raise ValueError("Golden file changed: "+name)
        for name,digest in golden["source_files"].items():
            if sha(a.golden/name)!=digest:raise ValueError("Golden source changed: "+name)
        result["golden_result_sha256"]=sha(a.golden/"result.json")
        if a.stage=="host":
            (out/"run_windows_desktop.py").write_bytes(locked(D_REF,"tools/run_windows_desktop.py"))
            sources=[]; include=[]
            groups=[("fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4",["zero_dce_cnn_top.cpp","zero_dce_cnn_top.h"]),
                ("fpga/perf/cnn_v1_2_phase3b_r4",["row_transfer.hpp","rowstream_arch.inc","rowstream_group_arch.inc"]),
                ("fpga/hls/bilinear_fixed16_buffered",["bilinear_fixed16_buffered.cpp","bilinear_fixed16_buffered.hpp"]),
                ("fpga/hls/curve_image_fixed16",["curve_image_fixed16.cpp","curve_image_fixed16.hpp"]),
                ("fpga/joint_lowlight_compact_d/hls",["joint_adapters.cpp","joint_adapters.hpp"])]
            for folder,names in groups:
                dest=out/"source"/folder; dest.mkdir(parents=True)
                include.append("-I"+dest.as_posix())
                for name in names:
                    f=dest/name; f.write_bytes(locked(BASE,folder+"/"+name))
                    if name.endswith(".cpp"):sources.append(f)
            ddir=out/"source/compact_d"; ddir.mkdir()
            for name in ("compact_d.cpp","compact_d.hpp"):
                (ddir/name).write_bytes(locked(D_REF,"compact_d_fpga/hls/"+name))
            emit=ddir/"emit_parameters.py"
            emit.write_bytes(locked(D_REF,"compact_d_fpga/tools/emit_parameters.py"))
            spec=importlib.util.spec_from_file_location("locked_emit",emit)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            result["d_parameters"]=module.emit(a.d_package,ddir/"generated_parameters.hpp")
            sources.append(ddir/"compact_d.cpp");include.append("-I"+ddir.as_posix())
            test=out/"test_joint_models.cpp";shutil.copy2(ROOT/"tests/test_joint_models.cpp",test)
            exe=out/"test_joint_models.exe"
            execute("compile",["D:/m/mingw64/bin/g++.exe","-std=c++14","-O2","-pthread","-Wno-unknown-pragmas",
                "-I"+(a.vitis/"include").as_posix(),*include,*sources,test,"-o",exe],desktop=True)
            # DLL resolution remains local to this copied executable.
            for f in Path("D:/m/mingw64/bin").glob("*.dll"):shutil.copy2(f,out/f.name)
            text=execute("simulate_host",[exe,a.golden,a.golden/"source"])
            if "JOINT_HLS_HOST_PASS scalars=13775760" not in text.splitlines():
                raise ValueError("Missing full HLS Host success marker")
            result["verification"]="locked HLS C models versus independent same-image integer Golden; no joint RTL claim"
        else:
            tb=(ROOT/"tests/tb_joint_fusion.sv").read_text()
            marker="    function automatic signed [15:0] sample(input integer branch,input integer index);"
            if tb.count(marker)!=1:raise ValueError("Testbench anchor changed")
            arrays="    reg [15:0] frame_i[0:N-1],frame_l[0:N-1],frame_d[0:N-1],frame_o[0:N-1];\n"
            tb=tb.replace(marker,arrays+marker)
            pattern="            sample=$signed(v);"
            tb=tb.replace(pattern,"            sample=branch==0?$signed(frame_i[index]):branch==1?$signed(frame_l[index]):$signed(frame_d[index]);")
            tb=tb.replace("        repeat(6)@(negedge clk);rst=1;", """        $readmemh("original.hex",frame_i);$readmemh("lowlight.hex",frame_l);
        $readmemh("d_output.hex",frame_d);$readmemh("fused.hex",frame_o);
        repeat(6)@(negedge clk);rst=1;""")
            tb=tb.replace("                if(saved_w!=={expected(index+1),expected(index)})", """                if({expected(index+1),expected(index)}!=={frame_o[index+1],frame_o[index]})
                    $fatal(1,"Independent software versus testbench Golden mismatch index=%0d",index);
                if(saved_w!=={frame_o[index+1],frame_o[index]})""")
            tb=tb.replace("FUSION_FULL_FRAME_PASS", "FUSION_SAME_IMAGE_PASS")
            (out/"tb_joint_fusion.sv").write_text(tb,encoding="ascii",newline="\n")
            shutil.copy2(ROOT/"rtl/joint_fusion.v",out/"joint_fusion.v")
            for name in ("original","lowlight","d_output","fused"):
                shutil.copy2(a.golden/(name+".hex"),out/(name+".hex"))
            runtime=ivl_runtime(out,Path("D:/iverilog/install"),Path("D:/m/mingw64/bin"))
            execute("compile",[runtime/"iverilog.exe","-B"+str(runtime),"-g2012","-Wall","-s","tb_joint_fusion",
                "-Ptb_joint_fusion.N=2747520","-o",out/"fusion.vvp",out/"joint_fusion.v",out/"tb_joint_fusion.sv"])
            text=execute("simulate_rtl",[runtime/"vvp.exe",out/"fusion.vvp"])
            if "FUSION_SAME_IMAGE_PASS scalars=2747520 reads=4121280 writes=1373760" not in text.splitlines():
                raise ValueError("Missing full same-image fusion RTL success marker")
            result["verification"]="actual fusion AXI RTL versus same-image I/L/D model outputs and separate software Golden"
        result["sources"]={f.relative_to(out).as_posix():sha(f) for f in out.rglob("*")
            if f.is_file() and f.suffix in (".v",".sv",".cpp",".hpp",".h",".inc")}
        result["pass"]=True
    except Exception as e:
        result["error"]=str(e);raise
    finally:
        (out/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
        print("JOINT_VERIFY_PASS="+str(result["pass"]),flush=True)


if __name__=="__main__":main()
