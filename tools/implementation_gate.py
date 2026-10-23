"""Validate the exact routed-system numerical replay before collecting a release.

This fixed regression covers 8x8 task0 cold/warm, task1, then task0 without
reset. It does not certify the physical PS/DDR, SDF timing, or video throughput.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hex_frame(path):
    tokens = path.read_text().split()
    if len(tokens) != 192 or any(not re.fullmatch('[0-9a-fA-F]{4}', t) for t in tokens):
        raise RuntimeError('Incomplete/unknown 8x8 frame: ' + str(path))
    return struct.pack('<192H', *(int(t, 16) for t in tokens))


def validate_replay(report_path, netlist_sha256):
    report_path = Path(report_path)
    folder = report_path.parent
    report = json.loads(report_path.read_text())
    frames = report.get('frames', [])
    if (not report.get('completed') or not report.get('pass')
            or report.get('kind') != 'post_route_functional'
            or report.get('full_system_netlist_sha256') != netlist_sha256
            or [(f.get('seq'), f.get('task')) for f in frames] != [(0, 0), (1, 0), (2, 1), (3, 0)]
            or any(f.get('golden_mismatch') != 0 for f in frames)):
        raise RuntimeError('Exact routed-system four-frame numerical replay absent/failed')
    fixtures = report['fixture_sha256']
    expected_task0 = fixtures['expected_q14_nchw_8x8.bin']
    expected_input0 = fixtures['input_q14_nchw_8x8.bin']
    for frame in frames:
        seq = frame['seq']
        data = (folder / f'actual_{seq}.bin').read_bytes()
        golden = hex_frame(folder / f'golden_{seq}.hex')
        input_data = hex_frame(folder / f'input_{seq}.hex')
        if len(data) != 384 or data != golden or hashlib.sha256(data).hexdigest() != frame['sha256']:
            raise RuntimeError('Replay output/Golden bytes disagree: ' + str(seq))
        if frame['task'] == 0 and (hashlib.sha256(data).hexdigest() != expected_task0
                or hashlib.sha256(input_data).hexdigest() != expected_input0):
            raise RuntimeError('Task0 replay differs from immutable fixture')
    extra = report['additional_task1_vectors']
    for source, staged in [('input_1.hex', 'input_2.hex'), ('golden_1.hex', 'golden_2.hex')]:
        if sha(folder / staged) != extra[source]:
            raise RuntimeError('Task1 staged vector identity differs')
    snapshots = report.get('executed_source_sha256', {})
    required = {'run_board_repro.py', 'diagnostic_boundary.py', 'physical_system_repro.py', 'rtl_memory_test.sv'}
    if set(snapshots) != required:
        raise RuntimeError('Executed replay source snapshots incomplete')
    for name, expected in snapshots.items():
        if sha(folder / 'executed_sources' / name) != expected:
            raise RuntimeError('Executed replay source differs: ' + name)
    if snapshots['run_board_repro.py'] != report['runner_sha256'] or snapshots['rtl_memory_test.sv'] != report['template_sha256']:
        raise RuntimeError('Runner/template snapshot identity differs')
    for name, expected in report['helper_sha256'].items():
        if snapshots.get(name) != expected:
            raise RuntimeError('Replay helper snapshot identity differs')
    if sha(folder / 'weather_rtl_test.sv') != report['testbench_sha256']:
        raise RuntimeError('Executed testbench differs')
    log_path = folder / 'simulation.log'
    log = log_path.read_text(errors='replace')
    if sha(log_path) != report['simulation_log_sha256'] or 'BOARD_REPRO_COMPLETED frames=4' not in log or 'Fatal:' in log:
        raise RuntimeError('Replay completion log differs/failed')
    observed = re.findall(r'WEATHER_AXI_FRAME_COMPLETED case=(\d+) task=(\d+) shape=8x8 cycles=(\d+)', log)
    if [(int(seq), int(task)) for seq, task, _ in observed] != [(0, 0), (1, 0), (2, 1), (3, 0)]:
        raise RuntimeError('Replay log task/frame sequence incomplete')
    return {'pass': True, 'report_sha256': sha(report_path),
            'full_system_netlist_sha256': netlist_sha256,
            'frames': frames, 'cycles': [int(cycles) for _, _, cycles in observed],
            'scope': report['scope']}


def copy_replay(report_path, destination):
    source = Path(report_path).parent
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('run.json', 'simulation.log', 'weather_rtl_test.sv', 'ddr_transactions.txt'):
        shutil.copy2(source / name, destination / name)
    for seq in range(4):
        for name in (f'actual_{seq}.bin', f'input_{seq}.hex', f'golden_{seq}.hex'):
            shutil.copy2(source / name, destination / name)
    shutil.copytree(source / 'executed_sources', destination / 'executed_sources')
