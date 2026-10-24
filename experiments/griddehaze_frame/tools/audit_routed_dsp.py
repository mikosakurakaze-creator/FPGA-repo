"""Check stable binary OPMODE combinations for actual DPREG-7 routed cells.

This is a limited combinational proof, not a timing or physical-glitch proof.
Repeated appearances of the same net bit are correlated, never independent.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--netlist', type=Path, required=True)
    p.add_argument('--drc', type=Path, required=True)
    p.add_argument('--unisim', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    text = a.netlist.read_text()
    modules = {m[1]: m[0] for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule', text, re.S)}
    drc = a.drc.read_text()
    paths = re.findall(r'DPREG-7#\d+ Warning\s+DSP48E2_PregDynOpmodeZmuxP:\s+The DSP48E2 cell (\S+)', drc)
    expected = int(re.search(r'^\|\s*DPREG-7\s*\|.*?\|\s*(\d+)\s*\|$', drc, re.M)[1])
    if not paths or len(paths) != expected:
        raise RuntimeError('DRC detail/summary count mismatch')
    # These selectors are taken from the installed model, whose hash is saved.
    model = a.unisim.read_text()
    for pattern in (r"2'b01\s*:\s*wmux\s*=\s*P_FDBK_in", r"2'b10\s*:\s*xmux\s*=\s*P_FDBK_in",
                    r"3'b010\s*:\s*zmux\s*=\s*P_FDBK_in", r"3'b100\s*:\s*zmux\s*=\s*P_FDBK_in",
                    r"3'b11x\s*:\s*zmux\s*=.*P_FDBK_in"):
        if not re.search(pattern, model):
            raise RuntimeError('Unsupported DSP model selector table')
    results = []
    for path in paths:
        parts = path.split('/')
        if parts.pop(0) != 'system_i':
            raise RuntimeError('Unexpected top hierarchy: ' + path)
        module = 'system'  # write_verilog retains this physical parent.
        for instance in parts[:-1]:
            match = re.search(r'^\s*(\w+)\s+' + re.escape(instance) + r'\s*\(', modules[module], re.M)
            if not match:
                raise RuntimeError('Cannot resolve actual instance: ' + path)
            module = match[1]
        # Bound the parameter block; do not cross an earlier primitive while
        # searching for a later named cell in the same module.
        dsp = re.search(r'\bDSP48E2\s*#\(((?:[^()]|\([^()]*\))*)\)\s*'
                        + re.escape(parts[-1]) + r'\s*\((.*?)\);', modules[module], re.S)
        if dsp is None:
            raise RuntimeError('Cannot resolve exact DSP primitive: ' + path)
        # Vivado omits parameters that equal the primitive default.  The
        # installed DSP48E2 model defines IS_OPMODE_INVERTED=9'b000000000,
        # so an omitted assignment is an explicit all-zero inversion mask.
        inversion_match = re.search(r"\.IS_OPMODE_INVERTED\(9'b([01]{9})\)", dsp[1])
        inversion = int(inversion_match[1], 2) if inversion_match else 0
        preg = int(re.search(r'\.PREG\(([01])\)', dsp[1])[1])
        expression = re.search(r'\.OPMODE\(([^()]*)\)', dsp[2])[1]
        bits = [bit.strip() for bit in expression.strip('{}').split(',')]
        # write_verilog may escape hierarchical net names (for example
        # ``\\cond..._[0]``).  Treat every comma-delimited non-literal token
        # as one binary selector; the audit varies each distinct selector.
        if len(bits) != 9 or any(not re.fullmatch(r"1'b[01]|[^,{}\s]+", bit) for bit in bits):
            raise RuntimeError('Unsupported OPMODE expression: ' + expression)
        symbols = sorted(set(bit for bit in bits if not re.fullmatch(r"1'b[01]", bit)))
        modes = []
        for combination in itertools.product((0, 1), repeat=len(symbols)):
            values = dict(zip(symbols, combination))
            value = 0
            for bit in bits:
                value = value * 2 + (int(bit[-1]) if re.fullmatch(r"1'b[01]", bit) else values[bit])
            modes.append(value ^ inversion)
        feedback = [value for value in modes if value >> 7 == 1 or value & 3 == 2 or value >> 4 & 7 in (2, 4, 6, 7)]
        results.append({'cell': path, 'preg': preg, 'opmode_expression': expression,
                        'inversion': f'{inversion:09b}', 'binary_modes_overapprox': [f'{v:09b}' for v in modes],
                        'p_feedback_modes': [f'{v:09b}' for v in feedback]})
    report = {'scope': 'stable binary input combinations at 19 DPREG-7 cells; excludes physical transitions, SDF, and all other DRC classes',
              'pass_no_stable_binary_p_feedback': all(not row['p_feedback_modes'] for row in results),
              'sha256': {'netlist': sha(a.netlist), 'drc': sha(a.drc), 'unisim': sha(a.unisim), 'tool': sha(Path(__file__))},
              'checked_cells': len(results), 'cells': results}
    if a.output.exists():
        raise RuntimeError('Refuse to overwrite audit evidence')
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'cells'}, indent=2))
    return 0 if report['pass_no_stable_binary_p_feedback'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
