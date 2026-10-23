"""Build a simulation boundary from the exact parent wiring of a routed system.

Retain weather, both data SmartConnects, control SmartConnect and reset verbatim.
Replace the PS hard block by stimulus/memory and hold other PL masters idle.
"""
from pathlib import Path
import re


def build_physical_path(source, target, interface):
    text = Path(source).read_text()
    modules = {m[1]: m[0] for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule', text, re.S)}
    parent = modules['system']
    parent = re.sub(r'\(\*.*?\*\)', '', parent, flags=re.S)
    wire_lines = re.findall(r'^\s*wire\s+[^;]+;', parent, re.M)
    wires = {}
    for line in wire_lines:
        match = re.fullmatch(r'\s*wire\s+(\[\d+:\d+\])?\s*(\\\S+|\w+)\s*;', line)
        if not match:
            raise RuntimeError('Unparsed parent wire: ' + line)
        width, name = match.groups()
        wires[name] = tuple(map(int, width.strip('[]').split(':'))) if width else None

    def instance(name):
        match = re.search(r'^\s*(\w+)\s+' + re.escape(name) + r'\s*\((.*?)\);', parent, re.M | re.S)
        if not match:
            raise RuntimeError('Missing physical instance: ' + name)
        ports = dict(re.findall(r'\.(\\\S+|\w+)\s*\(([^()]*)\)', match[2]))
        return match[1], ports, match[0]

    names = ('weather_frame_top_0', 'cnn_data_sc', 'curve_ddr_sc', 'rst_ps_100m', 'axi_control')
    actual = {name: instance(name) for name in names}
    _, ps, _ = instance('zynq_ultra_ps_e_0')
    ps_module = instance('zynq_ultra_ps_e_0')[0]
    ps_body = re.sub(r'\(\*.*?\*\)', '', modules[ps_module], flags=re.S)
    ps_declarations = {name: (direction, width or '') for direction, width, name in re.findall(
        r'^\s*(input|output)\s+(\[\d+:\d+\])?\s*(\w+)\s*;', ps_body, re.M)}

    def ps_field(name):
        if name.startswith('s_axi_CTRL_'):
            return 'maxigp0_' + name[len('s_axi_CTRL_'):].lower()
        if name.startswith('m_axi_gmem_'):
            bundle, field = name[len('m_axi_gmem_'):].split('_', 1)
            return 'saxigp' + ('2' if bundle == 'in' else '5') + '_' + field.lower()
        return None

    # The PS HPM control bus is not necessarily 32 bits. Preserve its actual
    # lane and ID widths too, not just the HP memory data width.
    for name, (direction, _) in list(interface.items()):
        field = ps_field(name)
        if field in ps:
            ps_direction, width = ps_declarations[field]
            if direction == ps_direction:
                raise RuntimeError('PS boundary direction mismatch: ' + name)
            interface[name] = (direction, width)
    clock = actual['weather_frame_top_0'][1]['ap_clk']
    if any(actual[name][1]['aclk'] != clock for name in ('cnn_data_sc', 'curve_ddr_sc', 'axi_control')):
        raise RuntimeError('Unexpected PL interconnect clock domain')
    if any(ps[name] != clock for name in ('maxihpm0_fpd_aclk', 'saxihp0_fpd_aclk', 'saxihp3_fpd_aclk')):
        raise RuntimeError('Unexpected PS AXI clock domain')
    if re.search(r'^\s*assign\b', parent, re.M):
        raise RuntimeError('Parent assignments need explicit inclusion before replay')
    statements, adaptation = [], []

    def bit_name(name, bit):
        return name + (' ' if name.startswith('\\') else '') + '[' + str(bit) + ']'

    def bits(expression):
        expression = expression.strip()
        if expression.startswith('{') and expression.endswith('}'):
            return [bit for part in expression[1:-1].split(',') for bit in bits(part)]
        if re.fullmatch(r"1'b[01]", expression):
            return [None]
        if expression in wires:
            width = wires[expression]
            return [expression + (' ' if expression.startswith('\\') else '')] if width is None else [
                bit_name(expression, index) for index in range(width[0], width[1]-1, -1)]
        match = re.fullmatch(r'(.+?)\[(\d+)(?::(\d+))?\]', expression)
        if match and match[1] in wires:
            hi, lo = int(match[2]), int(match[3] or match[2])
            return [bit_name(match[1], index) for index in range(hi, lo-1, -1)]
        raise RuntimeError('Unparsed physical expression: ' + expression)

    def drive(expression, source_signal, reason):
        targets = bits(expression)
        signal = 'stimulus_' + str(len(adaptation))
        statements.append('wire [' + str(len(targets)-1) + ':0] ' + signal + ';')
        statements.append('assign ' + signal + '=' + source_signal + ';')
        for index, destination in enumerate(reversed(targets)):
            if destination is not None:
                statements.append('assign ' + destination + '=' + signal + '[' + str(index) + '];')
        adaptation.append({'target': expression, 'source': source_signal, 'reason': reason})

    drive(actual['weather_frame_top_0'][1]['ap_clk'], 'ap_clk', 'PS PL0 clock replaced by 100MHz stimulus')
    drive(actual['rst_ps_100m'][1]['ext_reset_in'], 'ap_rst_n', 'PS PL reset replaced by stimulus')
    used = set()
    for name, (direction, width) in interface.items():
        if name in ('ap_clk', 'ap_rst_n'):
            continue
        if name == 'interrupt':
            statements.append("assign interrupt=1'b0;")
            continue
        ps_name = ps_field(name)
        if ps_name is None:
            raise RuntimeError('Unknown diagnostic interface port: ' + name)
        if ps_name not in ps:
            if direction == 'output':
                statements.append("assign " + name + "=0;")
            adaptation.append({'target': name, 'reason': 'legacy HLS field absent at actual PS interface'})
            continue
        expression = ps[ps_name]
        used.add(ps_name)
        if direction == 'input':
            drive(expression, name, 'PS hard block response/stimulus replaced')
        else:
            statements.append('assign ' + name + '=' + expression + ';')
    for field in ('arlen', 'awlen', 'arid', 'awid', 'arburst', 'awburst', 'arsize', 'awsize', 'wlast'):
        ps_name = 'maxigp0_' + field
        if ps_name in used:
            raise RuntimeError('Duplicate PS control stimulus')
        value = "1" if field in ('arburst', 'awburst', 'wlast') else "2" if field in ('arsize', 'awsize') else "0"
        drive(ps[ps_name], value, 'single-beat 32-bit PS control transaction')
    for name in ('cnn_data_sc', 'curve_ddr_sc'):
        module, ports, _ = actual[name]
        module_body = re.sub(r'\(\*.*?\*\)', '', modules[module], flags=re.S)
        for direction, port in re.findall(r'^\s*(input|output)\s+(?:\[\d+:\d+\])?\s*(\w+)\s*;', module_body, re.M):
            if direction == 'input' and re.fullmatch(r'S0[012]_AXI_\w+', port):
                drive(ports[port], "-1" if port.endswith(('rready', 'bready')) else "0", 'other PL masters held idle')
    module, ports, _ = actual['axi_control']
    module_body = re.sub(r'\(\*.*?\*\)', '', modules[module], flags=re.S)
    for direction, port in re.findall(r'^\s*(input|output)\s+(?:\[\d+:\d+\])?\s*(\w+)\s*;', module_body, re.M):
        if direction == 'input' and re.fullmatch(r'M0[012]_AXI_\w+', port):
            # These targets are never addressed in this fixture. Model their
            # responses explicitly; floating VALID/READY can poison arbitration.
            drive(ports[port], '0', 'unaddressed low-light control targets held idle')
    declarations = '\n'.join(direction + ' ' + width + ' ' + name + ';' for name, (direction, width) in interface.items())
    shim = ('module diagnostic_weather_path(' + ','.join(interface) + ');\n' + declarations
            + '\n' + '\n'.join(wire_lines) + '\n' + '\n'.join(statements)
            + '\n' + '\n'.join(value[2] for value in actual.values()) + '\nendmodule\n')
    # Keep the original export intact: protected SmartConnect module bodies
    # live outside plaintext module/endmodule blocks and must not be stripped.
    Path(target).write_text('`timescale 1 ps / 1 ps\n' + shim + '\n' + text)
    return {'retained_instances': list(names), 'plaintext_modules_in_original_export': len(modules), 'includes_glbl': 'glbl' in modules,
            'ps_boundary_interface': interface,
            'adaptations': adaptation, 'scope': 'actual parent wiring; PS replaced; other PL masters idle; no SDF'}
