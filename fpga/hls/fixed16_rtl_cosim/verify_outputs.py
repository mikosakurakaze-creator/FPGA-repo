"""Compare Vitis HLS C and RTL m_axi output vectors for one Fixed16 transaction."""

import argparse
import struct
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tv_dir", type=Path)
    parser.add_argument("top")
    parser.add_argument("elements", type=int)
    args = parser.parse_args()

    c_path = args.tv_dir / "cdatafile" / f"c.{args.top}.autotvout_gmem_output.dat"
    rtl_path = args.tv_dir / "rtldatafile" / f"rtl.{args.top}.autotvout_gmem_output.dat"
    c_data = c_path.read_bytes()
    rtl_data = rtl_path.read_bytes()
    expected_bytes = 16 + args.elements * 2  # observed 16-byte transaction header + i16 payload
    if len(c_data) != expected_bytes or len(rtl_data) != expected_bytes:
        raise ValueError(
            f"unexpected vector lengths: C={len(c_data)}, RTL={len(rtl_data)}, "
            f"expected={expected_bytes}"
        )
    if c_data[:16] != rtl_data[:16]:
        raise ValueError("C/RTL transaction headers differ")

    encoding = f"<{args.elements}h"
    c_values = struct.unpack(encoding, c_data[16:])
    rtl_values = struct.unpack(encoding, rtl_data[16:])
    differences = [abs(c - rtl) / 16384.0 for c, rtl in zip(c_values, rtl_values)]
    mismatches = sum(c != rtl for c, rtl in zip(c_values, rtl_values))
    print(
        f"top={args.top} elements={args.elements} bit_exact={c_data == rtl_data} "
        f"mismatches={mismatches} max_abs_difference={max(differences):.12g} "
        f"mean_abs_difference={sum(differences) / args.elements:.12g}"
    )
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
