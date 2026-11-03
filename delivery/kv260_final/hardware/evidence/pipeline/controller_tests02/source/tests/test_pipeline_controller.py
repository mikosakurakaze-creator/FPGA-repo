import unittest
from test_controller import Backend,buffers
from controller import Buffer
from pipeline_controller import FrameRequest,JointPipelineController

class TimedBackend(Backend):
    # Advance every active hardware core together, independently of poll order.
    def __init__(self):
        super().__init__();self.tick=0;self.end={};self.frame_of={};self.finished_frame={};self.input_frames={}
        self.delays={"prepare":3,"cnn":4,"bilinear":3,"curve":7,"d":12,"fusion":5}
    def step(self):
        self.tick+=1
        for ip in list(self.end):
            if self.tick>=self.end[ip]:
                del self.end[ip];self.done[ip]=True;self.finished_frame[ip]=self.frame_of[ip]
                self.events.append(("complete_frame",ip,self.frame_of[ip],self.tick))
        return self.tick/1000
    def read32(self,ip,offset):
        if offset==0:
            ctrl=0 if ip in self.end else 4
            if self.done[ip]:ctrl|=2
            self.done[ip]=False
            return ctrl
        if ip=="fusion" and offset==0x70:return self.finished_frame.get(ip,0)
        return self.reg.get((ip,offset),0) if offset!=0x10 else self.failure.get(ip,0)&0xFFFFFFFF
    def write32(self,ip,offset,value):
        if offset==0 and value==1:
            if ip in self.end:raise AssertionError("overwrote running core")
            address=self.reg[ip,0x18] if ip in ("prepare","d","fusion") else self.reg[ip,0x10]
            frame=self.input_frames.get(address,0)
            if ip=="fusion" and self.reg[ip,0x68]!=frame:raise AssertionError("mixed-frame pointer/cookie")
            self.frame_of[ip]=frame;self.end[ip]=self.tick+self.delays[ip];self.done[ip]=False
            self.events.append(("start_frame",ip,frame,self.tick))
        else:
            if ip in self.end:raise AssertionError("configured busy core")
            self.reg[ip,offset]=value

def slot(index):return {k:Buffer(v.address+index*0x04000000,v.size) for k,v in buffers().items()}

class PipelineTests(unittest.TestCase):
    def test_thirty_frames_three_slots_overlap_and_preserve_dependencies(self):
        b=TimedBackend();c=JointPipelineController(b,clock=b.step)
        slots=[slot(i) for i in range(3)];output=[];prepared=[]
        def load(req):
            prepared.append((req.frame_id,b.tick))
            b.input_frames.update({buf.address:req.frame_id for buf in req.buffers.values()})
        frames=[FrameRequest(i+1,slots[i%3],(10923,10923,10922),load) for i in range(30)]
        n=c.run_pipeline(frames,on_output=lambda i,buf:output.append((i,buf,b.tick)))
        self.assertEqual(n,30);self.assertEqual([x[0] for x in output],list(range(1,31)))
        for i,t in prepared:
            if i>3:self.assertGreaterEqual(t,output[i-4][2])
        events=b.events
        starts=[e for e in events if e[0]=="start_frame"]
        self.assertEqual(len(starts),180)
        from pipeline_controller import DEPENDENCIES
        started={(e[1],e[2]):e[3] for e in starts}
        finished={(e[1],e[2]):e[3] for e in events if e[0]=="complete_frame"}
        for frame in range(1,31):
            for ip,deps in DEPENDENCIES.items():
                self.assertIn((ip,frame),started)
                for dep in deps:self.assertGreaterEqual(started[ip,frame],finished[dep,frame])
        # First three frame slots' RGB addresses identify their producer paths.
        first_fusion=next(e[3] for e in starts if e[1]=="fusion")
        second_prepare=[e[3] for e in starts if e[1]=="prepare"][1]
        self.assertLess(second_prepare,first_fusion)
        # Compare steady-state batch time against thirty isolated frame delays.
        self.assertLess(b.tick,30*(3+max(4+3+7,12)+5))
        self.assertFalse(c.poisoned)
    def test_failure_never_releases_bad_output_and_poison_prevents_reuse(self):
        b=TimedBackend();b.failure["fusion"]=-3;c=JointPipelineController(b,clock=b.step);out=[]
        with self.assertRaises(RuntimeError):c.run_pipeline([FrameRequest(1,slot(0),(32768,0,0),lambda req:b.input_frames.update({buf.address:req.frame_id for buf in req.buffers.values()}))],on_output=lambda *x:out.append(x))
        self.assertEqual(out,[]);self.assertTrue(c.poisoned)
    def test_timeout_does_not_recycle_slots(self):
        b=TimedBackend();b.delays["d"]=100000;c=JointPipelineController(b,clock=b.step);out=[]
        with self.assertRaises(TimeoutError):c.run_pipeline([FrameRequest(1,slot(0),(32768,0,0))],on_output=lambda *x:out.append(x),timeout_s=.1)
        self.assertEqual(out,[]);self.assertTrue(c.poisoned)
    def test_invalid_frame_does_not_launch(self):
        b=TimedBackend();c=JointPipelineController(b,clock=b.step)
        with self.assertRaises(ValueError):c.run_pipeline([FrameRequest(1,slot(0),(0,0,0))],on_output=lambda *x:None)
        self.assertFalse(any(e[0]=="start_frame" for e in b.events))

if __name__=="__main__":unittest.main()
