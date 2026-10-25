"""Use a local copy of the installed vendor runtime; never change the installation."""
import os
from pathlib import Path
import shutil
import subprocess


def run_vendor(tool_root, runtime, executable, arguments, cwd, log):
    tool_root, runtime = Path(tool_root), Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    folders = [tool_root/'lib/win64.o', tool_root/'tps/win64',
               tool_root/'tps/win64/python-3.13.0', tool_root/'tps/win64/python-3.13.0/DLLs',
               tool_root/'tps/win64/jre21.0.5_11/bin']
    # Local application-directory DLL resolution avoids the observed Windows
    # loader failure. Files come exclusively from this exact tool installation.
    for folder in folders:
        for source in folder.glob('*.dll'):
            target = runtime/source.name
            if not target.exists():
                shutil.copy2(source, target)
    shutil.copy2(tool_root/'bin/unwrapped/win64.o'/executable, runtime/executable)
    env = os.environ.copy()
    env.update(RDI_APPROOT=str(tool_root), HDI_APPROOT=str(tool_root), RDI_DATADIR=str(tool_root/'data'),
               RDI_BINDIR=str(tool_root/'bin'), RDI_BINROOT=str(tool_root/'bin'), RDI_BASEROOT=str(tool_root.parent),
               RDI_LIBDIR=str(tool_root/'lib/win64.o'), RDI_PROG=str(runtime/executable),
               RDI_PLATFORM='win64', RDI_OPT_EXT='.o', RDI_INSTALLVERSION='2025.2',
               RDI_INSTALLROOT=str(tool_root.parent.parent), RDI_SHARED_DATA=str(tool_root.parent/'SharedData/data'),
               RDI_JAVAROOT=str(tool_root/'tps/win64/jre21.0.5_11'), XILINX_VIVADO=str(tool_root),
               XILINX_HLS=str(tool_root.parent/'Vitis'), TCL_LIBRARY=str(tool_root/'tps/tcl/tcl8.6'),
               PYTHONHOME=str(tool_root/'tps/win64/python-3.13.0'), PROCESSOR_ARCHITECTURE='AMD64')
    for key in list(env):
        if key.startswith(('RDI_', 'HDI_', 'XILINX_')) or key in ('TCL_LIBRARY', 'PYTHONHOME'):
            env[key] = env[key].replace('\\', '/')
    env['PATH'] = ';'.join(map(str, [runtime, *folders, tool_root/'bin', tool_root/'gnuwin/bin',
                                    tool_root/'tps/win64/jre21.0.5_11/bin/server']))+';'+env['PATH']
    return subprocess.run([str(runtime/executable), *map(str, arguments)], cwd=cwd, env=env,
                          stdout=log, stderr=subprocess.STDOUT)
