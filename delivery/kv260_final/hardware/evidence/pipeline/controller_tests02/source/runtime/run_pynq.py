"""Explicit board invocation for the reviewed package. Not executed on a board here.

Requires Linux/aarch64, PYNQ, exclusive PL ownership, and a locally built fence
library. Do not use /dev/mem guesses or substitute CPU virtual addresses.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import platform

from controller import BASES, SIZES, Buffer, JointController, validate_weights

DDR_END = 0x7FF00000  # Top 1 MiB of DDR LOW is reserved by the frozen PS configuration.
CELLS = {"bilinear": "bilinear_fixed16_buffered_0", "curve": "curve_image_fixed16_0",
         "cnn": "zero_dce_cnn_top_0", "prepare": "joint_rgb8_prepare_0",
         "fusion": "joint_fusion_0", "d": "compact_d_top_0"}


def verify_files(package):
    manifest = json.loads((package/"manifest.json").read_text())
    if manifest.get("status") != "HARDWARE_PACKAGE_READY_BOARD_NOT_TESTED":
        raise ValueError("This is not an accepted joint hardware package")
    for name, spec in manifest["files"].items():
        path = (package/name).resolve()
        if not path.is_relative_to(package.resolve()) or not path.is_file():
            raise ValueError("Missing/unsafe package file: "+name)
        if path.stat().st_size != spec["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
            raise ValueError("Package file identity mismatch: "+name)
    return manifest


class PynqBackend:
    def __init__(self, mmios, allocations, fence):
        self.mmios, self.allocations = mmios, allocations
        self.library = ctypes.CDLL(str(fence))
        self.fence = self.library.joint_mmio_fence
        self.fence.argtypes, self.fence.restype = [], None

    def read32(self, ip, offset):
        return int(self.mmios[ip].read(offset))

    def write32(self, ip, offset, value):
        self.mmios[ip].write(offset, int(value))

    def barrier(self):
        self.fence()

    def _allocation(self, name, buffer):
        value = self.allocations[name]
        if int(value.physical_address) != buffer.address or value.nbytes != buffer.size:
            raise RuntimeError("DMA allocation ownership changed")
        return value

    def to_device(self, name, buffer, access):
        # Flush outputs too: dirty CPU lines must not later overwrite PL output.
        self._allocation(name, buffer).sync_to_device()
        self.fence()

    def to_cpu(self, name, buffer):
        self.fence()
        self._allocation(name, buffer).sync_from_device()
        self.fence()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--package", required=True, type=Path)
    p.add_argument("--rgb", required=True, type=Path, help="Exactly 720*1272*3 decoded RGB8 HWC bytes")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--weights", nargs=3, type=int, default=[10923, 10923, 10922])
    p.add_argument("--timeout", type=float, default=120.0)
    a = p.parse_args()
    validate_weights(a.weights)
    if platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("Run this entry point on the target Linux/aarch64 board")
    if a.output.exists():
        raise ValueError("Refusing to overwrite existing output")
    package = a.package.resolve()
    manifest = verify_files(package)
    raw = a.rgb.read_bytes()
    if len(raw) != SIZES["rgb"]:
        raise ValueError("Input must be exactly 1272x720 RGB8 HWC; decode/crop explicitly upstream")
    fence = package/"runtime/libjoint_fence.so"
    if not fence.is_file():
        raise FileNotFoundError("Build runtime/mmio_fence.c on the target before running")
    from pynq import Overlay, MMIO, allocate
    import numpy as np
    overlay = Overlay(str(package/"joint_system.bit"), download=False)
    for key, cell in CELLS.items():
        actual = overlay.ip_dict.get(cell)
        if actual is None or int(actual["phys_addr"]) != BASES[key]:
            raise ValueError("HWH control address mismatch: "+cell)
    # Loading/recovery and exclusive hardware ownership are operator obligations.
    overlay.download()
    allocations = {}
    controller = None
    completed = False
    try:
        for name, size in SIZES.items():
            allocations[name] = allocate(shape=(size,), dtype=np.uint8)
            value = allocations[name]
            if int(value.physical_address) % 64 or int(value.physical_address)+value.nbytes > DDR_END:
                raise RuntimeError("Allocator did not supply aligned usable DDR LOW")
            value[:] = 0
        allocations["rgb"][:] = np.frombuffer(raw, dtype=np.uint8)
        for name, filename in {"weights": "weights_int8.bin", "bias": "bias_int32.bin",
                               "weight_frac": "weight_frac.bin", "lut": "tanh_lut_q15.bin"}.items():
            payload = (package/"model"/filename).read_bytes()
            if len(payload) != SIZES[name]:
                raise ValueError("Model payload size mismatch")
            allocations[name][:] = np.frombuffer(payload, dtype=np.uint8)
        buffers = {name: Buffer(int(value.physical_address), int(value.nbytes)) for name, value in allocations.items()}
        mmios = {name: MMIO(base, 0x10000) for name, base in BASES.items()}
        controller = JointController(PynqBackend(mmios, allocations, fence))
        controller.run(1, buffers, a.weights, timeout_s=a.timeout)
        a.output.write_bytes(allocations["fused"].tobytes())
        completed = True
        print(json.dumps({"status": "FRAME_COMPLETED", "frame_id": 1, "weights_q15": a.weights,
                          "output_bytes": a.output.stat().st_size,
                          "output_sha256": hashlib.sha256(a.output.read_bytes()).hexdigest(),
                          "package_build": manifest["build_id"]}, indent=2))
    finally:
        if completed or controller is None or not controller.poisoned:
            for value in allocations.values():
                value.freebuffer()
        else:
            # Do not free a physical allocation still reachable by outstanding
            # PL AXI traffic. Keep the process alive until operator recovery.
            print("PL failure: DMA allocations retained. Reset/drain the full PL before terminating this process.", flush=True)
            import time
            while True:
                time.sleep(60)


if __name__ == "__main__":
    main()
