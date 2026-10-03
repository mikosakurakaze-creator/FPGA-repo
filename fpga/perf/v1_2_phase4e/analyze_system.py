"""Validate the writer-only full CNN system gate and quantify residual barriers."""
import argparse
import collections
import csv
import hashlib
import json
import re
import statistics
from pathlib import Path

from prepare_system import ROOT, SHA


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def describe(values):
    if not values:
        return dict(n=0)
    return dict(n=len(values), min=min(values), max=max(values), median=statistics.median(values),
                mean=sum(values)/len(values), sum=sum(values))


def records(text, prefix):
    return [dict((k, int(v)) for k, v in re.findall(r'(\w+)=(-?\d+)', line))
            for line in text.splitlines() if line.startswith(prefix + ' ')]


def expected_writes():
    regions = json.loads((ROOT / 'buffer_map.json').read_text())['regions']
    result = {0: [], 1: [], 3: [], 4: []}
    for block in range(1, 8):
        output = block == 7
        base = regions['a_low0' if output else 'workspace']['base']
        slot = 0 if output else (block - 1) * 203520
        for band in range(15):
            for channel in range(3 if output else 32):
                for row in range(4):
                    address = base + 2 * (slot + channel * 6360 + (band*4+row)*106)
                    result[4 if output else 3].append((address//2, 106, block-1))
                    remaining = 212
                    while remaining:
                        count = min(remaining, 4096 - address % 4096)
                        result[1 if output else 0].append((address, count//4-1, block-1))
                        address += count
                        remaining -= count
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args()
    run = args.run
    assert not (run/'analysis.json').exists()
    manifest = json.loads((run/'run_manifest.json').read_text())
    assert manifest['config'] == dict(FRAMES=1, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2, DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128)
    frozen = manifest['original_source_manifest']
    for item in frozen['source_files']:
        assert SHA(Path(item['path'])) == item['sha256'], item['path']
    for item in manifest['substitutions']:
        assert SHA(Path(item['candidate'])) == item['candidate_sha256']
    for name, digest in manifest['protected_copies'].items():
        assert SHA(run/name) == digest, name
    assert SHA(run/'system_tb.sv') == manifest['generated_tb_sha256']
    exit_status = json.loads((run/'exit_status.json').read_text())
    assert exit_status['exit_code'] == 0
    assert SHA(run/'xsim.dir/phase4e_system/xsimk.exe')==exit_status['kernel_sha256']
    assert SHA(Path(exit_status['local_evidence']))==exit_status['local_evidence_sha256']
    text = (run/'system.log').read_text()
    assert 'FULL_CNN_NUMERICAL_PASS' in text and 'Fatal:' not in text
    launches=[line for line in text.splitlines() if line.startswith('# xsim ') and '-testplusarg ' in line]
    assert len(launches)==1
    launch=launches[0]
    for key,value in manifest['config'].items():
        assert re.findall(r'-testplusarg '+key+r'=(\d+)(?:\s|$)',launch)==[str(value)]
    runtime_ddr=records(text,'DDR_V2')[0]
    runtime_service=records(text,'DDR_SHARED')[0]
    assert runtime_ddr==dict(READ_OUTSTANDING=2,WRITE_OUTSTANDING=2)
    assert runtime_service['PERIOD']==1 and runtime_service['DELAY']==16
    hp_stats=records(text,'HP_STATS')
    assert len(hp_stats)==4
    assert (hp_stats[0]['AR'],hp_stats[0]['AW'],hp_stats[0]['R'],hp_stats[0]['W'],hp_stats[0]['WRITE_BYTES'])==(18345,12293,244440,163800,2480400)
    assert (hp_stats[1]['AR'],hp_stats[1]['AW'],hp_stats[1]['R'],hp_stats[1]['W'])==(83,0,1296,0)
    for hp in hp_stats[2:]:
        assert hp['AR']==hp['AW']==hp['R']==hp['W']==0
    stages = records(text, 'STAGE_FRAME')
    assert len(stages) == 1
    cnn = stages[0]
    assert cnn['STAGE'] == cnn['FRAME'] == cnn['MISMATCHES'] == 0
    assert cnn['SCALARS'] == 19080 and cnn['CYCLES'] == cnn['DONE'] - cnn['START']
    final = records(text, 'PHASE4E_CNN_FINAL')[0]
    assert final['FRAMES']==1 and final['SCALARS']==19080
    assert final['RAW_MISMATCHES']==final['GUARD_ERRORS']==final['HAZARD_ERRORS']==0
    assert final['GROUP_DRAINS']==final['WRITER_DRAINS']==7
    assert final['CREDIT_FINAL_WS']==final['CREDIT_FINAL_OUT']==0
    assert final['CREDIT_MAX_WS']<=2 and final['CREDIT_MAX_OUT']<=2
    stage_events = read_csv(run/'results/stage_events.csv')
    assert [(r['event'],int(r['stage']),int(r['frame']),int(r['cycle'])) for r in stage_events] == [('START',0,0,cnn['START']),('DONE',0,0,cnn['DONE'])]
    bus_events = read_csv(run/'results/write_events.csv')
    for row in bus_events:
        for k in ('cycle','bus','len','size','block'):
            row[k]=int(row[k])
        row['addr']=int(row['addr'],16)
    expected=expected_writes()
    buses={}
    for index,name in ((0,'workspace'),(1,'output'),(2,'hp0'),(3,'logical_workspace'),(4,'logical_output')):
        events=[r for r in bus_events if r['bus']==index]
        select=lambda kind:[r for r in events if r['event']==kind]
        aws=select('AW'); first=select('WFIRST'); last=select('ROW_DATA_END' if index>=3 else 'WLAST'); bs=select('B')
        assert len(aws)==len(first)==len(last)==len(bs)
        if index in expected:
            actual=[(r['addr'],r['len'],r['block']) for r in aws]
            assert actual==expected[index], (name,'address/length/order/block mismatch')
        for a,f,l,b in zip(aws,first,last,bs):
            assert a['cycle']<=f['cycle']<=l['cycle']<=b['cycle']
        occupancy=0;max_occupancy=0
        for event in events:
            if event['event']=='AW':occupancy+=1
            if event['event']=='B':occupancy-=1
            assert occupancy>=0
            max_occupancy=max(max_occupancy,occupancy)
        assert occupancy==0
        if index>=2:assert max_occupancy<=2
        logical_overlap=[b['cycle']>n['cycle'] for b,n in zip(bs,aws[1:]) if n['block']==b['block']]
        payload_overlap=[b['cycle']>n['cycle'] for b,n in zip(bs,first[1:]) if n['block']==b['block']]
        data_overlap=[b['cycle']>n['cycle'] for b,n in zip(bs,last[1:]) if n['block']==b['block']]
        buses[name]=dict(aw=len(aws),data_ends=len(last),b=len(bs),max_pending=max_occupancy,final_pending=occupancy,
                        address_interval=describe([n['cycle']-a['cycle'] for a,n in zip(aws,aws[1:]) if n['block']==a['block']]),
                        wlast_to_b=describe([b['cycle']-l['cycle'] for l,b in zip(last,bs)]),
                        next_write_starts_before_previous_b=sum(logical_overlap),
                        next_write_first_payload_before_previous_b=sum(payload_overlap),
                        next_write_data_end_before_previous_b=sum(data_overlap),
                        address_interval_by_block={str(block+1):describe([n['cycle']-a['cycle'] for a,n in zip(aws,aws[1:]) if a['block']==n['block']==block]) for block in sorted(set(a['block'] for a in aws))},
                        address_sequence_sha256=hashlib.sha256(json.dumps([(r['addr'],r['len'],r['block']) for r in aws]).encode()).hexdigest())
    assert buses['logical_workspace']['next_write_starts_before_previous_b']>0
    # DDR strict FIFO carries workspace then final A_low writes with one stream.
    source=[r for r in bus_events if r['event']=='AW' and r['bus'] in (0,1)]
    hp=[r for r in bus_events if r['event']=='AW' and r['bus']==2]
    assert len(source)==len(hp)
    for a,h in zip(source,hp):
        assert a['addr']==h['addr']
        assert h['len']+1==(a['addr']%16+(a['len']+1)*4+15)//16
    drains=read_csv(run/'results/block_drains.csv')
    assert sum(r['event']=='0' for r in drains)==sum(r['event']=='1' for r in drains)==7
    assert sum(r['event']=='3' for r in drains)==7 and sum(r['event']=='2' for r in drains)==1
    for event in ('0','1'):
        assert [int(r['block']) for r in drains if r['event']==event]==list(range(7))
    assert [int(r['block']) for r in drains if r['event']=='3']==list(range(-1,6))
    for row in drains:
        assert int(row['credit_ws'])==int(row['credit_out'])==int(row['ddr_wc'])==0
        assert row['ws_aw']==row['ws_wlast']==row['ws_b']
        assert row['out_aw']==row['out_wlast']==row['out_b']
    functions=read_csv(run/'results/function_events.csv')
    funcs={};completed=[]
    for index,name in manifest['function_map'].items():
        pending=None;durations=[]
        for row in functions:
            if row['function']!=index:continue
            if row['event']=='START':pending=row
            elif pending is not None:
                item=dict(function=name,block=int(pending['block']),start=int(pending['cycle']),done=int(row['cycle']))
                item['cycles']=item['done']-item['start'];durations.append(item);completed.append(item);pending=None
        funcs[name]=dict(completions=len(durations),active_elapsed=describe([d['cycles'] for d in durations]))
    blocks=[]
    for block in range(7):
        block_functions={r['function']:r for r in completed if r['block']==block}
        for name in ('group_block','output_writer','point_compute','output_packer'):
            assert name in block_functions, (block,name)
        writer=block_functions['output_writer'];compute=block_functions['point_compute'];group=block_functions['group_block']
        blocks.append(dict(block=block+1,group_start=group['start'],group_done=group['done'],group_cycles=group['cycles'],
                           writer_start=writer['start'],writer_done=writer['done'],writer_active_elapsed=writer['cycles'],
                           pw_compute_done=compute['done'],writer_after_compute_tail=writer['done']-compute['done'],
                           output_packer_done=block_functions['output_packer']['done']))
    credit_barrier=final['CREDIT_BARRIER_WS']+final['CREDIT_BARRIER_OUT']
    terminal=final['TERMINAL_DRAIN_WAIT']
    writer_elapsed=funcs['output_writer']['active_elapsed']['sum']
    delta=3421992-cnn['CYCLES']
    sufficient=delta>=88659 and cnn['CYCLES']<=3333333
    result=dict(conclusion='WRITE_RETIREMENT_FIX_SUFFICIENT' if sufficient else 'WRITE_RETIREMENT_FIX_INSUFFICIENT',
                stage_gate='CNN_SYSTEM_STAGE_30FPS_PASS' if sufficient else 'CNN_SYSTEM_STAGE_30FPS_FAIL',
                old_cycles=3421992,new_cycles=cnn['CYCLES'],saved_cycles=delta,remaining_gap=max(0,cnn['CYCLES']-3333333),
                numerical=dict(a_low_checked=19080,raw_mismatch=0,guard=0,hazard=0),
                runtime_config_verified=manifest['config'],
                hp_stats=hp_stats,
                final=final,buses=buses,blocks=blocks,functions=funcs,
                writer_barriers=dict(aw_capacity_credit2_cycles=credit_barrier,terminal_block_drain_cycles=terminal,
                                     writer_active_elapsed_sum=writer_elapsed,
                                     capacity_fraction_of_writer_active=credit_barrier/writer_elapsed,
                                     terminal_drain_fraction_of_writer_active=terminal/writer_elapsed,
                                     capacity_fraction_of_cnn=credit_barrier/cnn['CYCLES'],
                                     terminal_drain_fraction_of_cnn=terminal/cnn['CYCLES'],
                                     note='Observed overlapping activity fractions; they are not additive causal latency savings.'),
                frozen_original_sources_verified=len(frozen['source_files']),candidate_overlays_verified=3,
                protected_copies_verified=len(manifest['protected_copies']),
                evidence_sha256={p.name:SHA(p) for p in (run/'system.log',run/'run_manifest.json',run/'system.prj',run/'exit_status.json',run/'results/write_events.csv',run/'results/function_events.csv',run/'results/block_drains.csv')})
    (run/'analysis.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('conclusion','stage_gate','old_cycles','new_cycles','saved_cycles','remaining_gap','numerical','writer_barriers')}))


if __name__ == '__main__':
    main()
