"""Real Host-RAM native tests; no ioctl/transport/DMA allocator/board access."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest

LENGTHS = [10075,1944,486,8194,38160,5495040,38160,5495040,
           38160,5495040,5495040,38160,5495040,5495040]
OUT = [38160,5495040,5495040]
POISON, GUARD = -23131, 0xC3

class Span(C.Structure):
    _fields_ = [('base',C.c_void_p),('allocation_bytes',C.c_uint64),
                ('payload_offset',C.c_uint64),('payload_bytes',C.c_uint64)]

class Receipt(C.Structure):
    _fields_ = [('abi_version',C.c_uint32),('status',C.c_uint32)] + [
        (name,C.c_uint64) for name in ('full_output_poison_bytes','input_copy_bytes',
        'compared_scalars','mismatches','slot_guard_bytes','guard_errors',
        'poison_checked_scalars','poison_occurrences')] + [
        ('first_bad_span',C.c_uint32),('first_guard_side',C.c_uint32),
        ('first_bad_scalar',C.c_uint64),('first_bad_guard_byte',C.c_uint64),
        ('observed_int16',C.c_int32),('expected_int16',C.c_int32)]

def address(s): return s.base+s.payload_offset
def clone(spans): return (Span*len(spans))(*(Span(s.base,s.allocation_bytes,s.payload_offset,s.payload_bytes) for s in spans))

class Native:
    def __init__(self, path):
        # CDLL releases the GIL; PyDLL would retain it. No Python callbacks.
        self.lib=C.CDLL(str(Path(path).resolve()))
        span=C.POINTER(Span);receipt=C.POINTER(Receipt)
        self.lib.kv_hp_validate_poison.argtypes=[span,C.c_int16,receipt]
        self.lib.kv_hp_prepare.argtypes=[span,span,span,C.c_uint32,C.c_uint32,C.c_int16,receipt]
        self.lib.kv_hp_verify.argtypes=[span,span,C.c_uint32,C.c_uint8,receipt]
        for name in ('kv_hp_validate_poison','kv_hp_prepare','kv_hp_verify'):
            getattr(self.lib,name).restype=C.c_int

class Fixture:
    def __init__(self, blobs=None):
        self.owners=[]
        self.immutable=(Span*14)(*(self.make(n,False,0x10+i,
                              None if blobs is None else blobs[i]) for i,n in enumerate(LENGTHS)))
        self.outputs=(Span*3)(*(self.make(n,True,0x11) for n in OUT))
        self.active=(Span*2)(*(self.make(n,True,0x22) for n in OUT[:2]))
    def make(self,n,guarded,fill,blob=None):
        offset=64 if guarded else 0;size=n+(128 if guarded else 0)
        b=C.create_string_buffer(size);self.owners.append(b);p=C.addressof(b)
        C.memset(p,GUARD,size);C.memset(p+offset,fill,n)
        if blob is not None:
            assert len(blob)==n;C.memmove(p+offset,blob,n)
        return Span(p,size,offset,n)
    def simulate_correct_output(self,kind):
        for i,n in enumerate(OUT):C.memmove(address(self.outputs[i]),address(self.immutable[8+3*kind+i]),n)
    def reset_outputs(self):
        for s in self.outputs:
            C.memset(s.base,GUARD,s.allocation_bytes)
            C.memset(address(s),0x11,s.payload_bytes)

class HotpathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('KV_HP_LIBRARY')
        if not path:raise RuntimeError('Set KV_HP_LIBRARY to an explicit Host-built library')
        cls.native=Native(path);cls.f=Fixture()
        assert C.sizeof(Span)==32 and C.sizeof(Receipt)==104
    def setUp(self):self.f.reset_outputs()
    def prepare(self,kind=0,copy=1,outputs=None,active=None,imm=None,receipt=None):
        r=receipt if receipt is not None else Receipt()
        rc=self.native.lib.kv_hp_prepare(outputs if outputs is not None else self.f.outputs,
            active if active is not None else (self.f.active if copy else None),
            imm if imm is not None else self.f.immutable,kind,copy,POISON,C.byref(r))
        return rc,r
    def test_real_full_size_poison_input_copy_and_bit_exact_compare(self):
        r=Receipt();self.assertEqual(self.native.lib.kv_hp_validate_poison(self.f.immutable,POISON,C.byref(r)),0)
        self.assertEqual(r.poison_checked_scalars,11028240)
        for kind in (0,1):
            rc,r=self.prepare(kind);self.assertEqual(rc,0)
            self.assertEqual(r.full_output_poison_bytes,11028240);self.assertEqual(r.input_copy_bytes,5533200)
            for s in self.f.outputs:
                self.assertEqual(C.string_at(address(s),s.payload_bytes),bytes([0xA5])*s.payload_bytes)
                self.assertEqual(C.string_at(s.base,64),bytes([GUARD])*64)
                self.assertEqual(C.string_at(address(s)+s.payload_bytes,64),bytes([GUARD])*64)
            for i,s in enumerate(self.f.active):
                src=self.f.immutable[4+kind*2+i]
                self.assertEqual(C.string_at(address(s),s.payload_bytes),C.string_at(address(src),src.payload_bytes))
                self.assertEqual(C.string_at(s.base,64),bytes([GUARD])*64)
                self.assertEqual(C.string_at(address(s)+s.payload_bytes,64),bytes([GUARD])*64)
            self.f.simulate_correct_output(kind);r=Receipt()
            self.assertEqual(self.native.lib.kv_hp_verify(self.f.outputs,self.f.immutable,kind,GUARD,C.byref(r)),0)
            self.assertEqual(r.compared_scalars,5514120);self.assertEqual(r.slot_guard_bytes,384)
            self.assertEqual((r.mismatches,r.guard_errors),(0,0))
    def test_preloaded_path_does_not_copy_inputs(self):
        before=[C.string_at(address(s),s.payload_bytes) for s in self.f.active]
        rc,r=self.prepare(copy=0);self.assertEqual(rc,0);self.assertEqual(r.input_copy_bytes,0)
        self.assertEqual(before,[C.string_at(address(s),s.payload_bytes) for s in self.f.active])
    def test_partial_stale_poison_is_detected_and_failed_count_is_not_full(self):
        self.prepare();self.f.simulate_correct_output(0)
        index=OUT[1]//2-1;C.c_int16.from_address(address(self.f.outputs[1])+index*2).value=POISON
        r=Receipt();rc=self.native.lib.kv_hp_verify(self.f.outputs,self.f.immutable,0,GUARD,C.byref(r))
        self.assertEqual(rc,6);self.assertEqual(r.mismatches,1)
        self.assertEqual((r.first_bad_span,r.first_bad_scalar),(1,index))
        self.assertEqual(r.compared_scalars,19080+2747520)
        self.assertEqual(r.slot_guard_bytes,384)
    def test_previous_A_output_does_not_pass_B(self):
        self.f.simulate_correct_output(0);r=Receipt()
        self.assertEqual(self.native.lib.kv_hp_verify(self.f.outputs,self.f.immutable,1,GUARD,C.byref(r)),6)
        self.assertEqual(r.compared_scalars,1)
    def test_golden_contains_poison_is_rejected_before_prepare(self):
        s=self.f.immutable[13];at=address(s)+s.payload_bytes-2;old=C.c_int16.from_address(at).value
        try:
            C.c_int16.from_address(at).value=POISON;r=Receipt()
            self.assertEqual(self.native.lib.kv_hp_validate_poison(self.f.immutable,POISON,C.byref(r)),5)
            self.assertEqual((r.first_bad_span,r.first_bad_scalar),(13,s.payload_bytes//2-1))
            self.assertEqual(r.poison_occurrences,1)
        finally:C.c_int16.from_address(at).value=old
    def test_front_and_rear_guard_damage_fail_fast(self):
        self.f.simulate_correct_output(0)
        for i,side in ((0,0),(2,1)):
            s=self.f.outputs[i];at=s.base if side==0 else address(s)+s.payload_bytes
            old=C.c_uint8.from_address(at+63).value
            try:
                C.c_uint8.from_address(at+63).value=0;r=Receipt()
                self.assertEqual(self.native.lib.kv_hp_verify(self.f.outputs,self.f.immutable,0,GUARD,C.byref(r)),7)
                self.assertEqual((r.first_bad_span,r.first_guard_side,r.first_bad_guard_byte),(i,side,63))
                self.assertEqual(r.compared_scalars,0);self.assertEqual(r.guard_errors,1)
            finally:C.c_uint8.from_address(at+63).value=old
    def test_guard_bounds_overflow_alignment_and_lengths_reject_before_writes(self):
        bads=[]
        o=clone(self.f.outputs);o[2].allocation_bytes-=1;bads.append((o,2))
        o=clone(self.f.outputs);o[0].payload_offset=63;bads.append((o,2))
        o=clone(self.f.outputs);o[0].base=(1<<64)-16;o[0].allocation_bytes=4096;bads.append((o,2))
        o=clone(self.f.outputs);o[0].payload_offset=(1<<64)-1;bads.append((o,2))
        o=clone(self.f.outputs);o[0].base=None;bads.append((o,2))
        o=clone(self.f.outputs);o[2].payload_bytes-=2;bads.append((o,1))
        b=C.create_string_buffer(OUT[0]+129);o=clone(self.f.outputs)
        o[0]=Span(C.addressof(b),len(b),65,OUT[0]);bads.append((o,3))
        before=[C.string_at(address(s),s.payload_bytes) for s in self.f.outputs]
        for o,expected in bads:
            with self.subTest(error=expected):
                r=Receipt();r.abi_version=99;rc,r=self.prepare(outputs=o,receipt=r)
                self.assertEqual(rc,expected);self.assertEqual(r.abi_version,99)
                self.assertEqual(before,[C.string_at(address(s),s.payload_bytes) for s in self.f.outputs])
    def test_aliases_against_output_immutable_input_and_receipt_are_rejected(self):
        before=[C.string_at(address(s),s.payload_bytes) for s in self.f.outputs]
        imm=clone(self.f.immutable);imm[9]=self.f.outputs[1]
        self.assertEqual(self.prepare(imm=imm)[0],4)
        r=Receipt();self.assertEqual(self.native.lib.kv_hp_verify(self.f.outputs,imm,0,GUARD,C.byref(r)),4)
        imm=clone(self.f.immutable);imm[4]=self.f.active[0]
        self.assertEqual(self.prepare(imm=imm)[0],4)
        active=clone(self.f.active);active[1]=self.f.outputs[1]
        self.assertEqual(self.prepare(active=active)[0],4)
        out=clone(self.f.outputs);out[0]=Span(out[1].base,out[1].allocation_bytes,64,OUT[0])
        self.assertEqual(self.prepare(outputs=out)[0],4)
        # Input copy must not overwrite padding/guards of an immutable view.
        arena=C.create_string_buffer(38160*2+1024);p=C.addressof(arena)
        active=clone(self.f.active);active[0]=Span(p,38160+128,64,38160)
        imm=clone(self.f.immutable);imm[4]=Span(p+38160+32,38160+512,256,38160)
        self.assertEqual(self.prepare(active=active,imm=imm)[0],4)
        receipt=C.cast(address(self.f.outputs[0]),C.POINTER(Receipt))
        self.assertEqual(self.native.lib.kv_hp_prepare(self.f.outputs,self.f.active,self.f.immutable,0,1,POISON,receipt),4)
        self.assertEqual(before,[C.string_at(address(s),s.payload_bytes) for s in self.f.outputs])
    def test_invalid_kind_copy_mode_and_missing_copy_target_rejected(self):
        self.assertEqual(self.prepare(kind=2)[0],1);self.assertEqual(self.prepare(copy=2)[0],1)
        r=Receipt();self.assertEqual(self.native.lib.kv_hp_prepare(self.f.outputs,None,self.f.immutable,0,1,POISON,C.byref(r)),1)
    def test_cdll_allows_python_thread_progress_during_native_scanning(self):
        ready=threading.Event();go=threading.Event();done=threading.Event();count=[0]
        def worker():
            ready.set();go.wait()
            while not done.is_set():count[0]+=1;time.sleep(.0001)
        t=threading.Thread(target=worker);t.start();self.assertTrue(ready.wait(1))
        prior=sys.getswitchinterval();sys.setswitchinterval(10)
        try:
            go.set()
            for _ in range(8):
                r=Receipt();self.assertEqual(self.native.lib.kv_hp_validate_poison(self.f.immutable,POISON,C.byref(r)),0)
            done.set()
        finally:sys.setswitchinterval(prior);done.set();go.set();t.join(1)
        self.assertFalse(t.is_alive());self.assertGreater(count[0],0)
    def test_optional_real_S1_assets_are_SHA_bound_and_compared_in_Host_RAM(self):
        plan=os.environ.get('KV_HP_S1_PLAN')
        if not plan:self.skipTest('Optional real S1 raw numerical assets not supplied')
        assets=json.loads(Path(plan).read_text(encoding='utf-8'))['assets']
        names=['A/'+n for n in ('weights_int8.bin','bias_int32.bin','weight_frac.bin','tanh_lut_q15.bin')]
        names += [g+'/'+n for g in ('A','B') for n in ('input_q14.bin','model_input_q14.bin')]
        names += [g+'/'+n for g in ('A','B') for n in ('expected_a_low_q14.bin','expected_a_full_q14.bin','expected_enhanced_q14.bin')]
        blobs=[]
        for name,n in zip(names,LENGTHS):
            item=assets[name];blob=Path(item['path']).read_bytes()
            self.assertEqual(len(blob),n);self.assertEqual(hashlib.sha256(blob).hexdigest(),item['sha256']);blobs.append(blob)
        f=Fixture(blobs);r=Receipt()
        self.assertEqual(self.native.lib.kv_hp_validate_poison(f.immutable,POISON,C.byref(r)),0)
        self.assertEqual(r.poison_checked_scalars,11028240)
        for kind in (0,1):
            r=Receipt();self.assertEqual(self.native.lib.kv_hp_prepare(f.outputs,f.active,f.immutable,kind,1,POISON,C.byref(r)),0)
            f.simulate_correct_output(kind);r=Receipt()
            self.assertEqual(self.native.lib.kv_hp_verify(f.outputs,f.immutable,kind,GUARD,C.byref(r)),0)
            self.assertEqual((r.compared_scalars,r.slot_guard_bytes),(5514120,384))
        for s,blob in zip(f.immutable,blobs):
            self.assertEqual(hashlib.sha256(C.string_at(address(s),s.payload_bytes)).digest(),hashlib.sha256(blob).digest())

if __name__=='__main__':unittest.main()
