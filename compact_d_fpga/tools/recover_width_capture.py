"""Compare completed active-frame captures from the interrupted large RTL run."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, default=Path('D:/weather_builds/compact_d_cosim_large01'))
    p.add_argument('--golden', type=Path, default=Path('D:/weather_builds/compact_d_large_vectors01/random_17x1280'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    capture = a.build/'component/hls/sim/tv/rtldatafile/rtl.compact_d_top.autotvout_gmem_out.dat'
    raw = capture.read_bytes()
    golden = (a.golden/'21_output.relu.i16').read_bytes()
    report = json.loads((a.golden/'report.json').read_text())
    log_file = a.build/'component/hls/sim/verilog/xsim.log'
    log = log_file.read_text(errors='replace')
    if '// RTL Simulation : 2 / 7' not in log:
        raise RuntimeError('Two completed RTL transactions absent')
    frames = []
    cursor = 0
    for seq in range(2):
        # Vitis 2025.2's Byte<2> TV format: big-endian 32-bit high/depth
        # header followed by big-endian 16-bit memory scalars.
        high, depth = (int.from_bytes(raw[cursor+i:cursor+i+4], 'big') for i in (0, 4))
        if high != 0 or depth != 2764800:
            raise RuntimeError('Unexpected vendor TV header')
        active = raw[cursor+8:cursor+8+len(golden)]
        if len(active) != len(golden):
            raise RuntimeError('Incomplete active frame')
        little = bytearray(len(active))
        little[0::2], little[1::2] = active[1::2], active[0::2]
        if little != golden:
            raise RuntimeError('Maximum-width RTL output differs from A')
        (a.out/f'actual_{seq}.i16').write_bytes(little)
        frames.append(dict(seq=seq, shape=report['shape'], bytes=len(little), sha256=sha(little), exact=True))
        if seq == 0:
            tail = raw[cursor+8+len(golden):cursor+8+2*depth]
            if len(tail) != 2*depth-len(golden) or tail != b'\x30\x39'*(len(tail)//2):
                raise RuntimeError('First-frame guard region changed or incomplete')
        cursor += 8+2*depth
    result = dict(pass_result=True, scope='active output of two completed 17x1280 RTL transactions; first-frame full guard region',
                  suite_completed=False, full720p_rtl_executed=False,
                  limitation='Interrupted seven-transaction vendor run; return/counter files were not flushed, second guard region incomplete. No whole-suite PASS is inferred.',
                  frames=frames, capture_sha256=sha(raw), xsim_log_sha256=sha(log_file.read_bytes()),
                  golden_report_sha256=sha((a.golden/'report.json').read_bytes()), bundle_id=report['bundle_id'])
    (a.out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print('D_MAX_WIDTH_ACTIVE_OUTPUTS_EXACT frames=2; full suite remains incomplete')


if __name__ == '__main__':
    main()
