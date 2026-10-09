"""Host mocks only. No board access and no real FPS claims."""
import threading
import copy
import unittest
from ring_runner import RingExperiment, Completion
from analyze_ring import analyze

class Clock:
    def __init__(self): self.lock=threading.Lock();self.n=100
    def __call__(self):
        with self.lock: self.n+=100;return self.n

class Mock:
    def __init__(self, fail=None):
        self.live={};self.history={};self.started=[];self.verified=[]
        self.fail=fail;self.aborted=False;self.quarantined=False
    def prepare(self,s,i,k,c):
        if s in self.live:raise AssertionError('overwrote unverified output')
        if s in self.history:assert self.history[s]!=k
        self.live[s]=(i,k);self.history[s]=k
        return {'full_output_poison_bytes':11028240,'input_kind':k,'input_copy_bytes':5533200 if c else 0}
    def compute(self,s,i,k,stop):
        if self.aborted or stop.is_set():raise RuntimeError('stopped')
        self.started.append(i);return Completion((10,20,30),(1,1,1),(1,1,1))
    def verify(self,s,i,k):
        assert self.live[s]==(i,k)
        if i==self.fail:raise RuntimeError('Golden mismatch')
        self.verified.append(i);del self.live[s]
        return {'compared_scalars':5514120,'mismatches':0,'slot_guard_bytes':384,'guard_errors':0}
    def abort_new_starts(self):self.aborted=True
    def quarantine(self):self.quarantined=True
    def final_audit(self):return {'immutable_inputs_models_golden_sha_ok':True,'all_guards_ok':True}

class RingTests(unittest.TestCase):
    def test_every_frame_full_pipeline_verified_and_fixed_slot_changes_kind(self):
        b=Mock();report=RingExperiment(b,Clock()).run(measured=60,warmup=6)
        self.assertEqual(len(b.started),132);self.assertEqual(b.started,b.verified)
        self.assertEqual(report['BOARD_30FPS'],'NOT_TESTED')
        self.assertTrue(all(r['verified'] for r in report['frames']))
        for p in report['phases']:
            self.assertLessEqual(p['output_end_ns'],p['validation_end_ns'])
            self.assertLessEqual(p['fully_validated_fps'],p['observed_producer_fps'])
        stats=analyze(report)
        self.assertEqual(stats['BOARD_30FPS'],'NOT_TESTED')
        self.assertEqual(stats['all_frame_module_starts'],[132]*3)
        report['frames'][6]['verified']=False
        with self.assertRaises(ValueError):analyze(report)
    def test_error_stops_and_quarantines_no_retry(self):
        b=Mock(fail=0);run=RingExperiment(b,Clock())
        with self.assertRaises(RuntimeError):run.run(measured=60,warmup=6)
        self.assertTrue(b.aborted and b.quarantined)
        self.assertLessEqual(len(b.started),3)
        with self.assertRaises(RuntimeError):run.run(measured=60,warmup=6)
    def test_short_window_and_even_ring_rejected(self):
        for n in (2,4,8):
            with self.assertRaises(ValueError):RingExperiment(Mock(),Clock(),slots=n)
        with self.assertRaises(ValueError):RingExperiment(Mock(),Clock()).run(measured=59)
    def test_incomplete_module_sequence_rejected(self):
        b=Mock();b.compute=lambda *a:Completion((10,20,30),(1,1,0),(1,1,0))
        with self.assertRaises(RuntimeError):RingExperiment(b,Clock()).run(measured=60)
        self.assertTrue(b.quarantined)
    def test_failed_stop_request_does_not_hide_unknown_dma_state(self):
        b=Mock(fail=0)
        def bad_stop():raise RuntimeError('driver STOP latch unavailable')
        b.abort_new_starts=bad_stop
        with self.assertRaisesRegex(RuntimeError,'STOP_REQUEST_NOT_CONFIRMED'):
            RingExperiment(b,Clock()).run(measured=60)
        self.assertTrue(b.quarantined)
    def test_stuck_validator_is_quarantined_before_bounded_join(self):
        b=Mock();entered=threading.Event();release=threading.Event()
        def blocked(*args):entered.set();release.wait(2);return {'compared_scalars':5514120,'mismatches':0,'slot_guard_bytes':384,'guard_errors':0}
        b.verify=blocked
        old_prepare=b.prepare
        def fail_prepare(s,i,k,c):
            if i==1:
                self.assertTrue(entered.wait(1));raise RuntimeError('prepare failed')
            return old_prepare(s,i,k,c)
        b.prepare=fail_prepare;run=RingExperiment(b,Clock())
        try:
            with self.assertRaisesRegex(RuntimeError,'VALIDATOR_NOT_JOINED_DMA_QUARANTINED'):
                run.run(measured=60,join_seconds=.01)
            self.assertTrue(b.quarantined);self.assertFalse(run.worker_joined)
        finally:release.set();run.worker.join(1)

    def test_offline_analyzer_rejects_replay_ownership_and_warmup_tampering(self):
        report=RingExperiment(Mock(),Clock()).run(measured=60,warmup=6)
        def duplicate_phase(r):r['phases'][1]['phase']=0
        def wrong_copy(r):r['phases'][1]['copy_input']=False
        def early_reuse(r):r['frames'][3]['prepare_begin_ns']=r['frames'][0]['verify_end_ns']-1
        def bad_warm_time(r):r['frames'][0]['verify_end_ns']=r['frames'][0]['output_ready_ns']-1
        def bad_warm_module(r):r['frames'][0]['module_ns']=[10,20,0]
        def bad_phase_order(r):r['frames'][0]['phase']=1
        for mutate in (duplicate_phase,wrong_copy,early_reuse,bad_warm_time,bad_warm_module,bad_phase_order):
            with self.subTest(case=mutate.__name__):
                bad=copy.deepcopy(report);mutate(bad)
                with self.assertRaises(ValueError):analyze(bad)

if __name__=='__main__':unittest.main()
