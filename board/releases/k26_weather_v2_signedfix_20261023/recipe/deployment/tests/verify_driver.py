#!/usr/bin/env python3
"""Compile the C driver and exercise MMIO/DMA mocks, not a physical board."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT.parent/"experiments/onchip_frame"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx",type=Path,required=True)
    p.add_argument("--cc",type=Path,help="defaults to gcc next to g++")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--experiment",choices=("onchip_frame","stream_frame"),default="onchip_frame")
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    core=ROOT.parent/"experiments"/a.experiment
    cxx=a.cxx.resolve();cc=a.cc.resolve() if a.cc else cxx.with_name("gcc.exe" if os.name=="nt" else "gcc")
    env=os.environ.copy();env["PATH"]=str(cxx.parent)+os.pathsep+env.get("PATH","")
    report={"pass":False,"scope":"host C11 driver with emulated MMIO/DMA and real C++ kernels; no board/Linux DMA validation",
            "started_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"steps":[],"source_sha256":{}}
    for base in (ROOT,core):
        for f in sorted(base.rglob("*")):
            if f.is_file() and f.suffix in (".h",".c",".cpp",".py"):
                report["source_sha256"][f.relative_to(ROOT.parent).as_posix()]=sha(f)
    def run(name,cmd,marker=None):
        r=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,errors="replace",env=env,timeout=240)
        log=out/(name+".log");log.write_text(r.stdout+r.stderr,encoding="utf-8")
        ok=r.returncode==0 and (marker is None or marker in r.stdout)
        report["steps"].append({"name":name,"command":[str(x) for x in cmd],"return_code":r.returncode,
                                "log":log.name,"log_sha256":sha(log),"pass":ok})
        if not ok:raise RuntimeError(name+" failed; see "+str(log))
        print(name+" PASS",flush=True)
    try:
        run("compiler",[cxx,"--version"])
        objects=[]
        for name in ("weather_control","weather_tiled"):
            obj=out/(name+".o");objects.append(obj)
            run(name,[cc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-I"+str(ROOT),"-c",ROOT/(name+".c"),"-o",obj])
        exe=out/("test_weather_control.exe" if os.name=="nt" else "test_weather_control")
        cmd=[cxx,"-std=c++11","-O2","-Wall","-Wextra","-Werror","-Wno-unknown-pragmas","-Wno-unused-label",
             "-I"+str(ROOT),"-I"+str(core/"src"),ROOT/"tests/test_weather_control.cpp",
             core/"src/weather_frame.cpp",core/"src/weather_kernel_reference.cpp"]+objects+["-o",exe]
        if os.name=="nt":cmd+=["-static"]
        run("link",cmd)
        run("driver_suite",[exe],"DRIVER_HOST_SUITE_PASS")
        report["executable_sha256"]=sha(exe);report["pass"]=True
    except Exception as exc:
        report["error"]=repr(exc);print(str(exc),file=sys.stderr)
    finally:
        report["finished_utc"]=dt.datetime.now(dt.timezone.utc).isoformat()
        (out/"verification.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["pass"] else 1

if __name__=="__main__":sys.exit(main())
