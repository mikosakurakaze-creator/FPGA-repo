"""Controlled netlist experiment: restore one receiver's synthesized C input.

This edits a NEW simulation file only. It is not a bitstream fix or a substitute
for checkpoint correction, implementation, timing checks, and board validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


MODULE = ('system_weather_frame_top_0_0_weather_frame_top_'
          'mac_muladd_15ns_7s_22s_23_4_1_DSP48_0_84')
SOURCE_SHA = '587cdf289bfbd886a20857f0d30e70a3da15303837414d020345e9841035cbb8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    raw = args.netlist.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Require the exact original routed export')
    if args.output.exists():
        raise RuntimeError('Refuse to replace diagnostic evidence')
    text = raw.decode()
    module = re.search(r'\bmodule\s+' + MODULE + r'\b.*?\bendmodule', text, re.S)
    if module is None:
        raise RuntimeError('Receiver module absent')
    body = module[0]
    if body.count('DSP48E2 #(') != 1 or 'IS_OPMODE_INVERTED' in body:
        raise RuntimeError('Receiver primitive differs from audited fixture')
    changes = {}
    replacements = {'C': "{{26{DSP_ALU_INST[21]}},DSP_ALU_INST}",
                    'PCIN': "48'b0", 'OPMODE': "9'b000110101"}
    for port, replacement in replacements.items():
        pattern = r'\.' + port + r'\(([^()]*)\)'
        matches = list(re.finditer(pattern, body))
        if len(matches) != 1:
            raise RuntimeError('Ambiguous receiver port: ' + port)
        original = matches[0][1]
        if port == 'C' and original.replace(' ', '') != '{' + ','.join(["1'b1"] * 48) + '}':
            raise RuntimeError('Original C is not the expected inactive constant')
        if port == 'OPMODE' and original.replace(' ', '') != "{1'b0,1'b0,1'b0,1'b0,1'b1,1'b0,1'b1,1'b0,1'b1}":
            raise RuntimeError('Original OPMODE is not M+PCIN')
        if port == 'PCIN' and not original.endswith(',DSP_ALU_INST}'):
            raise RuntimeError('Unexpected cascade input')
        changes[port] = {'before': original, 'after': replacement}
        body = re.sub(pattern, lambda _: '.' + port + '(' + replacement + ')', body)
    result = text[:module.start()] + body + text[module.end():]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', newline='') as stream:
        stream.write(result)
    report = {'kind': 'diagnostic_modified_functional', 'source_sha256': SOURCE_SHA,
              'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
              'module': MODULE, 'changed_ports': changes,
              'scope': 'simulation intervention only; no checkpoint/bit/board modification'}
    args.output.with_suffix('.patch.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
