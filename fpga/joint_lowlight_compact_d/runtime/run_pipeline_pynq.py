"""Target-board replay entry: three frame slots and independent core scheduling.

This file is supplied for explicit execution on KV260, not executed by packaging.
Timing includes input copies/cache ownership, MMIO polling and output copies/hashes.
Replaying one RGB file measures this supplied path, not a camera/video application.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

from controller import BASES, SIZES, Buffer, validate_buffers, validate_weights
from pipeline_controller import FrameRequest, JointPipelineController, MODEL_READ_ONLY
from run_pynq import CELLS, DDR_END, PynqBackend, verify_files


class RingPynqBackend(PynqBackend):
    """Resolve DMA ownership by physical buffer, since each slot repeats names."""
    def _allocation(self, name, buffer):
        value = self.allocations.get(buffer.address)
        if value is None or int(value.physical_address) != buffer.address or int(value.nbytes) != buffer.size:
            raise RuntimeError("DMA ring allocation ownership changed: " + name)
        return value


def timing_result(started, completed_at, ended):
    count = len(completed_at)
    if count < 2 or ended <= started or completed_at[-1] <= completed_at[0]:
        raise ValueError("At least two valid frame completions are required")
    return {
        "frames": count,
        "elapsed_seconds": ended - started,
        "batch_fps": count / (ended - started),
        "completion_interval_fps": (count - 1) / (completed_at[-1] - completed_at[0]),
        "max_completion_gap_ms": 1000 * max(b-a for a, b in zip(completed_at, completed_at[1:])),
        "scope": "replayed RGB file; includes CPU copy/cache/MMIO/output hash; excludes load/allocation/final disk write",
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--rgb", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Final completed frame, INT16 Q14 NCHW")
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--slots", type=int, default=3)
    parser.add_argument("--weights", nargs=3, type=int, default=[10923, 10923, 10922])
    parser.add_argument("--timeout", type=float, default=120.0, help="Per admitted frame watchdog, not target latency")
    args = parser.parse_args()
    validate_weights(args.weights)
    if args.frames < 2 or args.slots < 2 or args.timeout <= 0:
        raise ValueError("At least two frames/slots and a positive timeout are required")
    if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("Execute this entry on KV260 Linux/aarch64")
    if args.output.resolve() == args.metrics.resolve() or args.output.exists() or args.metrics.exists():
        raise ValueError("Use distinct new output and metrics paths")
    package = args.package.resolve()
    manifest = verify_files(package)
    raw = args.rgb.read_bytes()
    if len(raw) != SIZES["rgb"]:
        raise ValueError("Input must contain exactly 1272x720 RGB8 HWC bytes")
    fence = package / "runtime/libjoint_fence.so"
    if not fence.is_file():
        raise FileNotFoundError("Compile runtime/mmio_fence.c on the target first")
    from pynq import Overlay, MMIO, allocate
    import numpy as np

    overlay = Overlay(str(package / "joint_system.bit"), download=False)
    for key, cell in CELLS.items():
        actual = overlay.ip_dict.get(cell)
        if actual is None or int(actual["phys_addr"]) != BASES[key]:
            raise ValueError("HWH address mismatch: " + cell)
    overlay.download()
    allocations, slots = {}, []
    controller = None
    completed = False

    def new_allocation(size):
        value = allocate(shape=(size,), dtype=np.uint8)
        address = int(value.physical_address)
        if address in allocations:
            raise RuntimeError("Allocator reused a live allocation")
        allocations[address] = value
        if address % 64 or address + int(value.nbytes) > DDR_END:
            raise RuntimeError("Allocator did not provide aligned usable DDR LOW")
        value[:] = 0
        return Buffer(address, int(value.nbytes))

    try:
        shared = {name: new_allocation(SIZES[name]) for name in sorted(MODEL_READ_ONLY)}
        filenames = {"weights": "weights_int8.bin", "bias": "bias_int32.bin",
                     "weight_frac": "weight_frac.bin", "lut": "tanh_lut_q15.bin"}
        for name, filename in filenames.items():
            payload = (package / "model" / filename).read_bytes()
            if len(payload) != SIZES[name]:
                raise ValueError("Model payload size mismatch: " + name)
            allocations[shared[name].address][:] = np.frombuffer(payload, dtype=np.uint8)
        for _ in range(args.slots):
            slot = dict(shared)
            slot.update({name: new_allocation(size) for name, size in SIZES.items() if name not in MODEL_READ_ONLY})
            validate_buffers(slot)
            slots.append(slot)
        mmios = {name: MMIO(base, 0x10000) for name, base in BASES.items()}
        backend = RingPynqBackend(mmios, allocations, fence)
        controller = JointPipelineController(backend)
        raw_array = np.frombuffer(raw, dtype=np.uint8)
        records, completed_at = [], []
        latest = [None]

        def load_input(request):
            # Called only after the previous owner of this slot was consumed.
            allocations[request.buffers["rgb"].address][:] = raw_array

        def consume_output(frame_id, buffer):
            payload = backend._allocation("fused", buffer).tobytes()
            digest = hashlib.sha256(payload).hexdigest()
            latest[0] = payload
            completed_at.append(time.perf_counter())
            records.append({"frame_id": frame_id, "output_sha256": digest,
                            "seconds_from_start": completed_at[-1] - started})

        requests = (FrameRequest(i, slots[(i-1) % args.slots], tuple(args.weights), load_input)
                    for i in range(1, args.frames+1))
        started = time.perf_counter()
        count = controller.run_pipeline(requests, on_output=consume_output,
                                        max_inflight=args.slots, timeout_s=args.timeout)
        ended = time.perf_counter()
        if count != args.frames:
            raise RuntimeError("Incomplete frame batch")
        completed = True
        metrics = timing_result(started, completed_at, ended)
        metrics.update(status="BOARD_REPLAY_COMPLETED", package_build=manifest["build_id"],
                       weights_q15=args.weights, slots=args.slots,
                       input_sha256=hashlib.sha256(raw).hexdigest(), output_records=records,
                       allocated_bytes=sum(int(a.nbytes) for a in allocations.values()),
                       target_fps=30, batch_target_met=metrics["batch_fps"] >= 30,
                       interval_target_met=metrics["completion_interval_fps"] >= 30)
        args.output.write_bytes(latest[0])
        args.metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in metrics.items() if k != "output_records"}, indent=2))
    finally:
        if completed or controller is None or not controller.poisoned:
            for value in allocations.values():
                value.freebuffer()
        else:
            print("PL failure: DMA retained. Drain/reset the full PL before terminating this process.", flush=True)
            while True:
                time.sleep(60)


if __name__ == "__main__":
    main()
