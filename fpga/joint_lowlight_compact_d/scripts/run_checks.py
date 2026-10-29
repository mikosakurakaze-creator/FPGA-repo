"""Run real RTL checks/OOC synthesis, recording results outside the repository."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ivl_runtime(root, installation, compiler):
    runtime=root/"ivl_runtime"
    runtime.mkdir()
    for p in (installation/"lib/ivl").iterdir():
        if p.is_file():shutil.copy2(p,runtime/p.name)
    for name in ("iverilog.exe","vvp.exe"):
        shutil.copy2(installation/"bin"/name,runtime/name)
    # Local DLL resolution, without altering the tool installation or machine PATH.
    for p in compiler.glob("*.dll"):shutil.copy2(p,runtime/p.name)
    return runtime


def vendor_runtime(root, installation):
    runtime=root/"vendor_runtime"
    runtime.mkdir()
    folders=[installation/"lib/win64.o",installation/"tps/win64",
             installation/"tps/win64/python-3.13.0",installation/"tps/win64/python-3.13.0/DLLs",
             installation/"tps/win64/jre21.0.5_11/bin",
             installation/"tps/win64/jre21.0.5_11/bin/server"]
    for folder in folders:
        for p in folder.glob("*.dll"):
            if not (runtime/p.name).exists():shutil.copy2(p,runtime/p.name)
    exe=runtime/"vivado.exe"
    shutil.copy2(installation/"bin/unwrapped/win64.o/vivado.exe",exe)
    env=os.environ.copy()
    env.update(RDI_APPROOT=str(installation),HDI_APPROOT=str(installation),
               RDI_DATADIR=str(installation/"data"),RDI_BINDIR=str(installation/"bin"),
               RDI_BINROOT=str(installation/"bin"),RDI_BASEROOT=str(installation.parent),
               RDI_LIBDIR=str(installation/"lib/win64.o"),RDI_PROG=str(exe),
               RDI_PLATFORM="win64",RDI_OPT_EXT=".o",RDI_INSTALLVERSION="2025.2",
               RDI_INSTALLROOT=str(installation.parent.parent),
               RDI_SHARED_DATA=str(installation.parent/"SharedData/data"),
               RDI_JAVAROOT=str(installation/"tps/win64/jre21.0.5_11"),
               XILINX_VIVADO=str(installation),XILINX_HLS=str(installation.parent/"Vitis"),
               RT_LIBPATH=str(installation/"scripts/rt/data"),SYNTH_COMMON=str(installation/"scripts/rt/data"),
               RT_TCL_PATH=str(installation/"scripts/rt/base_tcl/tcl"),
               TCL_LIBRARY=str(installation/"tps/tcl/tcl8.6"),
               PYTHONHOME=str(installation/"tps/win64/python-3.13.0"),PROCESSOR_ARCHITECTURE="AMD64")
    for key in env:
        if key.startswith(("RDI_","HDI_","XILINX_")) or key in ("TCL_LIBRARY","PYTHONHOME","RT_LIBPATH","RT_TCL_PATH","SYNTH_COMMON"):
            env[key]=env[key].replace("\\","/")
    env["PATH"]=";".join(str(p) for p in [runtime,*folders,installation/"bin",installation/"gnuwin/bin",
                         installation/"tps/win64/jre21.0.5_11/bin/server"])+";"+env.get("PATH","")
    return exe,env


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--stage",choices=("rtl","full","ooc","package","verify"),required=True)
    p.add_argument("--checkpoint",type=Path)
    p.add_argument("--iverilog",type=Path,default=Path("D:/iverilog/install"))
    p.add_argument("--compiler-bin",type=Path,default=Path("D:/m/mingw64/bin"))
    p.add_argument("--vivado",type=Path,default=Path("D:/vivado/2025.2/Vivado"))
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__,out/"run_checks.py")
    shutil.copy2(ROOT/"rtl/joint_fusion.v",out/"joint_fusion.v")
    shutil.copy2(ROOT/"tests/tb_joint_fusion.sv",out/"tb_joint_fusion.sv")
    result={"stage":a.stage,"pass":False,"board_operations":0,"steps":[],
            "source_sha256":{str(f.relative_to(ROOT)).replace("\\","/"):sha(f)
            for f in (ROOT/"rtl/joint_fusion.v",ROOT/"tests/tb_joint_fusion.sv",Path(__file__))}}
    def execute(name,command,env=None):
        start=time.perf_counter()
        command=[v.as_posix() if isinstance(v,Path) else str(v) for v in command]
        with (out/(name+".log")).open("wb") as log:
            r=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
        result["steps"].append({"name":name,"command":list(map(str,command)),"return_code":r.returncode,
                                "seconds":time.perf_counter()-start,"log_sha256":sha(out/(name+".log"))})
        log=(out/(name+".log")).read_text(errors="replace")
        if r.returncode:raise RuntimeError(name+" failed: "+log[-3000:])
        return log
    try:
        if a.stage in ("rtl","full"):
            runtime=ivl_runtime(out,a.iverilog,a.compiler_bin)
            n=2747520 if a.stage=="full" else 65536
            execute("compile",[runtime/"iverilog.exe","-B"+str(runtime),"-g2012","-Wall",
                    "-s","tb_joint_fusion","-Ptb_joint_fusion.N="+str(n),"-o",out/"fusion.vvp",
                    ROOT/"rtl/joint_fusion.v",ROOT/"tests/tb_joint_fusion.sv"])
            log=execute("simulate",[runtime/"vvp.exe",out/"fusion.vvp"])
            marker="FUSION_FULL_FRAME_PASS scalars=2747520" if a.stage=="full" else "FUSION_RTL_PASS frames=10 invalid=9 scalars=655360"
            if not any(line.startswith(marker) for line in log.splitlines()):raise RuntimeError("Missing full RTL success marker")
            result["verification"]="AXI RTL versus independent signed-floor integer Golden"
            result["success_line"]=next(line for line in log.splitlines() if line.startswith(marker))
        else:
            exe,env=vendor_runtime(out,a.vivado)
            script={"package":"fusion_package.tcl","ooc":"fusion_ooc.tcl","verify":"fusion_verify.tcl"}[a.stage]
            if a.stage=="verify":
                if a.checkpoint is None:raise ValueError("--checkpoint is required for verify")
                result["checkpoint_sha256"]=sha(a.checkpoint)
            shutil.copy2(ROOT/"rtl/joint_fusion.v",out/"joint_fusion.v")
            shutil.copy2(ROOT/"scripts"/script,out/script)
            log=execute("vendor_console",[exe,"-mode","batch","-log",out/"vivado.log","-journal",out/"vivado.jou",
                    "-source",out/script,"-tclargs",a.checkpoint if a.stage=="verify" else out/"joint_fusion.v",out/a.stage],env)
            marker={"package":"FUSION_IP_PACKAGE_PASS","ooc":"FUSION_OOC_SYNTHESIS_PASS","verify":"FUSION_CHECKPOINT_VERIFICATION_PASS"}[a.stage]
            if marker not in log.splitlines():raise RuntimeError("Missing vendor success marker")
            result["reports"]={str(f.relative_to(out)).replace("\\","/"):sha(f) for f in (out/a.stage).glob("*.rpt")}
            if a.stage=="package":
                result["ip_zip_sha256"]=sha(out/"package/joint_fusion_ip.zip")
                result["component_sha256"]=sha(out/"package/ip/component.xml")
                result["verification"]="Vivado IP packaging/integrity; no complete-system claim"
            elif a.stage=="verify":
                if sha(a.checkpoint)!=result["checkpoint_sha256"]:raise ValueError("Checkpoint changed")
                result["verification"]="Independent reopening of actual OOC checkpoint; not complete-system signoff"
            else:result["verification"]="K26 OOC synthesis; not a complete-system timing signoff"
        result["pass"]=True
    except Exception as e:
        result["error"]=str(e)
        raise
    finally:
        (out/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,indent=2),flush=True)


if __name__=="__main__":main()
