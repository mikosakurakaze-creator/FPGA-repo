import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"runtime"))
from controller import BASES, SIZES, Buffer, JointController


class Backend:
    def __init__(self, d_delay=5):
        self.events=[]
        self.reg={}
        self.left={}
        self.done={ip:True for ip in BASES}  # Deliberately stale done flags.
        self.delays={"prepare":2,"cnn":3,"bilinear":2,"curve":3,"d":d_delay,"fusion":2}
        self.failure={}

    def read32(self, ip, offset):
        if offset==0:
            if self.left.get(ip,0)>0:
                self.left[ip]-=1
                if self.left[ip]==0:
                    self.done[ip]=True
                    self.events.append(("complete",ip))
            ctrl=0 if self.left.get(ip,0)>0 else 4
            if self.done[ip]:ctrl|=2
            self.done[ip]=False
            return ctrl
        if offset==0x10:return self.failure.get(ip,0)&0xFFFFFFFF
        if ip=="fusion" and offset==0x70:return self.reg[(ip,0x68)]
        return self.reg.get((ip,offset),0)

    def write32(self, ip, offset, value):
        if offset==0 and value==1:
            self.events.append(("start",ip))
            self.left[ip]=self.delays[ip]
            self.done[ip]=False
        else:self.reg[ip,offset]=value

    def barrier(self):self.events.append(("barrier",))
    def to_device(self, name, buffer, access):self.events.append(("device",name,access))
    def to_cpu(self, name, buffer):self.events.append(("cpu",name))


def buffers():
    result={}
    addr=0x10000000
    for name,size in SIZES.items():
        size=(size+63)//64*64
        result[name]=Buffer(addr,size)
        addr+=size
    return result


class ControllerTest(unittest.TestCase):
    def test_either_path_may_complete_first(self):
        for delay in (1,30):
            with self.subTest(delay=delay):
                backend=Backend(delay)
                c=JointController(backend)
                for frame in (11,12):
                    backend.events.clear()
                    c.run(frame,buffers(),(10923,10923,10922))
                    e=backend.events
                    self.assertLess(e.index(("complete","prepare")),e.index(("start","d")))
                    self.assertLess(e.index(("complete","prepare")),e.index(("start","cnn")))
                    self.assertLess(e.index(("complete","cnn")),e.index(("start","bilinear")))
                    self.assertLess(e.index(("complete","bilinear")),e.index(("start","curve")))
                    for ip in ("d","curve"):
                        self.assertLess(e.index(("complete",ip)),e.index(("start","fusion")))
                    for ip in BASES:self.assertEqual(e.count(("start",ip)),1)
                    self.assertEqual(e[-1],("cpu","fused"))
                    self.assertEqual(backend.reg["d",0x38],1272)

    def test_ip_failure_blocks_fusion_and_reuse(self):
        for ip in ("prepare","d"):
            backend=Backend();backend.failure[ip]=-1
            c=JointController(backend)
            with self.assertRaises(RuntimeError):c.run(1,buffers(),(32768,0,0))
            self.assertNotIn(("start","fusion"),backend.events)
            self.assertTrue(c.poisoned)
            with self.assertRaises(RuntimeError):c.run(2,buffers(),(32768,0,0))

    def test_fusion_failure_never_exposes_output(self):
        backend=Backend();backend.failure["fusion"]=-3
        c=JointController(backend)
        with self.assertRaises(RuntimeError):c.run(1,buffers(),(32768,0,0))
        self.assertNotIn(("cpu","fused"),backend.events)
        self.assertTrue(c.poisoned)

    def test_wrong_frame_never_exposes_output(self):
        class WrongFrame(Backend):
            def read32(self,ip,offset):
                if ip=="fusion" and offset==0x70:return 999
                return super().read32(ip,offset)
        backend=WrongFrame();c=JointController(backend)
        with self.assertRaises(RuntimeError):c.run(1,buffers(),(32768,0,0))
        self.assertNotIn(("cpu","fused"),backend.events)

    def test_timeout_poisoning(self):
        backend=Backend(1000000)
        ticks=iter(range(100000))
        c=JointController(backend,clock=lambda: next(ticks))
        with self.assertRaises(TimeoutError):c.run(1,buffers(),(0,32768,0),timeout_s=10)
        self.assertTrue(c.poisoned)
        self.assertNotIn(("start","fusion"),backend.events)

    def test_invalid_weights_never_start(self):
        for weights in ((0,0,0),(0x18000,0,0),(-1,32768,1),(True,32767,0)):
            backend=Backend();c=JointController(backend)
            with self.assertRaises(ValueError):c.run(1,buffers(),weights)
            self.assertEqual(backend.events,[])

    def test_bad_buffer_range_or_overlap(self):
        for name,value in (("original",Buffer(0x10000000,5495040)),
                           ("d_input",Buffer(0x7FFFFFC0,5495040)),
                           ("fused",Buffer(0x40000001,5495040))):
            backend=Backend();b=buffers();b[name]=value
            with self.assertRaises(ValueError):JointController(backend).run(1,b,(0,0,32768))
            self.assertEqual(backend.events,[])


if __name__=="__main__":unittest.main()
