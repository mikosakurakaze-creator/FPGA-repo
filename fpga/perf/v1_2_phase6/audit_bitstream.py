"""Gate natural bitstream completion and unchanged Phase5 route/timing/DRC."""
import sys
sys.dont_write_bytecode=True
import collections, datetime, json, re
from pathlib import Path
OUT=Path(__file__).resolve().parent
REPO=Path('E:/github/-')
BASE=Path('E:/HLS/kv260_three_module_v1_2_phase4')
IMPL=BASE/'phase4g/integration_01/project/v12_wc.runs/impl_1'
sys.path.insert(0,str(OUT))
from prepare import sha,save,stamp,after
sys.path.insert(0,str(REPO/'fpga/perf/v1_2_phase5'))
from analyze_implementation import timing_summary,drc_report,route_report,clock_report

exit_record=json.loads((OUT/'bitstream_exit_status.json').read_text())
assert exit_record['returncode']==0 and exit_record['natural_process_exit'] and not exit_record['forced_termination']
status=dict(line.split('\t',1) for line in (OUT/'reports/run_status.tsv').read_text().splitlines()[1:])
assert status['IMPL_INITIAL_STATUS']=='route_design Complete!' and status['IMPL_NEEDS_REFRESH']=='0'
assert status['IMPL_STATUS']=='write_bitstream Complete!' and status['IMPL_PROGRESS']=='100%'
assert status['NATURAL_BITSTREAM_END']==status['POSTBIT_REPORTS_COMPLETE']==status['ROUTED_WRITECREDIT_HIERARCHY']=='PASS'
assert status['FORMAL_CNN_REVISION']=='2114810448'
for n in ('.write_bitstream.end.rst','.vivado.end.rst'): assert (IMPL/n).is_file()
for n in ('.write_bitstream.error.rst','.vivado.error.rst'): assert not (IMPL/n).exists()
bit=Path(status['BIT_PATH']); assert bit.is_file() and bit.stat().st_size==int(status['BIT_BYTES'])>0
oldlog=(OUT/'impl_before_runme.log').read_bytes()
all_runlog=(IMPL/'runme.log').read_bytes()
assert all_runlog.startswith(oldlog), 'Phase5 run log prefix changed'
runlog=all_runlog[len(oldlog):].decode('utf-8')
(OUT/'bitstream_run_only.log').write_text(runlog,encoding='utf-8')
assert 'write_bitstream completed successfully' in runlog
assert not re.search(r'^\s*(opt_design|place_design|phys_opt_design|route_design) completed successfully',runlog,re.M), 'Earlier implementation stage reran'
logs={}
for p in (OUT/'bitstream_console.log', OUT/'bitstream_vivado.log',IMPL/'runme.log'):
    t=runlog if p==IMPL/'runme.log' else p.read_text(); err=re.findall(r'^ERROR:.*$',t,re.M); crit=re.findall(r'^CRITICAL WARNING:.*$',t,re.M)
    assert not err and not crit, (str(p),err,crit)
    logs[p.as_posix()]=dict(errors=err,critical_warnings=crit,warning_count=len(re.findall(r'^WARNING:',t,re.M)))
timing=timing_summary((OUT/'reports/postbit_timing_summary.rpt').read_text())
p5=json.loads((BASE/'phase5/implementation_01/implementation_gate.json').read_text())
assert timing==p5['post_route_timing'], (timing,p5['post_route_timing'])
drc=drc_report((OUT/'reports/postbit_drc.rpt').read_text())
assert drc['severity_totals']['Error']==drc['severity_totals']['Critical Warning']==0
assert drc['rules']==p5['drc']['rules'], 'DRC rule/severity/count changed'
old_details={(d['rule'],d['index']):d for d in p5['drc']['details']}
new_details={(d['rule'],d['index']):d for d in drc['details']}
drc_detail_delta=[dict(rule=k[0],index=k[1],before=old_details.get(k),after=new_details.get(k)) for k in old_details.keys()|new_details.keys() if old_details.get(k)!=new_details.get(k)]
for delta in drc_detail_delta:
    assert (delta['rule'],delta['index'])==('RTSTAT-10',1)
    for d in (delta['before'],delta['after']):
        assert d['severity']=='Warning' and '20 net(s) have no routable loads.' in d['detail']
        assert '(the first 15 of 20 listed nets/buses).' in d['detail'] and 'Related violations: <none>' in d['detail']
        names=re.findall(r'system_i/[^,\s]+',d['detail'])
        assert len(names)==15 and all(re.fullmatch(r'system_i/axi_control/inst/(m\d\d|s\d\d)_nodes/(m\d\d|s\d\d)_[a-z]+_node/inst/mi_handler_m_sc_areset_pipe',n) for n in names)
save('drc_detail_comparison.json',dict(status='PASS',identical_detail_count=198-len(drc_detail_delta),rules_and_severity_totals_identical=True,preview_differences=drc_detail_delta,limitation='RTSTAT-10 report displays only 15 of 20 nets; displayed selection changed after DCP reload. Full 20-net set is not claimed separately compared; the routed DCP is byte-identical and no new Error/Critical Warning exists.'))
route=route_report((OUT/'reports/postbit_route_status.rpt').read_text(),(OUT/'impl_before_runme.log').read_text())
assert route==p5['routing']
clock=clock_report((OUT/'reports/postbit_clocks.rpt').read_text())
assert clock['period_ns']==10.0
after()
result=dict(status='BITSTREAM_PASS',generated_at=stamp(),natural_exit=exit_record,run_status=status,log_audit=logs,
 bitstream=dict(path=bit.as_posix(),bytes=bit.stat().st_size,sha256=sha(bit),generated_at=datetime.datetime.fromtimestamp(bit.stat().st_mtime,datetime.timezone(datetime.timedelta(hours=8))).isoformat()),
 timing=timing,phase5_timing_identical=True,drc_severity_totals=drc['severity_totals'],phase5_drc_rules_totals_identical=True,drc_detail_preview_differences=drc_detail_delta,
 route=route,clock=clock,implementation_rerun=False,protection='PASS')
save('bitstream_gate.json',result)
print('PHASE6_BITSTREAM_GATE=PASS',json.dumps(result['bitstream']),flush=True)
