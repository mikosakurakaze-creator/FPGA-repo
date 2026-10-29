"""Single-frame scheduling contract; supply a real, cache-safe MMIO/DMA backend.

This module does not load a bitstream or allocate Linux DMA memory. A timeout or
AXI/IP failure poisons the controller until the caller has reset the whole PL
and proved outstanding transactions are drained; constructing a new Python
object by itself is not recovery.
"""
from dataclasses import dataclass
import time

FRAME_BYTES = 5495040
SIZES = {
    "rgb": 2747520, "original": FRAME_BYTES, "d_input": FRAME_BYTES,
    "cnn_input": 38160, "a_low": 38160, "a_full": FRAME_BYTES,
    "lowlight": FRAME_BYTES, "d_output": FRAME_BYTES, "fused": FRAME_BYTES,
    "workspace": 2442240, "weights": 10075, "bias": 1944,
    "weight_frac": 486, "lut": 8194,
}
BASES = {"bilinear": 0xA0000000, "curve": 0xA0010000,
         "cnn": 0xA0020000, "prepare": 0xA0030000,
         "fusion": 0xA0040000, "d": 0xA0050000}


@dataclass(frozen=True)
class Buffer:
    address: int
    size: int


def validate_buffers(buffers):
    if set(buffers) != set(SIZES):
        raise ValueError("Provide exactly the named input/model/work/output buffers")
    for name, need in SIZES.items():
        b = buffers[name]
        if (type(b.address) is not int or type(b.size) is not int or b.address < 0
                or b.address % 64 or b.size < need or b.address + b.size > 0x80000000):
            raise ValueError(f"Invalid LOW-DDR/alignment/size for {name}")
    pairs = list(buffers.items())
    for i, (an, a) in enumerate(pairs):
        for bn, b in pairs[i+1:]:
            if a.address < b.address+b.size and b.address < a.address+a.size:
                raise ValueError(f"Overlapping buffers: {an}, {bn}")


def validate_weights(weights):
    if len(weights) != 3 or any(type(w) is not int or not 0 <= w <= 32768 for w in weights):
        raise ValueError("Weights must be three unsigned Q15 integers in [0,32768]")
    if sum(weights) != 32768:
        raise ValueError("Q15 weights must sum exactly to 32768")


class JointController:
    """Backend: read32(ip, offset), write32(ip, offset, u32), barrier(),
    to_device(name, Buffer, access), to_cpu(name, Buffer). Transfers must enforce
    the platform's DMA/cache ownership rules; a no-op is valid only for an
    independently established coherent/non-cacheable mapping.
    """
    def __init__(self, backend, *, clock=time.monotonic):
        self.backend = backend
        self.clock = clock
        self.poisoned = False
        self.last_frame = 0
        self.running = False

    def _pointer(self, ip, offset, buffer):
        self.backend.write32(ip, offset, buffer.address & 0xFFFFFFFF)
        self.backend.write32(ip, offset+4, buffer.address >> 32)

    def _start(self, ip):
        ctrl = self.backend.read32(ip, 0)  # Drain a stale COR done before launch.
        if not ctrl & 4:
            raise RuntimeError(f"{ip} is not idle")
        self.backend.barrier()
        self.backend.write32(ip, 0, 1)  # One start write; auto_restart stays off.

    def _done(self, ip, *, returned=False):
        ctrl = self.backend.read32(ip, 0)
        if not ctrl & 2:
            return False
        if not ctrl & 4:
            raise RuntimeError(f"{ip}: done without idle")
        if returned:
            ret = self.backend.read32(ip, 0x10)
            if ret:
                signed = ret if ret < 0x80000000 else ret-0x100000000
                raise RuntimeError(f"{ip} failed with status {signed}")
        self.backend.barrier()
        return True

    def run(self, frame_id, buffers, weights, *, timeout_s=30.0):
        if self.poisoned or self.running:
            raise RuntimeError("Controller is poisoned or already running")
        if type(frame_id) is not int or not self.last_frame < frame_id <= 0xFFFFFFFF:
            raise ValueError("frame_id must increase without wrapping")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        validate_buffers(buffers)
        validate_weights(weights)
        b = buffers
        self.running = True
        deadline = self.clock()+timeout_s
        try:
            # Claim every allocation before launching any producer. The backend
            # must eliminate dirty CPU output lines as well as flush read inputs.
            read_only = {"rgb", "weights", "bias", "weight_frac", "lut"}
            for name, buf in b.items():
                self.backend.to_device(name, buf, "read" if name in read_only else "read_write")
            for ip in BASES:
                if not self.backend.read32(ip, 0) & 4:
                    raise RuntimeError(f"{ip} was busy before the frame")
            for ip, fields in {
                "prepare": [(0x18,"rgb"),(0x24,"original"),(0x30,"d_input"),(0x3C,"cnn_input")],
                "cnn": [(0x10,"cnn_input"),(0x1C,"weights"),(0x28,"bias"),(0x34,"weight_frac"),
                        (0x40,"lut"),(0x4C,"a_low"),(0x58,"workspace")],
                "bilinear": [(0x10,"a_low"),(0x1C,"a_full")],
                "curve": [(0x10,"original"),(0x1C,"a_full"),(0x28,"lowlight")],
                "d": [(0x18,"d_input"),(0x24,"d_output")],
                "fusion": [(0x18,"original"),(0x24,"lowlight"),(0x30,"d_output"),(0x3C,"fused")],
            }.items():
                for offset, name in fields:
                    self._pointer(ip, offset, b[name])
            for ip, fields in {
                "prepare": [(0x48,0x4A503031)],
                "bilinear": [(0x28,60),(0x30,106)],
                "curve": [(0x34,2747520)],
                "d": [(0x30,720),(0x38,1272),(0x40,0x44433031)],
                "fusion": [(0x48,weights[0]),(0x50,weights[1]),(0x58,weights[2]),
                           (0x60,0x4A463031),(0x68,frame_id)],
            }.items():
                for offset, value in fields:
                    self.backend.write32(ip, offset, value)
            self._start("prepare")
            while not self._done("prepare", returned=True):
                if self.clock() >= deadline:
                    raise TimeoutError("prepare timeout")
            # Both branches use this call's successfully completed prepare. No
            # previous frame's flags or timing estimates participate in gating.
            self._start("cnn")
            self._start("d")
            low_stage = "cnn"
            low_done = d_done = False
            while not (low_done and d_done):
                if self.clock() >= deadline:
                    raise TimeoutError("model paths timeout")
                if not d_done:
                    d_done = self._done("d", returned=True)
                if not low_done and self._done(low_stage):
                    if low_stage == "cnn":
                        low_stage = "bilinear"
                        self._start(low_stage)
                    elif low_stage == "bilinear":
                        low_stage = "curve"
                        self._start(low_stage)
                    else:
                        low_done = True
            self._start("fusion")
            while not self._done("fusion", returned=True):
                if self.clock() >= deadline:
                    raise TimeoutError("fusion timeout")
            if self.backend.read32("fusion", 0x70) != frame_id:
                raise RuntimeError("Fusion completion belongs to another frame")
            self.backend.to_cpu("fused", b["fused"])
            self.last_frame = frame_id
            return b["fused"]
        except Exception:
            self.poisoned = True
            raise
        finally:
            self.running = False
