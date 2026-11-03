"""Multi-frame scheduling reference; no board/FPS claim without a real backend.

Frame input preparation is delayed until all overlapping prior allocations are
released. on_output must consume/copy the result before a buffer slot is reused.
Failure poisons this owner; resetting Python never drains hardware transactions.
"""
from dataclasses import dataclass
import time
from controller import BASES, JointController, validate_buffers, validate_weights

MODEL_READ_ONLY={"weights","bias","weight_frac","lut"}
POINTERS={
    "prepare": [(0x18,"rgb"),(0x24,"original"),(0x30,"d_input"),(0x3C,"cnn_input")],
    "cnn": [(0x10,"cnn_input"),(0x1C,"weights"),(0x28,"bias"),(0x34,"weight_frac"),
            (0x40,"lut"),(0x4C,"a_low"),(0x58,"workspace")],
    "bilinear": [(0x10,"a_low"),(0x1C,"a_full")],
    "curve": [(0x10,"original"),(0x1C,"a_full"),(0x28,"lowlight")],
    "d": [(0x18,"d_input"),(0x24,"d_output")],
    "fusion": [(0x18,"original"),(0x24,"lowlight"),(0x30,"d_output"),(0x3C,"fused")],
}
DEPENDENCIES={"prepare":(),"cnn":("prepare",),"d":("prepare",),
              "bilinear":("cnn",),"curve":("bilinear",),"fusion":("curve","d")}

@dataclass(frozen=True)
class FrameRequest:
    frame_id: int
    buffers: dict
    weights: tuple
    # Callback receives this request only after its buffer slot is safe to reuse.
    prepare_input: object = None

class JointPipelineController(JointController):
    def _configure_stage(self,ip,request):
        for offset,name in POINTERS[ip]:self._pointer(ip,offset,request.buffers[name])
        configs={"prepare": [(0x48,0x4A503031)],"bilinear": [(0x28,60),(0x30,106)],
                 "curve": [(0x34,2747520)],"d": [(0x30,720),(0x38,1272),(0x40,0x44433031)],
                 "fusion": [(0x48,request.weights[0]),(0x50,request.weights[1]),
                            (0x58,request.weights[2]),(0x60,0x4A463031),(0x68,request.frame_id)]}
        for offset,value in configs.get(ip,()):self.backend.write32(ip,offset,value)

    @staticmethod
    def _conflicts(request,active):
        for previous in active:
            for name,buf in request.buffers.items():
                for other,old in previous["request"].buffers.items():
                    if buf.address<old.address+old.size and old.address<buf.address+buf.size:
                        if name==other and name in MODEL_READ_ONLY and buf==old:continue
                        return True
        return False

    def run_pipeline(self,requests,*,on_output,max_inflight=3,timeout_s=30.0):
        """Overlap independent frames, preserve every within-frame producer edge.

        requests may reuse a ring of buffer dictionaries. prepare_input runs only
        after prior use has finished and on_output has consumed that slot. Shared
        model arrays must be immutable; other overlaps serialize slot admission.
        Returned integer is completed frame count, never an FPS estimate.
        """
        if self.poisoned or self.running:raise RuntimeError("Controller is poisoned or already running")
        if type(max_inflight) is not int or max_inflight<2:raise ValueError("Use at least two frame slots")
        if timeout_s<=0 or not callable(on_output):raise ValueError("Positive timeout and output callback required")
        iterator=iter(requests)
        self.running=True;active=[];owners={};pending=None;exhausted=False
        last_admitted=self.last_frame;completed=0
        try:
            for ip in BASES:
                if not self.backend.read32(ip,0)&4:raise RuntimeError(ip+" was busy before pipeline")
            while not exhausted or pending is not None or active:
                # Poll only the frame that owns each running core. Programming
                # another stage never changes a running core's configuration.
                for ip,state in list(owners.items()):
                    if self._done(ip,returned=ip in ("prepare","d","fusion")):
                        if ip=="fusion" and self.backend.read32(ip,0x70)!=state["request"].frame_id:
                            raise RuntimeError("Fusion completion belongs to another frame")
                        state["done"].add(ip);del owners[ip]
                while active and "fusion" in active[0]["done"]:
                    state=active.pop(0);request=state["request"]
                    self.backend.to_cpu("fused",request.buffers["fused"])
                    on_output(request.frame_id,request.buffers["fused"])
                    self.last_frame=request.frame_id;completed+=1
                now=self.clock()
                if any(now>=state["deadline"] for state in active):raise TimeoutError("Pipeline frame timeout")
                if pending is None and not exhausted and len(active)<max_inflight:
                    try:pending=next(iterator)
                    except StopIteration:exhausted=True
                    if pending is not None:
                        if not isinstance(pending,FrameRequest):raise TypeError("Expected FrameRequest")
                        if type(pending.frame_id) is not int or not last_admitted<pending.frame_id<=0xFFFFFFFF:
                            raise ValueError("frame_id must increase without wrapping")
                        validate_buffers(pending.buffers);validate_weights(pending.weights)
                if pending is not None and len(active)<max_inflight and not self._conflicts(pending,active):
                    if pending.prepare_input is not None:pending.prepare_input(pending)
                    for name,buf in pending.buffers.items():
                        self.backend.to_device(name,buf,"read" if name in MODEL_READ_ONLY or name=="rgb" else "read_write")
                    active.append({"request":pending,"started":set(),"done":set(),"deadline":self.clock()+timeout_s})
                    last_admitted=pending.frame_id;pending=None
                for ip in ("fusion","curve","bilinear","cnn","d","prepare"):
                    if ip in owners:continue
                    state=next((s for s in active if ip not in s["started"]),None)
                    if state is not None and all(dep in state["done"] for dep in DEPENDENCIES[ip]):
                        self._configure_stage(ip,state["request"]);self._start(ip)
                        state["started"].add(ip);owners[ip]=state
            return completed
        except BaseException:
            self.poisoned=True
            raise
        finally:self.running=False
