"""Test an explicitly counterfactual feature-saturation explanation of a fixture.

This does not observe board internals or establish a hardware root cause.
The unchanged exported-RTL trace must first reproduce the supplied Golden.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signed(value):
    return value - 65536 if value & 32768 else value


def rne(value, shift):
    quotient, remainder = divmod(abs(value), 1 << shift)
    half = 1 << (shift - 1)
    quotient += int(remainder > half or remainder == half and quotient & 1)
    return -quotient if value < 0 else quotient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--params', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = ('input_q14_nchw_8x8.bin', 'expected_q14_nchw_8x8.bin', 'weather_smoke_frame_0_q14.bin')
    fixture = args.fixture
    manifest = json.loads((fixture / 'manifest.json').read_text())
    for name in names:
        if sha(fixture / name) != manifest[name]['sha256'] or (fixture / name).stat().st_size != 384:
            raise RuntimeError('Fixture identity failed: ' + name)
    arrays = [struct.unpack('<192h', (fixture / name).read_bytes()) for name in names]
    input_values, golden, board = arrays
    match = re.search(r'\{8,3,1,1,0,12,14,\{9,9,9\},\{([^}]+)\},\{([^}]+)\}', args.params.read_text())
    if not match:
        raise RuntimeError('Require the actual task0 tail parameters; no default weights')
    weights, biases = [list(map(int, part.split(','))) for part in match.groups()]
    if len(weights) != 24 or len(biases) != 3:
        raise RuntimeError('Unexpected tail shape')
    by_frame = {}
    for line in args.trace.read_text().splitlines():
        frame, packet = line.split()
        if len(packet) != 44 or not re.fullmatch('[0-9a-fA-F]+', packet):
            raise RuntimeError('Require known-valued, complete 176-bit packets')
        value = int(packet, 16)
        by_frame.setdefault(int(frame), []).append([signed(value >> (16*c) & 65535) for c in range(11)])
    if sorted(by_frame) != [0, 1] or any(len(values) != 64 for values in by_frame.values()):
        raise RuntimeError('Require two complete 8x8 task0 exported-RTL traces')

    def tail(packet, channel):
        accumulator = biases[channel] + sum(weights[8*channel+c] * packet[c] for c in range(8))
        residual = max(-32768, min(32767, rne(accumulator, 7)))
        return max(0, min(16384, packet[8+channel] + residual))

    frames = []
    for frame, packets in sorted(by_frame.items()):
        original = [tail(packets[pixel], channel) for channel in range(3) for pixel in range(64)]
        if original != list(golden):
            raise RuntimeError('Unmodified trace/tail does not reproduce Golden')
        if any(packets[pixel][8+channel] != input_values[channel*64+pixel]
               for channel in range(3) for pixel in range(64)):
            raise RuntimeError('Exported-RTL RGB does not match original input')
        # The spatial mask is an observed final-output pattern, not an internal
        # signal recovered from the board. Keep this distinction in the report.
        affected = [pixel for pixel in range(64)
                    if any(board[channel*64+pixel] != golden[channel*64+pixel] for channel in range(3))]
        candidates = []
        for feature in range(8):
            changed = [packet.copy() for packet in packets]
            for pixel in affected:
                changed[pixel][feature] = 32767
            predicted = [tail(changed[pixel], channel) for channel in range(3) for pixel in range(64)]
            data = struct.pack('<192h', *predicted)
            candidates.append({'feature_zero_based': feature,
                               'board_mismatch': sum(a != b for a, b in zip(predicted, board)),
                               'predicted_sha256': hashlib.sha256(data).hexdigest()})
        frames.append({'frame': frame, 'unmodified_golden_mismatch': 0,
                       'unmodified_board_mismatch': sum(a != b for a, b in zip(original, board)),
                       'affected_pixels': len(affected), 'candidate_saturation_value': 32767,
                       'counterfactual_results': candidates,
                       'affected_pixel_indices': affected,
                       'feature2_original_range_at_affected_pixels':
                           [min(packets[i][2] for i in affected), max(packets[i][2] for i in affected)]})
    report = {'schema_version': 1,
              'classification': 'COUNTERFACTUAL_SIGNATURE_NOT_CONFIRMED_ROOT_CAUSE',
              'scope': 'exact task0 8x8 fixture; exported-RTL stage5 packets; unchanged task0 integer tail',
              'limitation': 'mask is derived from final mismatch locations; no internal board observation; other fault mechanisms are possible',
              'fixture_sha256': {name: sha(fixture / name) for name in names},
              'trace_sha256': sha(args.trace), 'params_sha256': sha(args.params),
              'tool_sha256': sha(Path(__file__)), 'tail_weights': weights, 'tail_biases': biases,
              'frames': frames}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise RuntimeError('Refuse to overwrite analysis evidence')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'classification': report['classification'], 'frames': frames}, indent=2))


if __name__ == '__main__':
    main()
