"""Compare recorded actual 168-bit FIFO ports to full 176-bit RTL packets.

Only compare representable, nonnegative feature lanes. Never invent deleted
sign bits. This fixed-fixture diagnostic checks frame0, six stages, 64 pixels.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--physical', required=True, type=Path)
    p.add_argument('--rtl', required=True, type=Path)
    p.add_argument('--physical-run', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.output.exists():
        raise RuntimeError('Refuse to replace evidence')
    origin = json.loads((a.physical / 'origin.json').read_text())
    run = json.loads(a.physical_run.read_text())
    if (not run['completed'] or len(run['frames']) != 2
            or any(f.get('board_mismatch') != 0 for f in run['frames'])
            or origin['origin_netlist_sha256'] != run['netlist_sha256']
            or origin['origin_testbench_sha256'] != run['testbench_sha256']):
        raise RuntimeError('Snapshot/run identity or board replay check failed')
    reports = []
    hashes = {'physical_run': sha(a.physical_run), 'origin': sha(a.physical / 'origin.json')}
    for stage in range(6):
        physical_file = a.physical / f'physical_stage_{stage}.txt'
        rtl_file = a.rtl / f'stage_{stage}.txt'
        actual_rows = [line.split() for line in physical_file.read_text().splitlines()]
        reference_rows = [line.split() for line in rtl_file.read_text().splitlines()
                          if line.split() and int(line.split()[0]) == 0]
        if len(actual_rows) != 64 or len(reference_rows) != 64:
            raise RuntimeError('Require exactly 64 packets per stage/frame')
        feature_bad = [0] * 8
        rgb_bad, packets_bad, positions, samples = 0, 0, [], []
        for pixel, (physical, rtl) in enumerate(zip(actual_rows, reference_rows)):
            if len(physical) != 3 or int(physical[0], 16) != 0 or len(rtl) != 2:
                raise RuntimeError('Unexpected trace encoding')
            actual, expected = int(physical[2], 16), int(rtl[1], 16)
            if actual.bit_length() > 168 or expected.bit_length() > 176:
                raise RuntimeError('Trace packet width exceeded')
            features = [(expected >> (16 * lane)) & 65535 for lane in range(8)]
            if any(value > 32767 for value in features):
                raise RuntimeError('RTL sign removal is not lossless at this packet')
            compressed = ((expected >> 128) << 120) | sum(
                value << (15 * lane) for lane, value in enumerate(features))
            if actual != compressed:
                packets_bad += 1
                positions.append([pixel // 8, pixel % 8])
                if len(samples) < 4:
                    samples.append({'pixel': pixel, 'sample': int(physical[1]),
                                    'expected_c2': features[2], 'actual_c2': (actual >> 30) & 32767})
            rgb_bad += (actual >> 120) != (expected >> 128)
            for lane, value in enumerate(features):
                feature_bad[lane] += ((actual >> (15 * lane)) & 32767) != value
        reports.append({'stage': stage, 'packets': 64, 'packet_mismatches': packets_bad,
                        'rgb_packet_mismatches': rgb_bad, 'feature_lane_mismatches': feature_bad,
                        'mismatch_positions_yx': positions, 'examples': samples})
        hashes[f'physical_stage_{stage}'] = sha(physical_file)
        hashes[f'rtl_stage_{stage}'] = sha(rtl_file)
    report = {'scope': 'observed first-frame actual routed FIFO inputs; no SDF/real PS DDR',
              'physical_frame_results': run['frames'], 'origin': origin,
              'sha256': hashes, 'stages': reports}
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'stages'}, indent=2))
    print(json.dumps([{key: value for key, value in stage.items()
                       if key not in ('mismatch_positions_yx', 'examples')} for stage in reports], indent=2))


if __name__ == '__main__':
    main()
