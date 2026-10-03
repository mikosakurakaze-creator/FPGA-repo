"""Generate and build a PL-only simulation of the actual V1.2 SmartConnect RTL.

Never rewrites the exported IPs, project or a previous experiment directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path('E:/HLS/kv260_three_module_v1_2_phase4')
HERE = Path(__file__).resolve().parent
VIVADO = Path('E:/Xilinx/2025.2/Vivado')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    assert args.name.replace('_', '').replace('-', '').isalnum()
    assert (ROOT / 'synthesis_gate.txt').read_text().strip() == 'PASS'
    out = ROOT / args.name
    out.mkdir(exist_ok=False)
    manifest = json.loads((ROOT / 'pl_wrapper_manifest.json').read_text())
    ports = manifest['external_ports']
    buf = json.loads((ROOT / 'buffer_map.json').read_text())
    regions = buf['regions']
    declarations = []
    control_init = []
    for name, spec in ports.items():
        if name in ('ap_clk', 'ap_rst_n'):
            continue
        kind = 'reg' if name.startswith('ctrl_') and spec['direction'] == 'input' else 'wire'
        width = '' if spec['width'] == 1 else f'[{spec["width"]-1}:0] '
        declarations.append(f'{kind} {width}{name};')
        if kind == 'reg':
            value = {'ARSIZE': 2, 'AWSIZE': 2, 'ARBURST': 1, 'AWBURST': 1, 'WLAST': 1}.get(name[5:], 0)
            control_init.append(f'{name}={value};')
    # The actual HP boundary is 128 bits, even though HLS masters are 32 bits.
    signals = {'araddr':49, 'arlen':8, 'arsize':3, 'arburst':2, 'arid':6,
               'arvalid':1, 'arready':1, 'rdata':128, 'rid':6, 'rlast':1,
               'rvalid':1, 'rready':1, 'rresp':2, 'awaddr':49, 'awlen':8,
               'awsize':3, 'awburst':2, 'awid':6, 'awvalid':1, 'awready':1,
               'wdata':128, 'wstrb':16, 'wlast':1, 'wvalid':1, 'wready':1,
               'bid':6, 'bvalid':1, 'bready':1, 'bresp':2}
    responses = {'arready', 'awready', 'rdata', 'rid', 'rlast', 'rvalid', 'rresp',
                 'wready', 'bid', 'bvalid', 'bresp'}
    aliases = []
    for sig, width in signals.items():
        declarations.append(f'wire [3:0] ddr_{sig};' if width == 1 else f'wire [{width-1}:0] ddr_{sig}[0:3];')
        for hp in range(4):
            port = f'hp{hp}_{sig.upper()}'
            if sig in responses:
                if port in ports:
                    aliases.append(f'assign {port}=ddr_{sig}[{hp}];')
            else:
                assert port in ports, port
                aliases.append(f'assign ddr_{sig}[{hp}]={port};')
    ddr_connect = ','.join(['.clk(ap_clk)', '.rst_n(ap_rst_n)']+[f'.{s}(ddr_{s})' for s in signals])
    aliases.append(f"shared_axi_ddr #(.WORDS({buf['memory_words128']}),.BASE(49'h{buf['ddr_base']:x})) ddr({ddr_connect});")
    const = [f"localparam longint DDR_BASE=64'h{buf['ddr_base']:x};",
             f'localparam integer REGION_COUNT={len(regions)};',
             'longint region_base[0:REGION_COUNT-1],region_bytes[0:REGION_COUNT-1];']
    names = list(regions)
    for name in names[:5]:
        const.append(f'localparam integer R_{name.upper()}={names.index(name)};')
    for name in ('cnn_input', 'a_low', 'a_full', 'model_input', 'enhanced'):
        const.append(f"localparam integer R_{name.upper()}[0:1]='{{{names.index(name+'0')},{names.index(name+'1')}}};")
    region_init = [f"region_base[{i}]=64'h{r['base']:x};region_bytes[{i}]={r['bytes']};"
                   for i, r in enumerate(regions.values())]
    content = (HERE / 'system_tb.sv.in').read_text()
    substitutions = {'DECLARATIONS': '\n  '.join(declarations),
                     'DUT_CONNECTIONS': ','.join(f'.{p}({p})' for p in ports),
                     'DDR_CONNECTIONS':'\n  '.join(aliases), 'BUFFER_CONSTANTS':'\n  '.join(const),
                     'REGION_INIT':'\n    '.join(region_init), 'CONTROL_INIT':'\n    '.join(control_init)}
    for key, value in substitutions.items():
        content = content.replace('@'+key+'@', value)
    assert '@' not in content.replace('@(', '').replace('@*', '')
    (out / 'system_tb.sv').write_text(content)
    for source in (ROOT / 'phase4_pl.v', HERE / 'shared_axi_ddr.sv'):
        shutil.copy2(source, out / source.name)
    project = []
    includes = set()
    libraries = set()
    sources = []
    omitted = []
    memory_files = []
    for line in (ROOT / 'simulation_files.tsv').read_text().splitlines():
        filename, kind, library = line.split('\t')
        source = Path(filename)
        if kind == 'Verilog Header':
            includes.add(source.parent.as_posix())
            continue
        if kind == 'Memory Initialization Files':
            memory_files.append(source)
            continue
        if library in ('axi_vip_v1_1_22', 'zynq_ultra_ps_e_vip_v1_0_22') or 'zynq_ultra_ps_e' in source.name or source.name in ('system.v', 'system_wrapper.v'):
            omitted.append(filename)
            continue
        language = {'Verilog':'verilog', 'SystemVerilog':'sv', 'VHDL':'vhdl'}[kind]
        project.append(f'{language} {library} "{source.as_posix()}"')
        libraries.add(library)
        sources.append({'path':filename, 'sha256':sha(source)})
        includes.add(source.parent.as_posix())
    # Also collect ROM data referenced by exported HLS Verilog.
    for sub in (ROOT / 'ip_repo').iterdir():
        memory_files.extend(sub.rglob('*.dat'))
    copied = {}
    for source in memory_files:
        if source.name in copied:
            assert copied[source.name] == sha(source), source
        else:
            shutil.copy2(source, out / source.name)
            copied[source.name] = sha(source)
    glbl = VIVADO / 'data/verilog/src/glbl.v'
    project.append(f'verilog xil_defaultlib "{glbl.as_posix()}"')
    for name, language in [('phase4_pl.v','verilog'), ('shared_axi_ddr.sv','sv'), ('system_tb.sv','sv')]:
        project.append(f'{language} xil_defaultlib "{(out/name).as_posix()}"')
    (out / 'system.prj').write_text('\n'.join(project)+'\n')
    for name in ('shared_ddr.hex', 'golden_low.hex', 'golden_full.hex', 'golden_enhanced.hex'):
        shutil.copy2(ROOT / name, out / name)
    flags = '\n'.join(f'-i "{p}"' for p in sorted(includes))
    libs = '\n'.join('-L '+lib for lib in sorted(libraries | {'unisims_ver','unimacro_ver','secureip','xpm'}))
    (out / 'xelab_options.txt').write_text(flags+'\n'+libs+'\n')
    cmd = ('@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
           'call "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n'
           f'cd /d "{out}"\n'
           'call xelab --relax --mt 2 -prj system.prj -f xelab_options.txt '
           'xil_defaultlib.phase4_system_tb xil_defaultlib.glbl -s phase4_system -log elaborate.log\n'
           'exit /b %errorlevel%\n')
    (out / 'build.cmd').write_text(cmd)
    (out / 'run.tcl').write_text('run all\nquit\n')
    (out / 'source_manifest.json').write_text(json.dumps({'source_files':sources, 'omitted_ps_sources':omitted,
            'rom_data':copied, 'generated_tb_sha256':sha(out/'system_tb.sv'),
            'pl_wrapper_sha256':sha(out/'phase4_pl.v'), 'ddr_model_sha256':sha(out/'shared_axi_ddr.sv'),
            'optimization':'Vivado 2025.2 xelab default enabled; no debug or wave logging'}, indent=2))
    print(f'Prepared {out}: {len(sources)} unchanged PL RTL sources, {len(copied)} ROM files, {len(ports)} ports.')


if __name__ == '__main__':
    main()
