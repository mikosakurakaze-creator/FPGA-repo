"""Replay a prepared routed-system snapshot and compare four Golden nodes.

This is a deliberately limited numerical sample, not full-network completion.
Tcl only advances simulation and reads signals; it never forces DUT state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8', newline='\n')


def collect(out, golden):
    """Require simulation markers and independently compare captured DDR bytes."""
    meta = json.loads((golden / 'report.json').read_text(encoding='utf-8'))
    log = (out / 'sample.log').read_text(encoding='utf-8', errors='replace')
    if ('GDN_ROUTED_SAMPLE_SEQUENCE_DONE nodes=1,2,3,4' not in log
            or re.search(r'(?m)^(?:Fatal:|ERROR:)', log)):
        raise ValueError('Routed numerical sample did not complete')
    captures = {}
    index = None
    for line in (out / 'sample_words.txt').read_text(encoding='ascii').splitlines():
        if line.startswith('NODE '):
            index = int(line[5:])
            if index in captures:
                raise ValueError('Duplicate node capture')
            captures[index] = bytearray()
        else:
            if index is None or not re.fullmatch('[0-9a-fA-F]{1,8}', line):
                raise ValueError('Unknown or malformed DDR word: ' + line)
            captures[index] += struct.pack('<I', int(line, 16))
    if set(captures) != {1, 2, 3, 4}:
        raise ValueError('Missing routed node captures')
    records = []
    for index, raw in sorted(captures.items()):
        node = meta['nodes'][index]
        reference = golden / 'nodes' / node['file']
        if (len(raw) != node['bytes'] or raw != reference.read_bytes()
                or hashlib.sha256(raw).hexdigest() != node['sha256']):
            raise ValueError('Routed Golden mismatch: ' + node['id'])
        actual = out / ('node_' + str(index) + '.raw')
        actual.write_bytes(raw)
        records.append(dict(index=index, id=node['id'], op=node['op'],
                            scalars=len(raw) // 2, sha256=sha(actual), mismatch=0))
    provenance = json.loads((out / 'sample_provenance.json').read_text(encoding='utf-8'))
    return dict(status='pass', kind='post_route_functional_numerical_samples',
                shape=meta['input_shape'], nodes=records,
                total_scalars=sum(n['scalars'] for n in records),
                provenance=provenance, simulation_log_sha256=sha(out / 'sample.log'),
                capture_sha256=sha(out / 'sample_words.txt'),
                tcl_sha256=sha(out / 'sample.tcl'),
                golden_report_sha256=sha(golden / 'report.json'),
                scope='Actual routed new core and parent reset/control/SmartConnect/DDR boundary; simulated PS DDR; no SDF',
                limitations=['Only nodes 1..4: two convolutions, ReLU, concatenation',
                             'No full-network post-route completion or warm-frame claim',
                             'No deconvolution, coefficient-multiply or addition post-route numerical coverage',
                             'No physical board or DMA-driver validation'])


def prepare(source, out, netlist, golden):
    """Reuse elaboration, retaining the original implemented arithmetic and paths."""
    out.mkdir(parents=True, exist_ok=False)
    compiled = (source / 'core_netlist.v').read_text(encoding='utf-8')
    original = netlist.read_text(encoding='utf-8')
    if not compiled.endswith(original):
        raise ValueError('Prepared netlist does not contain this routed export verbatim')
    test = (source / 'frame_axi_test.sv').read_text(encoding='ascii')
    if '`define GDN_NETLIST' not in test or 'diagnostic_grid_path dut(' not in test:
        raise ValueError('A prepared physical-system testbench is required')
    memory = json.loads((source / 'memory.json').read_text(encoding='utf-8'))
    fixture = json.loads((source / 'ddr_fixture.json').read_text(encoding='utf-8'))
    meta = json.loads((golden / 'report.json').read_text(encoding='utf-8'))
    if meta['input_shape'] != [1, 3, 4, 4] or memory['input_bytes'] != 96:
        raise ValueError('This numerical sample is defined for the frozen 4x4 case')
    shutil.copytree(source / 'xsim.dir', out / 'xsim.dir')
    for file in source.glob('*.hex'):
        shutil.copy2(file, out / file.name)
    lines = ['set core /gdn_frame_axi_test/dut/griddehaze_frame_top_0/inst',
             'set samples [open sample_words.txt w]', 'run 1000ns', 'set loops 0']
    # The graph index advances after retirement. Read each temporary before
    # its scratch slot is reused by the next convolution/ReLU.
    for until, nodes in [(3, [1, 2]), (5, [3, 4])]:
        lines += ['while {1} {',
                  '  set n [get_value -radix unsigned ${core}/i_2_fu_352]',
                  '  if {[string is integer -strict $n] && $n >= ' + str(until) + '} {break}',
                  '  run 1000ns', '  incr loops',
                  '  if {$loops > 4000} {error "sample watchdog: no expected graph progress"}', '}']
        for index in nodes:
            offset = fixture['scratch_at'] + memory['nodes'][index]['offset']
            size = meta['nodes'][index]['bytes']
            if offset % 4 or size % 4:
                raise ValueError('Expected word-aligned sample tensor')
            first, count = offset // 4, size // 4
            lines += ['puts $samples "NODE ' + str(index) + '"',
                      f'for {{set i {first}}} {{$i < {first + count}}} {{incr i}} {{',
                      r'  puts $samples [get_value -radix hex /gdn_frame_axi_test/feature/mem[$i]]',
                      '}', 'flush $samples',
                      f'puts "GDN_ROUTED_SAMPLE_CAPTURE node={index} words={count} graph_node=$n"']
    lines += ['close $samples',
              'puts "GDN_ROUTED_SAMPLE_SEQUENCE_DONE nodes=1,2,3,4"', 'quit']
    (out / 'sample.tcl').write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
    snapshot = source / 'xsim.dir/gdn_frame_axi_test'
    save(out / 'sample_provenance.json', dict(
        source_preparation=str(source), netlist_sha256=sha(netlist),
        compiled_netlist_sha256=sha(source / 'core_netlist.v'),
        compiled_test_sha256=sha(source / 'frame_axi_test.sv'),
        snapshot_sha256={n: sha(snapshot / n) for n in ['xsimk.exe', 'xsim.mem', 'xsim.reloc']},
        nodes=[1, 2, 3, 4],
        method='Exact elaborated routed-system snapshot; only read graph index and simulated DDR; no forcing or arithmetic substitution'))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--golden', type=Path, required=True)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--netlist', type=Path)
    parser.add_argument('--collect-only', action='store_true')
    parser.add_argument('--vivado', type=Path, default=Path('D:/vivado/2025.2/Vivado'))
    args = parser.parse_args()
    out, golden = args.out.resolve(), args.golden.resolve()
    if not args.collect_only:
        if args.prepared is None or args.netlist is None:
            parser.error('--prepared and --netlist are required for execution')
        prepare(args.prepared.resolve(), out, args.netlist.resolve(), golden)
        paths = [str(args.vivado / 'settings64.bat'), str(args.vivado / 'bin/xsim.bat')]
        if any(re.search(r'[\r\n"&|<>^%!]', p) for p in paths):
            raise ValueError('Unsupported batch path')
        command = out / 'sample.cmd'
        command.write_text('@echo off\ncall "' + paths[0] + '"\nif errorlevel 1 exit /b 1\ncall "'
                           + paths[1] + '" gdn_frame_axi_test -tclbatch sample.tcl -log sample.log\n'
                           'exit /b %errorlevel%\n', encoding='ascii', newline='\n')
        start = time.perf_counter()
        with (out / 'launcher.log').open('wb') as log:
            result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(command)],
                                    cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
        if result.returncode:
            raise RuntimeError('Simulator launcher failed; see launcher.log')
        save(out / 'execution.json', dict(seconds=time.perf_counter() - start,
                                          exit_code=result.returncode))
    report = collect(out, golden)
    save(out / 'sample_result.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
