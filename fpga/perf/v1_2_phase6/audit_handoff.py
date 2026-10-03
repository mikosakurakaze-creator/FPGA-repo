"""Final gate binds documented artifacts, actual ABI, evidence and protected inputs."""
import sys
sys.dont_write_bytecode=True
import json,re,zipfile
from pathlib import Path
OUT=Path(__file__).resolve().parent; REPO=Path('E:/github/-')
sys.path.insert(0,str(OUT))
from prepare import sha,save,stamp,after,git
bit=json.loads((OUT/'bitstream_gate.json').read_text())
xsa=json.loads((OUT/'xsa_gate.json').read_text())
m=json.loads((REPO/'fpga/docs/v1_2_hw_register_map.json').read_text(encoding='utf-8'))
assert bit['status']=='BITSTREAM_PASS' and xsa['status']=='XSA_PASS'
assert m['status']=='V1_2_HW_HANDOFF_READY'
expected={k:'PASS' for k in ('CNN_RTL_30FPS','SHORT_MULTI_FRAME_30FPS','IMPLEMENTABLE_CNN_IP','POST_ROUTE_100MHZ','BITSTREAM_XSA')};expected['BOARD_30FPS']='NOT_TESTED'
assert m['state']==expected
assert m['part']=='xck26-sfvc784-2LV-c' and m['vivado_version']=='2025.2'
assert m['clock']['nominal_frequency_hz']==100000000 and m['clock']['period_ns']==10 and m['clock']['hwh_frequency_hz']==99999001
for k,a in [('bitstream',bit['bitstream']),('xsa',xsa['xsa'])]:
    assert m['artifacts'][k]==a and sha(a['path'])==a['sha256'] and Path(a['path']).stat().st_size==a['bytes']
assert m['artifacts']['embedded_bitstream']==xsa['embedded_bitstream']
for key,ip in m['ips'].items():
    assert ip['base_address']==xsa['control_addresses'][key] and ip['range_bytes']==65536
    assert ip['xsa_driver_header_sha256']==xsa['driver_headers'][key]['sha256']==sha(ip['driver_header']['path'])
    header=Path(ip['driver_header']['path']).read_text(encoding='utf-8')
    for n,r in ip['pointer_registers'].items():
        assert r['width_bits']==64 and r['offset_high']==r['offset_low']+4 and r['word_width_bits']==32
        matches=re.findall(r'^#define\s+\S*_ADDR_'+n.upper()+r'_DATA\s+(0x[0-9a-fA-F]+)\s*$',header,re.M)
        assert len(matches)==1 and int(matches[0],0)==r['offset_low'],(key,n)
        for suffix,off in [('_1',r['offset_low']),('_2',r['offset_high'])]:assert int(xsa['registers'][key][n+suffix]['ADDRESS_OFFSET'])==off
release=m['cnn_release']; assert release['revision']==2114810448 and release['identity_sha256']=='a64d16faa3c102790eae873031da99cd775b6858f673ff8d4d8f7c92d17572e9'
for key in ('component','source_manifest','build_manifest'):assert sha(release[key]['path'])==release[key]['sha256']
for evidence in release['frozen_sources']+m['fixed_point_protocol']['references']:assert sha(evidence['path'])==evidence['sha256']
buffers=m['ddr']['buffers']; workspace=buffers['WORKSPACE_INT16']
assert workspace['bytes']==2442240 and workspace['elements']==1221120 and workspace['slot_fractional_bits']==[14,14,14,12,13,14]
assert workspace['slot_byte_offsets']==[i*407040 for i in range(6)]
expected_sizes={'INPUT_Q14':38160,'WEIGHTS_INT8':10075,'BIAS_INT32':1944,'WEIGHT_FRAC':486,'TANH_LUT_Q15':8194,'A_LOW_Q14':38160,'WORKSPACE_INT16':2442240,'A_FULL_Q14':5495040,'MODEL_INPUT_Q14':5495040,'ENHANCED_Q14':5495040}
assert {k:v['bytes'] for k,v in buffers.items()}==expected_sizes
for p in buffers.values():
    if 'payload' in p:assert sha(p['payload']['path'])==p['payload']['sha256'] and Path(p['payload']['path']).stat().st_size==p['bytes']
for phase in ('phase4f','phase5'):
    for k,e in m['evidence'][phase].items():
        if isinstance(e,dict) and 'sha256' in e:assert sha(e['path'])==e['sha256']
written=json.loads((OUT/'documents_written.json').read_text(encoding='utf-8'))
for doc in written['files']:
    assert sha(doc['path'])==doc['sha256']
    if Path(doc['path']).suffix=='.md':
        text=Path(doc['path']).read_text(encoding='utf-8')
        assert 'V1_2_HW_HANDOFF_READY' in text and 'NOT_TESTED' in text
        assert not re.search(r'BOARD_30FPS\s*[=:|]\s*(?:\*\*)?PASS',text)
        for art in (bit['bitstream'],xsa['xsa']):assert art['path'] in text and art['sha256'] in text and f"{art['bytes']:,}" in text
after()
protection=json.loads((OUT/'protection_after.json').read_text())
checks={k:'PASS' for k in ('natural_bitstream','postbit_timing_equal_phase5','no_new_error_critical','xsa_include_bit','zip_crc','embedded_bit_hash_equal','artifact_sha_size','hwh_modules_revision_clock_reset_topology','control_address_map','formal_driver_abi','ddr_payload_layout','fixed_protocol_reference','historical_evidence_preserved','source_protection','handoff_documents_complete','git_no_mutation')}
result=dict(status='V1_2_HW_HANDOFF_READY',generated_at=stamp(),checks=checks,state=expected,bitstream=bit['bitstream'],xsa=xsa['xsa'],embedded_bitstream=xsa['embedded_bitstream'],documents=written['files'],protection=dict(status=protection['status'],checked_count=protection['count'],only_named_reference_order_changes=protection['generated_synthesis_index_audit']),next_step='WAIT MASTER; no board test or PS software in this batch.')
save('handoff_gate.json',result)
save('finalization.json',dict(status='V1_2_HW_HANDOFF_READY',generated_at=stamp(),handoff_gate_sha256=sha(OUT/'handoff_gate.json'),files=written['files']))
print('PHASE6_FINAL_GATE=V1_2_HW_HANDOFF_READY',flush=True)
