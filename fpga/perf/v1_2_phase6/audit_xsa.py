"""Inspect actual XSA ZIP, HWH topology/map, embedded bit and driver payloads."""
import sys
sys.dont_write_bytecode=True
import datetime,hashlib,json,re,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
OUT=Path(__file__).resolve().parent
REPO=Path('E:/github/-'); BASE=Path('E:/HLS/kv260_three_module_v1_2_phase4')
sys.path.insert(0,str(OUT))
from prepare import sha,save,stamp,after
exit_record=json.loads((OUT/'export_xsa_exit_status.json').read_text(encoding='utf-8'))
assert exit_record['returncode']==0 and exit_record['natural_process_exit'] and not exit_record['forced_termination']
log=(OUT/'export_xsa_console.log').read_text(encoding='utf-8')
assert 'PHASE6_XSA_EXPORT_COMPLETE=PASS' in log
for p in (OUT/'export_xsa_console.log',OUT/'export_xsa_vivado.log'):
    t=p.read_text(encoding='utf-8'); assert not re.findall(r'^(?:ERROR|CRITICAL WARNING):.*$',t,re.M)
xsa=OUT/'kv260_three_module_v1_2_writecredit.xsa'; assert xsa.is_file()
bit=json.loads((OUT/'bitstream_gate.json').read_text())['bitstream']
old=json.loads((REPO/'fpga/docs/v1_1_hw_register_map.json').read_text())
with zipfile.ZipFile(xsa) as z:
    assert z.testzip() is None, 'ZIP CRC failed'
    names=z.namelist(); assert len(names)==len(set(names)), 'duplicate entries'
    bits=[n for n in names if n.lower().endswith('.bit')]
    assert len(bits)==1
    content=z.read(bits[0]); digest=hashlib.sha256(content).hexdigest()
    assert len(content)==bit['bytes'] and digest==bit['sha256'] and sha(bit['path'])==digest
    hwhs=[n for n in names if Path(n).name=='system.hwh']; assert len(hwhs)==1
    hwh=z.read(hwhs[0]); root=ET.fromstring(hwh)
    assert root.get('VIVADOVERSION')=='2025.2'
    original=BASE/'phase4g/integration_01/project/v12_wc.gen/sources_1/bd/system/hw_handoff/system.hwh'
    assert hwh==original.read_bytes(), 'Exported HWH differs from protected formal generated HWH'
    modules={m.get('INSTANCE'):m for m in root.findall('./MODULES/MODULE')}
    expected={'zynq_ultra_ps_e_0':'zynq_ultra_ps_e','rst_ps_100m':'proc_sys_reset','zero_dce_cnn_top_0':'zero_dce_cnn_top','bilinear_fixed16_buffered_0':'bilinear_fixed16_buffered','curve_image_fixed16_0':'curve_image_fixed16'}
    for n in ('axi_control','cnn_data_sc','cnn_model_sc','bilinear_ddr_sc','curve_ddr_sc'): expected[n]='smartconnect'
    for n,typ in expected.items(): assert n in modules and modules[n].get('MODTYPE')==typ,(n,typ)
    cnn=modules['zero_dce_cnn_top_0']; assert cnn.get('COREREVISION')=='2114810448' and cnn.get('VLNV')=='xilinx.com:hls:zero_dce_cnn_top:1.0'
    ps=modules['zynq_ultra_ps_e_0']; ranges={r.get('INSTANCE'):r for r in ps.findall('.//MEMRANGE')}
    registers={}; drivers={}
    for key,ip in old['ips'].items():
        module=modules[ip['instance']]; assert module.get('VLNV')==ip['vlnv']
        mr=ranges[ip['instance']]; assert mr.get('MASTERBUSINTERFACE')=='M_AXI_HPM0_FPD'
        assert int(mr.get('BASEVALUE'),0)==int(ip['base_address'],0) and int(mr.get('HIGHVALUE'),0)-int(mr.get('BASEVALUE'),0)+1==65536
        regs={r.get('NAME'):{p.get('NAME'):p.get('VALUE') for p in r.findall('./PROPERTY')} for r in module.findall('.//REGISTER')}
        for n,offset in {'CTRL':0,'GIER':4,'IP_IER':8,'IP_ISR':12}.items(): assert int(regs[n]['ADDRESS_OFFSET'])==offset and int(regs[n]['SIZE'])==32
        for n,r in ip['pointer_registers'].items():
            for suffix,offset in [('_1',r['offset_low']),('_2',r['offset_high'])]:
                d=regs[n+suffix]; assert int(d['ADDRESS_OFFSET'])==offset and int(d['SIZE'])==32 and d['ACCESS']=='write-only'
        for n,r in ip['scalar_registers'].items():
            # Generated headers/HWH escape C++ reserved names with _r.
            d=regs[n if n in regs else n+'_r']; assert int(d['ADDRESS_OFFSET'])==r['offset'] and int(d['SIZE'])==32 and d['ACCESS']=='write-only'
        registers[key]=regs
        pkg=BASE/'phase4g/ip_primary_05' if key=='cnn' else BASE/'phase4g/integration_01/stable_ip_repo'/key
        header=next(pkg.glob('drivers/*/src/*hw.h'))
        entries=[n for n in names if Path(n).name==header.name]; assert len(entries)==1
        header_content=z.read(entries[0]); assert header_content==header.read_bytes()
        drivers[key]=dict(entry=entries[0],source_path=header.as_posix(),bytes=len(header_content),sha256=hashlib.sha256(header_content).hexdigest())
    def ports(n):return {p.get('NAME'):p.attrib for p in modules[n].findall('./PORTS/PORT')}
    def buses(n):return {p.get('NAME'):p.attrib for p in modules[n].findall('./BUSINTERFACES/BUSINTERFACE')}
    clock=ports('zynq_ultra_ps_e_0')['pl_clk0']; signal=clock['SIGNAME']; freq=int(clock['CLKFREQUENCY'])
    assert freq==99999001
    for n in ('zero_dce_cnn_top_0','bilinear_fixed16_buffered_0','curve_image_fixed16_0'):
        p=ports(n); assert p['ap_clk']['SIGNAME']==signal and int(p['ap_clk']['CLKFREQUENCY'])==freq
        assert p['ap_rst_n']['SIGNAME']=='rst_ps_100m_peripheral_aresetn' and p['ap_rst_n']['POLARITY']=='ACTIVE_LOW'
    for n in ('axi_control','cnn_data_sc','cnn_model_sc','bilinear_ddr_sc','curve_ddr_sc'):
        p=ports(n); assert p['aclk']['SIGNAME']==signal and p['aresetn']['SIGNAME']=='rst_ps_100m_interconnect_aresetn'
    rst=ports('rst_ps_100m'); assert rst['slowest_sync_clk']['SIGNAME']==signal and rst['ext_reset_in']['SIGNAME']==ports('zynq_ultra_ps_e_0')['pl_resetn0']['SIGNAME']
    assert rst['ext_reset_in']['POLARITY']=='ACTIVE_LOW'
    def joined(m1,b1,m2,b2): assert buses(m1)[b1]['BUSNAME']==buses(m2)[b2]['BUSNAME'],(m1,b1,m2,b2)
    for axi,sc,si in [('gmem_input','cnn_data_sc','S00_AXI'),('gmem_output','cnn_data_sc','S01_AXI'),('gmem_workspace','cnn_data_sc','S02_AXI'),('gmem8','cnn_model_sc','S00_AXI'),('gmem32','cnn_model_sc','S01_AXI'),('gmem_lut','cnn_model_sc','S02_AXI')]:joined('zero_dce_cnn_top_0','m_axi_'+axi,sc,si)
    for hp,sc in enumerate(('cnn_data_sc','cnn_model_sc','bilinear_ddr_sc','curve_ddr_sc')): joined(sc,'M00_AXI','zynq_ultra_ps_e_0','S_AXI_HP'+str(hp)+'_FPD')
    for instance,sc,axes in [('bilinear_fixed16_buffered_0','bilinear_ddr_sc',['gmem_input','gmem_output']),('curve_image_fixed16_0','curve_ddr_sc',['gmem_input','gmem_parameter','gmem_output'])]:
        for i,axi in enumerate(axes):joined(instance,'m_axi_'+axi,sc,'S0'+str(i)+'_AXI')
    joined('zynq_ultra_ps_e_0','M_AXI_HPM0_FPD','axi_control','S00_AXI')
    for i,n in enumerate(('zero_dce_cnn_top_0','bilinear_fixed16_buffered_0','curve_image_fixed16_0')):joined('axi_control','M0'+str(i)+'_AXI',n,'s_axi_control')
    # Artifact inventory is the actual ZIP, not a list inferred from source packages.
    inventory=[dict(entry=n,bytes=z.getinfo(n).file_size,compressed_bytes=z.getinfo(n).compress_size,sha256=hashlib.sha256(z.read(n)).hexdigest()) for n in names if not n.endswith('/')]
after()
result=dict(status='XSA_PASS',generated_at=stamp(),natural_exit=exit_record,
 xsa=dict(path=xsa.as_posix(),bytes=xsa.stat().st_size,sha256=sha(xsa),generated_at=datetime.datetime.fromtimestamp(xsa.stat().st_mtime,datetime.timezone(datetime.timedelta(hours=8))).isoformat()),
 embedded_bitstream=dict(entry=bits[0],bytes=len(content),sha256=digest,identical_to_external_bitstream=True),zip_crc='PASS',
 hwh=dict(entry=hwhs[0],sha256=hashlib.sha256(hwh).hexdigest(),matches_protected_project_hwh=True,vivado_version=root.get('VIVADOVERSION'),formal_cnn_revision=2114810448),
 hwh_clock_frequency_hz=freq,clock_signal=signal,modules={n:modules[n].attrib for n in expected},registers=registers,
 control_addresses={key:ip['base_address'] for key,ip in old['ips'].items()},driver_headers=drivers,topology='PASS',inventory=inventory,protection='PASS')
save('xsa_gate.json',result)
print('PHASE6_XSA_GATE=PASS',json.dumps(result['xsa']),flush=True)
