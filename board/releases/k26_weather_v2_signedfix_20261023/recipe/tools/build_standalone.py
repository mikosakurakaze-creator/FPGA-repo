"""Vitis 2025.2 Python CLI script; creates an A53 standalone weather smoke ELF.

Environment: WEATHER_XSA, WEATHER_SW_WORKSPACE, WEATHER_SOURCE_ROOT.
Run with vitis.bat -s SCRIPT after building the combined XSA. Never connects
to hardware or launches the application.
"""
import os
from pathlib import Path
import shutil
import vitis

source = Path(os.environ['WEATHER_SOURCE_ROOT']).resolve()
workspace = Path(os.environ['WEATHER_SW_WORKSPACE']).resolve()
xsa = Path(os.environ['WEATHER_XSA']).resolve()
if workspace.exists() or not xsa.is_file():
    raise RuntimeError('New workspace and existing XSA required')
if shutil.which('aarch64-none-elf-gcc') is None:
    raise RuntimeError('A53 standalone compiler aarch64-none-elf-gcc is absent. '
                       'Install the matching Vitis Embedded/AArch64 toolchain; '
                       'the HLS/Vivado-only installation cannot build this ELF.')
client = vitis.create_client()
try:
    client.set_workspace(path=str(workspace))
    platform = client.create_platform_component(name='weather_platform', hw_design=str(xsa),
        os='standalone', cpu='psu_cortexa53_0', domain_name='a53_standalone',
        no_boot_bsp=True, generate_dtb=False)
    platform.build()
    xpfm = client.find_platform_in_repos('weather_platform')
    app = client.create_app_component(name='weather_smoke', platform=xpfm, domain='a53_standalone')
    app.import_files(from_loc=str(source / 'deployment'), files=[
        'weather_control.c', 'weather_control.h', 'weather_xilinx_standalone.c',
        'weather_xilinx_standalone.h'])
    app.import_files(from_loc=str(source / 'deployment/standalone'),
                     files=['main.c', 'weather_smoke_vectors.h'])
    app.build()
    elfs = list(workspace.rglob('weather_smoke.elf'))
    if not elfs:
        raise RuntimeError('ELF absent after build')
    print('WEATHER_STANDALONE_BUILD_PASS', *elfs)
finally:
    vitis.dispose()
