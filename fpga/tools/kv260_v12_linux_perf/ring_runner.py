"""Host-reviewable ring measurement core; no transport, DMA allocator or board CLI.

A Linux driver binding must implement Backend below. Never substitute JTAG calls.
The report is evidence awaiting independent audit, not a BOARD_30FPS update.
"""
from dataclasses import dataclass
from pathlib import Path
import platform
import threading
import time


@dataclass(frozen=True)
class Completion:
    module_ns: tuple
    starts: tuple
    dones: tuple
    stage_evidence: tuple = ()


class LinuxRawClock:
    def __init__(self):
        if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
            raise RuntimeError('BOARD_AARCH64_LINUX_REQUIRED')
        self.source = Path('/sys/devices/system/clocksource/clocksource0/current_clocksource').read_text().strip()
        if self.source != 'arch_sys_counter':
            raise RuntimeError('REVIEW_ACTUAL_CLOCKSOURCE_BEFORE_RUNNING')
        self.resolution = time.clock_getres(time.CLOCK_MONOTONIC_RAW)
        if self.resolution > 1e-6:
            raise RuntimeError('INSUFFICIENT_CLOCK_RESOLUTION')

    def __call__(self):
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)


class Backend:
    """Contract for lzm's independently reviewed, owned-DMA Linux driver binding.

    Allocate guarded slots once, use driver-returned DMA bus addresses internally,
    and claim all CSR regions exclusively. No arbitrary physical DDR addresses.
    prepare fills EVERY output word with a reviewed non-Golden poison, updates real
    A/B inputs and performs required DMA ownership/barriers. compute executes all
    three IPs, returns observed durations and respects a common kernel submit lock
    plus STOP latch before each start. verify compares all three complete INT16
    arrays and slot guards, before releasing ownership. Validation must release the
    Python GIL (native memcmp/extension), or use a process with shared ownership.
    All long/blocking bindings release the GIL or use independent processes.
    abort_new_starts is a bounded nonblocking software STOP latch, never AXI reset.
    quarantine is nonblocking and retains allocations/mappings/device references,
    independent of any MMIO/submit lock that could be stuck. compute has reviewed
    per-IP <=5s/2,000,000-poll bounds, but a synchronous bus hang cannot be canceled.
    The driver must also pin them if the process exits or its fd is closed.
    """
    def prepare(self, slot, frame_id, kind, copy_input): raise NotImplementedError
    def compute(self, slot, frame_id, kind, stop): raise NotImplementedError
    def verify(self, slot, frame_id, kind): raise NotImplementedError
    def abort_new_starts(self): raise NotImplementedError
    def quarantine(self): raise NotImplementedError
    def final_audit(self): raise NotImplementedError


class RingExperiment:
    def __init__(self, backend, clock, slots=3):
        if slots not in (3, 5, 7):
            raise ValueError('USE_ODD_FIXED_MODULO_SLOTS_TO_CHANGE_GOLDEN_ON_REUSE')
        self.backend, self.clock, self.slots = backend, clock, slots
        self.cv = threading.Condition()
        self.states = ['FREE'] * slots
        self.pending = []
        self.stop = threading.Event()
        self.closed = False
        self.error = None
        self.abort_error = None
        self.next_id = 0
        self.rows = []
        self.deadline = None
        self.quarantine_error = None
        self.worker_joined = None
        self.worker = threading.Thread(target=self._validator, name='kv-full-validator',daemon=True)

    def _deadline_check(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            raise RuntimeError('EXPERIMENT_DEADLINE_NO_RETRY')

    def _fail(self, exc):
        with self.cv:
            first = self.error is None
            if self.error is None:
                self.error = exc
            self.stop.set()
            self.cv.notify_all()
        # Backend serializes STOP/AP_START in the same kernel submit lock.
        if not first:
            return
        # Pin unknown DMA immediately; never wait for a worker before requesting it.
        try:
            self.backend.quarantine()
        except Exception as pin_error:
            self.quarantine_error = pin_error
        try:
            self.backend.abort_new_starts()
        except Exception as latch_error:
            with self.cv:
                self.abort_error = latch_error

    def _validator(self):
        try:
            while True:
                with self.cv:
                    while not self.pending and not self.closed and not self.stop.is_set():
                        self._deadline_check()
                        self.cv.wait(timeout=1)
                    if self.stop.is_set() or (self.closed and not self.pending):
                        return
                    row = self.pending.pop(0)
                    slot = row['slot']
                    if self.states[slot] != 'READY':
                        raise RuntimeError('INVALID_VALIDATOR_OWNERSHIP')
                    self.states[slot] = 'VALIDATING'
                row['verify_begin_ns'] = self.clock()
                check = self.backend.verify(slot, row['id'], row['kind'])
                if (check.get('compared_scalars') != 5514120 or check.get('mismatches') != 0 or
                        check.get('slot_guard_bytes') != 384 or check.get('guard_errors') != 0):
                    raise RuntimeError('INCOMPLETE_OR_FAILED_FULL_COMPARE')
                row['verification'] = check
                row['verify_end_ns'] = self.clock()
                with self.cv:
                    row['verified'] = True
                    self.states[slot] = 'FREE'
                    self.cv.notify_all()
        except Exception as exc:
            self._fail(exc)

    def _one(self, phase, warm, copy_input):
        frame_id = self.next_id
        slot, kind = frame_id % self.slots, frame_id % 2
        before_wait = self.clock()
        with self.cv:
            self._deadline_check()
            while self.states[slot] != 'FREE' and not self.stop.is_set():
                self.cv.wait(timeout=1)
                self._deadline_check()
            if self.stop.is_set():
                raise RuntimeError('STOP_LATCHED') from self.error
            self.states[slot] = 'PRODUCING'
        row = dict(id=frame_id, slot=slot, kind=kind, phase=phase, warmup=warm,
                   before_wait_ns=before_wait, prepare_begin_ns=self.clock(), verified=False)
        prep = self.backend.prepare(slot, frame_id, kind, copy_input)
        if (prep.get('full_output_poison_bytes') != 11028240 or
                prep.get('input_kind') != kind or
                prep.get('input_copy_bytes') != (5533200 if copy_input else 0)):
            raise RuntimeError('INCOMPLETE_POISON_OR_INPUT_UPDATE')
        row['preparation'] = prep
        row['prepare_end_ns'] = self.clock()
        if self.stop.is_set():
            raise RuntimeError('STOP_BEFORE_SUBMIT') from self.error
        row['compute_begin_ns'] = self.clock()
        result = self.backend.compute(slot, frame_id, kind, self.stop)
        row['output_ready_ns'] = self.clock()
        self._deadline_check()
        if (result.starts != (1, 1, 1) or result.dones != (1, 1, 1) or
                len(result.module_ns) != 3 or any(v <= 0 for v in result.module_ns)):
            raise RuntimeError('INCOMPLETE_REAL_PIPELINE')
        row['module_ns'] = list(result.module_ns)
        row['starts'], row['dones'] = list(result.starts), list(result.dones)
        row['driver_stage_evidence'] = result.stage_evidence
        with self.cv:
            self.rows.append(row)
            self.next_id += 1
            # If checker STOP raced with completion, preserve the occupied slot.
            if self.stop.is_set():
                raise RuntimeError('STOP_WHILE_FRAME_IN_FLIGHT') from self.error
            self.states[slot] = 'READY'
            self.pending.append(row)
            self.cv.notify_all()

    def _drain(self):
        with self.cv:
            while any(state != 'FREE' for state in self.states) and not self.stop.is_set():
                self.cv.wait(timeout=1)
                self._deadline_check()
            if self.stop.is_set():
                raise RuntimeError('VALIDATION_STOP') from self.error

    def run(self, measured=120, warmup=6, budget_seconds=1800, join_seconds=5):
        if measured < 60 or warmup < 1:
            raise ValueError('AT_LEAST_60_MEASURED_FRAMES_AND_WARMUP_REQUIRED')
        if self.worker.ident is not None or self.closed:
            raise RuntimeError('ONE_SHOT_RUN_NO_RETRY')
        if not 0 < budget_seconds <= 1800 or not 0 <= join_seconds <= 5:
            raise ValueError('INVALID_FINITE_DEADLINE')
        self.deadline = self.clock()+int(budget_seconds*1e9)
        self.worker.start()
        phases = []
        try:
            for phase, copy_input in enumerate((False, True)):
                for _ in range(warmup):
                    self._one(phase, True, copy_input)
                self._drain()  # warm-up verification is outside the measured window
                first = len(self.rows)
                begin = self.clock()
                for _ in range(measured):
                    self._one(phase, False, copy_input)
                produced = self.rows[-1]['output_ready_ns']
                self._drain()
                validated = max(row['verify_end_ns'] for row in self.rows[first:])
                if not begin < produced <= validated:
                    raise RuntimeError('INVALID_CONTINUOUS_TIMING')
                phases.append(dict(phase=phase,copy_input=copy_input,warmup=warmup,
                                   measured=measured,begin_ns=begin,output_end_ns=produced,
                                   validation_end_ns=validated,
                                   observed_producer_fps=measured*1e9/(produced-begin),
                                   fully_validated_fps=measured*1e9/(validated-begin)))
            final = self.backend.final_audit()
            if final.get('immutable_inputs_models_golden_sha_ok') is not True or final.get('all_guards_ok') is not True:
                raise RuntimeError('FINAL_IMMUTABLE_OR_GUARD_AUDIT_FAILED')
            with self.cv:
                self.closed = True
                self.cv.notify_all()
            self.worker.join(timeout=join_seconds)
            self.worker_joined = not self.worker.is_alive()
            if not self.worker_joined:
                raise RuntimeError('VALIDATOR_NOT_JOINED')
            return dict(status='MEASUREMENT_EVIDENCE_PENDING_INDEPENDENT_BOARD_AUDIT',
                        BOARD_30FPS='NOT_TESTED',scope='INSTRUMENTED_MEMORY_Q14_DDR_TO_ENHANCED_DDR',
                        timing_source=getattr(self.clock,'source','MOCK_OR_UNBOUND_CLOCK'),
                        slots=self.slots,phases=phases,frames=self.rows,final_audit=final,
                        warning='Includes full-poison, checker contention and all ring waits. Slow validation alone cannot establish production hardware FAIL; service sums are diagnostics only.')
        except Exception as exc:
            self._fail(exc)
            with self.cv:
                self.closed = True
                self.cv.notify_all()
            self.worker.join(timeout=join_seconds)
            self.worker_joined = not self.worker.is_alive()
            if self.quarantine_error is not None:
                raise RuntimeError('DMA_PIN_REQUEST_NOT_CONFIRMED_UNSAFE_TERMINAL_STATE') from self.quarantine_error
            if self.abort_error is not None:
                raise RuntimeError('STOP_REQUEST_NOT_CONFIRMED_DMA_MUST_REMAIN_PINNED') from self.abort_error
            if not self.worker_joined:
                raise RuntimeError('VALIDATOR_NOT_JOINED_DMA_QUARANTINED') from exc
            raise
