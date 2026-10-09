"""Offline statistics; never turns Host mock or unaudited reports into board PASS."""
import math

def distribution(values):
    if not values or any(v<0 for v in values):raise ValueError('INVALID_DURATIONS')
    v=sorted(values)
    percentile=lambda p:v[max(0,math.ceil(len(v)*p)-1)]
    return {'mean_ns':sum(v)/len(v),'max_ns':v[-1],
            'p95_ns':percentile(.95),'p99_ns':percentile(.99)}

def analyze(report):
    result={'BOARD_30FPS':'NOT_TESTED','status':'OFFLINE_DIAGNOSTICS_NEEDS_INDEPENDENT_BOARD_PROVENANCE',
            'timing_source':report['timing_source'],'phases':[]}
    rows=report['frames']
    if (report['final_audit'].get('immutable_inputs_models_golden_sha_ok') is not True or
            report['final_audit'].get('all_guards_ok') is not True):raise ValueError('FINAL_AUDIT_FAILED')
    if ([p['phase'] for p in report['phases']]!=[0,1] or
            any(p['copy_input']!=(p['phase']==1) or p['warmup']<1 or p['measured']<60 for p in report['phases']) or
            len(rows)!=sum(p['measured']+p['warmup'] for p in report['phases'])):
        raise ValueError('TOTAL_PHASE_OR_FRAME_COUNT_MISMATCH')
    if report['slots'] not in (3,5,7):raise ValueError('INVALID_RING_SIZE')
    expected=[(p['phase'],warm) for p in report['phases'] for warm,n in ((True,p['warmup']),(False,p['measured'])) for _ in range(n)]
    if [(v['phase'],v['warmup']) for v in rows]!=expected:raise ValueError('PHASE_SEQUENCE_MISMATCH')
    if [v['id'] for v in rows]!=list(range(len(rows))):raise ValueError('FRAME_ID_GAP_OR_REPLAY')
    if any(v['slot']!=v['id']%report['slots'] or v['kind']!=v['id']%2 for v in rows):
        raise ValueError('INPUT_OR_SLOT_REPLAY')
    last_slot={}
    for v in rows:
        times=[v[k] for k in ('before_wait_ns','prepare_begin_ns','prepare_end_ns','compute_begin_ns','output_ready_ns','verify_begin_ns','verify_end_ns')]
        if any(type(n) is not int or n<0 for n in times) or times!=sorted(times):
            raise ValueError('INVALID_FRAME_TIMING')
        if (len(v['module_ns'])!=3 or any(type(n) is not int or n<=0 for n in v['module_ns']) or
                sum(v['module_ns'])>v['output_ready_ns']-v['compute_begin_ns']):
            raise ValueError('INVALID_MODULE_WINDOWS')
        if v['prepare_begin_ns']<last_slot.get(v['slot'],0):raise ValueError('SLOT_REUSED_BEFORE_VALIDATION')
        last_slot[v['slot']]=v['verify_end_ns']
        q=v['preparation'];c=v['verification']
        if (not v['verified'] or q.get('full_output_poison_bytes')!=11028240 or
            q.get('input_kind')!=v['kind'] or q.get('input_copy_bytes')!=(5533200 if v['phase']==1 else 0) or
            c.get('compared_scalars')!=5514120 or c.get('mismatches')!=0 or
            c.get('slot_guard_bytes')!=384 or c.get('guard_errors')!=0 or
            v['starts']!=[1,1,1] or v['dones']!=[1,1,1]):raise ValueError('FRAME_RECEIPT_INCOMPLETE')
    for p in report['phases']:
        if len([v for v in rows if v['phase']==p['phase'] and v['warmup']])!=p['warmup']:
            raise ValueError('WARMUP_COUNT_MISMATCH')
        r=[v for v in rows if v['phase']==p['phase'] and not v['warmup']]
        w=[v for v in rows if v['phase']==p['phase'] and v['warmup']]
        if max(v['verify_end_ns'] for v in w)>p['begin_ns']:raise ValueError('WARMUP_INSIDE_MEASURED_WINDOW')
        if len(r)!=p['measured'] or len(r)<60 or not all(v['verified'] for v in r):
            raise ValueError('FRAME_COUNT_OR_VALIDATION_INCOMPLETE')
        intervals=[b['output_ready_ns']-a['output_ready_ns'] for a,b in zip(r,r[1:])]
        if any(v<=0 for v in intervals):raise ValueError('NONMONOTONIC_OUTPUT_SEQUENCE')
        if not p['begin_ns']<p['output_end_ns']<=p['validation_end_ns']:
            raise ValueError('INVALID_CONTINUOUS_TIMING')
        if not (p['begin_ns']<=r[0]['before_wait_ns'] and r[-1]['output_ready_ns']==p['output_end_ns'] and max(v['verify_end_ns'] for v in r)==p['validation_end_ns']):
            raise ValueError('CONTINUOUS_WINDOW_MISMATCH')
        output_fps=len(r)*1e9/(p['output_end_ns']-p['begin_ns'])
        validated_fps=len(r)*1e9/(p['validation_end_ns']-p['begin_ns'])
        rolling=[29e9/(r[i+29]['output_ready_ns']-r[i]['output_ready_ns']) for i in range(len(r)-29)]
        result['phases'].append({'phase':p['phase'],'frames':len(r),'warmup':p['warmup'],
            'producer_fps':output_fps,'fully_validated_fps':validated_fps,
            'minimum_30_output_window_fps':min(rolling),
            'output_interval':distribution(intervals),
            'wait':distribution([v['prepare_begin_ns']-v['before_wait_ns'] for v in r]),
            'prepare_including_full_poison_and_optional_input_copy':distribution([v['prepare_end_ns']-v['prepare_begin_ns'] for v in r]),
            'serial_compute_observed':distribution([v['output_ready_ns']-v['compute_begin_ns'] for v in r]),
            'module_observed':[distribution([v['module_ns'][i] for v in r]) for i in range(3)],
            'verification':distribution([v['verify_end_ns']-v['verify_begin_ns'] for v in r]),
            'frame_to_output_latency':distribution([v['output_ready_ns']-v['before_wait_ns'] for v in r]),
            'frame_to_validated_latency':distribution([v['verify_end_ns']-v['before_wait_ns'] for v in r]),
            'measured_starts':sum(sum(v['starts']) for v in r),
            'limitation':'Test poison/checker contention included. No subtraction or stitching of service intervals; no isolated PL arithmetic/DDR-stall claim.'})
    result['all_frame_module_starts']=[sum(v['starts'][i] for v in rows) for i in range(3)]
    result['all_frame_module_dones']=[sum(v['dones'][i] for v in rows) for i in range(3)]
    return result
