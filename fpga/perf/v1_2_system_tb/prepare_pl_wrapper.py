"""Replace ONLY the PS instance with BFM ports in a copy of real V1.2 RTL.

The actual three HLS modules, five SmartConnect instances, address apertures,
clock/reset wiring and conversion logic remain the generated system network.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[3]
RUN = Path('E:/HLS/kv260_three_module_v1_2_phase4')


def main():
    assert (RUN / 'synthesis_gate.txt').read_text().strip() == 'PASS'
    src = ROOT / 'fpga/vivado/three_module_integration_v1_2/three_module_integration_v1_2.gen/sources_1/bd/system/sim/system.v'
    text = src.read_text()
    ps = re.search(r'\n\s*system_zynq_ultra_ps_e_0_0 zynq_ultra_ps_e_0\s*\((.*?)\);', text, re.S)
    assert ps
    pin_to_net = dict(re.findall(r'\.(\w+)\(([^()]*)\)', ps[1]))
    directions = {}
    widths = {}
    aliases = {}
    constant_outputs = {}
    master_outputs = {'ARADDR','ARBURST','ARCACHE','ARID','ARLEN','ARLOCK','ARPROT','ARQOS','ARSIZE','ARUSER','ARVALID',
                      'AWADDR','AWBURST','AWCACHE','AWID','AWLEN','AWLOCK','AWPROT','AWQOS','AWSIZE','AWUSER','AWVALID',
                      'BREADY','RREADY','WDATA','WLAST','WSTRB','WVALID'}
    response_outputs = {'ARREADY','AWREADY','BID','BRESP','BVALID','RDATA','RID','RLAST','RRESP','RVALID','WREADY'}
    for ps_pin, net in pin_to_net.items():
        if ps_pin in ('pl_clk0', 'pl_resetn0'):
            name = 'ap_clk' if ps_pin == 'pl_clk0' else 'ap_rst_n'
            direction = 'input'
        else:
            m = re.fullmatch(r'(maxigp0|saxigp[2-5])_(\w+)', ps_pin)
            if not m:
                continue
            signal = m[2].upper()
            assert signal in master_outputs | response_outputs, signal
            is_control = m[1] == 'maxigp0'
            name = ('ctrl_' if is_control else 'hp' + str(int(m[1][-1])-2) + '_') + signal
            drive_into_pl = signal in (master_outputs if is_control else response_outputs)
            direction = 'input' if drive_into_pl else 'output'
        wire = re.search(r'^\s*wire\s*(\[[^\]]+\])?\s*' + re.escape(net) + r'\s*;', text, re.M) if net else None
        if wire:
            dimensions = wire[1] or ''
            width = 1 if not dimensions else int(re.search(r'\[(\d+):0\]', dimensions)[1]) + 1
        elif net:
            assert direction == 'output', (ps_pin, net)
            bits = re.findall(r"(\d+)'[bdh][0-9a-fA-Fxz]+", net)
            assert bits, net
            width = sum(map(int,bits))
            constant_outputs[name] = net
        else:
            # Unused PS response pins (for example HP1 write response) have
            # no PL consumer. Externalize them for a uniform DDR BFM only.
            signal = ps_pin.split('_')[-1].upper()
            width = 128 if signal == 'RDATA' else 6 if signal in ('RID','BID') else 2 if signal in ('RRESP','BRESP') else 1
            assert direction == 'input', ps_pin
        directions[name], widths[name], aliases[name] = direction, width, net
    assert {'ap_clk','ap_rst_n'} <= set(directions)
    assert all(widths['hp'+str(i)+'_WDATA'] == 128 for i in range(4))
    assert widths['ctrl_WDATA'] == 128
    declarations = []
    assigns = []
    for name in directions:
        dimension = '' if widths[name] == 1 else f'[{widths[name]-1}:0] '
        declarations.append(f'  {directions[name]} wire {dimension}{name}')
        if aliases[name]:
            assigns.append(f'  assign {aliases[name]} = {name};' if directions[name] == 'input'
                           else f'  assign {name} = {aliases[name]};')
    body = text[:ps.start()] + '\n  // PS replaced by external BFM/DDR ports only in this simulation copy.\n' + text[ps.end():]
    body, count = re.subn(r'\bmodule\s+system\s*\(\s*\);',
                         'module phase4_pl(\n' + ',\n'.join(declarations) + '\n);\n' + '\n'.join(assigns), body, count=1)
    assert count == 1
    (RUN / 'phase4_pl.v').write_text(body)
    evidence = dict(original_system=str(src), original_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
                    pl_copy_sha256=hashlib.sha256((RUN / 'phase4_pl.v').read_bytes()).hexdigest(),
                    removed_instance='zynq_ultra_ps_e_0', ps_pin_to_net=pin_to_net,
                    external_ports={n: dict(direction=directions[n], width=widths[n], original_net=aliases[n]) for n in directions},
                    preserved_constant_outputs=constant_outputs,
                    remaining_generated_network_unchanged=True)
    (RUN / 'pl_wrapper_manifest.json').write_text(json.dumps(evidence, indent=2))
    print('PL-only copy prepared with real SmartConnect network;', len(directions), 'BFM/HP ports.')


if __name__ == '__main__':
    main()
