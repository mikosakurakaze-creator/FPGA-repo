"""Compare raw little-endian RGB/NCHW INT16 output without third-party packages."""
import argparse
from pathlib import Path
import struct


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--expected', type=Path, required=True)
    p.add_argument('--actual', type=Path, required=True)
    p.add_argument('--height', type=int, required=True)
    p.add_argument('--width', type=int, required=True)
    a = p.parse_args()
    if not 1 <= a.height <= 720 or not 1 <= a.width <= 1280:
        p.error('Unsupported dimensions')
    count = 3*a.height*a.width
    buffers = [path.read_bytes() for path in [a.expected, a.actual]]
    if any(len(data) != count*2 for data in buffers):
        p.error('Both files must contain exactly 3*H*W little-endian INT16 scalars')
    bad, first, largest = 0, None, 0
    for i, (e, v) in enumerate(zip(struct.iter_unpack('<h', buffers[0]), struct.iter_unpack('<h', buffers[1]))):
        if e[0] != v[0]:
            bad += 1
            largest = max(largest, abs(e[0]-v[0]))
            if first is None:
                c, pixel = divmod(i, a.height*a.width)
                y, x = divmod(pixel, a.width)
                first = dict(channel='RGB'[c], y=y, x=x, expected=e[0], actual=v[0])
    print(f'mismatches={bad}/{count} max_integer_error={largest}')
    if first is not None:
        print('first_mismatch='+str(first))
        raise SystemExit(1)
    print('D_INTEGER_OUTPUT_EXACT')


if __name__ == '__main__':
    main()
