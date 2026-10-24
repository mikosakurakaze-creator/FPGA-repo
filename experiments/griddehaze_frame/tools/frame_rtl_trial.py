"""Drive the exact exported frame RTL using bounded, stalled AXI memories."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
from preflight import ROOT, audit, sha, save
from emit_model import layout
from ddr_fixture import frame_fixture

CODE_ROOT=Path(__file__).resolve().parents[1]


def main():
    tracked_sources={
        'frame_rtl_trial.py':Path(__file__).resolve(),
        'preflight.py':Path(__file__).with_name('preflight.py').resolve(),
        'emit_model.py':Path(__file__).with_name('emit_model.py').resolve(),
        'ddr_fixture.py':Path(__file__).with_name('ddr_fixture.py').resolve(),
        'frame_axi_test.sv':CODE_ROOT/'system/frame_axi_test.sv',
        'axi_bounded_memory.sv':CODE_ROOT/'system/axi_bounded_memory.sv',
    }
    source_hash_at_start={name:sha(path) for name,path in tracked_sources.items()}
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--synth',type=Path,required=True)
    p.add_argument('--case',default='size_4x4')
    p.add_argument('--golden',type=Path,help='explicit independently generated Golden directory using the frozen package')
    p.add_argument('--netlist',type=Path,help='actual exported functional core netlist; final-output check only')
    p.add_argument('--physical-system',type=Path,help='actual complete system functional netlist; replay original SmartConnect and PS boundary')
    p.add_argument('--netlist-top',default='system_griddehaze_frame_top_0_0')
    p.add_argument('--netlist-kind',choices=['post_synth_functional','post_route_functional'],default='post_synth_functional')
    p.add_argument('--probe-cycles',type=int,default=0,help='bounded diagnostic only; never produces a passing numerical-regression result')
    p.add_argument('--timeout-seconds',type=int,default=86400,help='wall-time limit per simulator invocation; gate-level full graph can require an overnight run')
    p.add_argument('--max-frame-cycles',type=int,default=200000000,help='simulation watchdog per frame, not a measured latency; total watchdog covers both cold and warm frames')
    p.add_argument('--vivado',type=Path,default=Path('D:/vivado/2025.2/Vivado'))
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    if a.netlist and a.physical_system:raise ValueError('Choose a core netlist or physical system')
    if a.probe_cycles and not 10000<=a.probe_cycles<=1000000:raise ValueError('Probe cycles must be 10000..1000000')
    if not 60<=a.timeout_seconds<=172800:raise ValueError('Simulator timeout must be 60..172800 seconds')
    if not 10000<=a.max_frame_cycles<=900000000:raise ValueError('Frame cycle budget must be 10000..900000000 to keep the signed cycle counter in range')
    netlist_mode=bool(a.netlist or a.physical_system)
    report=dict(pass_result=False,kind='independent_full_graph_axi_rtl',case=a.case,
                scope='exported RTL plus simulated AXI RAM; not PS, routed circuit or board')
    report.update(frame_cycle_budget=a.max_frame_cycles,total_cycle_budget=2*a.max_frame_cycles+1000000)
    if netlist_mode:
        report.update(kind=a.netlist_kind,scope='actual functional core netlist; final outputs and CSR only; simulated AXI RAM, no SDF, PS or board')
    def run(cmd,name):
        print('RTL_STAGE='+name+' LOG='+str(out/(name+'.log')),flush=True)
        start=time.perf_counter()
        with (out/(name+'.log')).open('wb') as f:
            r=subprocess.run(list(map(str,cmd)),cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=a.timeout_seconds)
        report.setdefault('steps',{})[name]=dict(exit_code=r.returncode,seconds=time.perf_counter()-start,log_sha256=sha(out/(name+'.log')))
        if r.returncode:raise RuntimeError(name+' process failed')
        return (out/(name+'.log')).read_text(encoding='utf-8',errors='replace')
    try:
        synth=json.loads((a.synth/'result.json').read_text(encoding='utf-8'))
        if not synth['pass_result']:raise RuntimeError('HLS synthesis not passed')
        rtl=a.synth/'component/hls/impl/ip/hdl/verilog'
        report['rtl_sha256']={f.name:sha(f) for f in rtl.iterdir() if f.is_file()}
        for f in rtl.iterdir():
            if f.is_file() and (not netlist_mode or f.suffix=='.dat'):shutil.copy2(f,out/f.name)
        if a.netlist:
            shutil.copy2(a.netlist,out/'core_netlist.v')
            report['netlist_sha256']=sha(a.netlist)
        m,g,params,_=audit(ROOT/'a_candidate/package')
        golden=a.golden.resolve() if a.golden else ROOT/'a_candidate/golden'/a.case
        meta=json.loads((golden/'report.json').read_text(encoding='utf-8'))
        if meta['manifest_sha256']!=sha(ROOT/'a_candidate/package/manifest.json'):raise RuntimeError('Golden package identity mismatch')
        if [n['id'] for n in meta['nodes']]!=[n['id'] for n in g['nodes']]:raise RuntimeError('Golden graph node sequence differs')
        report.update(case=golden.name,golden_report_sha256=sha(golden/'report.json'),golden_source=str(golden))
        h,w=meta['input_shape'][-2:]
        memory=layout(out/'layout.bin',h,w)
        save(out/'memory.json',memory)
        image=memory['input_bytes'];scratch=memory['scratch_bytes']
        fixture=frame_fixture(image,scratch,m['blob_nbytes'])
        save(out/'ddr_fixture.json',fixture)
        report['ddr_fixture_sha256']=sha(out/'ddr_fixture.json')
        feature_base=fixture['feature_base'];parameter_base=fixture['parameter_base']
        input_at=fixture['input_at'];output_at=fixture['output_at'];scratch_at=fixture['scratch_at']
        feature_bytes=fixture['feature_bytes'];layout_at=fixture['layout_at']
        parameter_capacity=fixture['parameter_capacity']
        def hexwords(path,data,offset=0):
            if len(data)%4: data+=bytes(4-len(data)%4)
            path.write_text('@'+format(offset//4,'x')+'\n'+''.join(f'{v:08x}\n' for v in struct.unpack('<'+'I'*(len(data)//4),data)),encoding='ascii')
        hexwords(out/'feature.hex',(golden/'input.raw').read_bytes(),input_at)
        hexwords(out/'parameter.hex',(ROOT/'a_candidate/package/parameters.bin').read_bytes())
        temp=out/'layout.hex';hexwords(temp,(out/'layout.bin').read_bytes(),layout_at)
        with (out/'parameter.hex').open('a',encoding='ascii') as f:f.write(temp.read_text())
        starts=[];counts=[];addresses=[];expected=[];total=0
        with (out/'golden.hex').open('w',encoding='ascii') as f:
            for n,r in zip(meta['nodes'],memory['nodes']):
                raw=(golden/('' if n['id']=='input' else 'nodes')/n['file']).read_bytes()
                if len(raw)!=n['bytes'] or __import__('hashlib').sha256(raw).hexdigest()!=n['sha256']:raise RuntimeError('Golden hash')
                starts.append(total);counts.append(len(raw));total+=len(raw)//2
                addresses.append(input_at if r['region']=='input' else output_at if r['region']=='output' else scratch_at+r['offset'])
                f.write(''.join(f'{v:04x}\n' for v in struct.unpack('<'+'H'*(len(raw)//2),raw)))
                expected.append(dict(id=n['id'],bytes=n['bytes'],sha256=n['sha256']))
        for name,values in [('node_start',starts),('node_bytes',counts),('node_at',addresses)]:
            (out/(name+'.hex')).write_text(''.join(f'{v:08x}\n' for v in values),encoding='ascii')
        top=(rtl/'griddehaze_frame_top.v').read_text()
        for anchor in ['reg   [8:0] i_2_fu_352;', 'ap_ST_fsm_state141 : begin', 'i_2_fu_352 <= add_ln80_reg_2805;']:
            if anchor not in top:raise RuntimeError('RTL retirement observer needs revision review: '+anchor)
        constants={k:int(v) for k,v in re.findall(r'^parameter\s+(C_\w+)\s*=\s*(\d+)\s*;',top,re.M)}
        for key,expression in re.findall(r'^parameter\s+(C_\w+)\s*=\s*([^;]+);',top,re.M):
            for k,v in sorted(constants.items(),key=lambda kv:-len(kv[0])):expression=re.sub(r'\b'+k+r'\b',str(v),expression)
            if re.fullmatch(r'[0-9 ()+*/-]+',expression):constants[key]=int(eval(expression,{'__builtins__':{}},{}))
        ports=[];interface={}
        for direction,width,name in re.findall(r'^(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',top,re.M):
            if width:
                high,low=width[1:-1].split(':')
                for k,v in sorted(constants.items(),key=lambda kv:-len(kv[0])):high=re.sub(r'\b'+k+r'\b',str(v),high)
                if not re.fullmatch(r'[0-9 ()+*/-]+',high):raise RuntimeError('unsupported width '+width)
                bits=eval(high,{'__builtins__':{}},{})-int(low)+1
                width=f'[{bits-1}:0]'
            ports.append((name,'logic '+width+' '+name+';'))
            interface[name]=(direction,width or '')
        if len(ports)!=110:raise RuntimeError('unexpected port count '+str(len(ports)))
        if a.physical_system:
            from grid_physical_path import build_path
            report['physical_replay']=build_path(a.physical_system,out/'core_netlist.v',interface)
            report.update(netlist_sha256=sha(a.physical_system),scope=report['physical_replay']['scope'])
            ports=[(n,'logic '+w+' '+n+';') for n,(d,w) in interface.items()]
            a.netlist_top='diagnostic_grid_path'
        if netlist_mode and not re.search(r'\bmodule\s+glbl\b',(out/'core_netlist.v').read_text()):
            shutil.copy2(a.vivado/'data/verilog/src/glbl.v',out/'glbl.v')
        connected=[k for k,v in ports]
        absent_outputs=[]
        if netlist_mode:
            nettext=(out/'core_netlist.v').read_text()
            body=re.search(r'\bmodule\s+'+re.escape(a.netlist_top)+r'\b.*?\bendmodule',nettext,re.S)
            if not body:raise RuntimeError('netlist top absent')
            clean_body=re.sub(r'\(\*.*?\*\)',' ',body.group(),flags=re.S)
            netports={n for d,w,n in re.findall(r'^\s*(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',clean_body,re.M)}
            connected=[k for k,v in ports if k in netports]
            directions={name:direction for direction,width,name in re.findall(r'^(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',top,re.M)}
            absent_outputs=[k for k,v in ports if k not in netports and directions[k]=='output']
            missing=[k for k,v in ports if k not in netports]
            if any(not ('USER' in n or n.startswith('m_axi_parameter_mem_AW') or n.startswith('m_axi_parameter_mem_W') or n.startswith('m_axi_parameter_mem_B') or n.endswith('_WID')) for n in missing):
                raise RuntimeError('Unexpected netlist port removal '+str(missing))
            report['netlist_removed_unused_ports']=missing
        instances=[]
        def width_of(name):
            width=interface[name][1]
            return int(width.split(':')[0][1:])+1 if width else 1
        for bundle,instance,base,capacity,ranges,writes in [
            ('feature_mem','feature',feature_base,feature_bytes,[(input_at,image),(output_at,image),(scratch_at,scratch)],[1,1]),
            ('parameter_mem','model_memory',parameter_base,parameter_capacity,[(0,m['blob_nbytes']),(layout_at,1344),(0,0)],[0,0])]:
            values=[f'.BASE(64\'h{base:x})',f'.BYTES({capacity})']
            values += [f'.DATA_WIDTH({width_of("m_axi_"+bundle+"_WDATA")})',f'.ID_WIDTH({width_of("m_axi_"+bundle+"_ARID")})']
            for i,(start,length) in enumerate(ranges):values += [f'.R{i}({start})',f'.N{i}({length})']
            values += [f'.WR1({writes[0]})',f'.WR2({writes[1]})']
            signals=['ARADDR','ARLEN','ARSIZE','ARBURST','ARID','ARVALID','ARREADY','RDATA','RLAST','RID','RRESP','RVALID','RREADY',
                     'AWADDR','AWLEN','AWSIZE','AWBURST','AWID','AWVALID','AWREADY','WDATA','WSTRB','WLAST','WVALID','WREADY','BID','BRESP','BVALID','BREADY']
            connections=['.clk(ap_clk)','.resetn(ap_rst_n)']
            for s in signals:
                wire=f'm_axi_{bundle}_{s}'
                if s in ['ARADDR','AWADDR'] and width_of(wire)<64:
                    wire="{{"+str(64-width_of(wire))+"{1'b0}},"+wire+"}"
                connections.append(f'.{s}({wire})')
            instances.append('gdn_axi_bounded_memory #('+','.join(values)+') '+instance+'('+','.join(connections)+');')
            instances.append(f'assign m_axi_{bundle}_RUSER=0,m_axi_{bundle}_BUSER=0;')
        tb=tracked_sources['frame_axi_test.sv'].read_text()
        instances+=['assign '+k+'=0;' for k in absent_outputs]
        replacements={'PORTS':'\n'.join(v for k,v in ports),'CONNECTIONS':',\n'.join(f'.{k}({k})' for k,v in ports),
                      'MEMORIES':'\n'.join(instances),'IMAGE_BYTES':image,'SCRATCH_BYTES':scratch,'HEIGHT':h,'WIDTH':w,
                      'GOLDEN_LAST':total-1,'FEATURE_WORDS':feature_bytes//4,'PARAMETER_WORDS':parameter_capacity//4,
                      'FRAME_CYCLES':a.max_frame_cycles,'TOTAL_CYCLES':2*a.max_frame_cycles+1000000,
                      'OUT_OFFSET':output_at,'OUT_BASE':format(feature_base+output_at,'08x'),'SCRATCH_BASE':format(feature_base+scratch_at,'08x'),
                      'INPUT_BASE':format(feature_base+input_at,'08x'),'PARAMETER_BASE':format(parameter_base,'08x'),
                      'LAYOUT_BASE':format(parameter_base+layout_at,'08x'),'PARAMETER_BYTES':m['blob_nbytes']}
        replacements['CONNECTIONS']=',\n'.join(f'.{k}({k})' for k in connected)
        for k,v in replacements.items():tb=tb.replace('@'+k+'@',str(v))
        if netlist_mode:
            tb='`define GDN_NETLIST\n'+tb.replace('griddehaze_frame_top dut(',a.netlist_top+' dut(')
            tb=tb.replace('cycle%1000000==0','cycle%10000==0')
        if a.physical_system:
            tb=tb.replace('s_axi_control_AWADDR=addr;',"s_axi_control_AWADDR=64'ha0040000+addr;")
            tb=tb.replace('s_axi_control_ARADDR=addr;',"s_axi_control_ARADDR=64'ha0040000+addr;")
            tb=tb.replace('s_axi_control_WDATA=data;',"s_axi_control_WDATA=0;s_axi_control_WDATA[(addr%($bits(s_axi_control_WDATA)/8))*8+:32]=data;s_axi_control_WSTRB=0;s_axi_control_WSTRB[addr%($bits(s_axi_control_WDATA)/8)+:4]=4'hf;")
            tb=tb.replace('data=s_axi_control_RDATA;',"data=s_axi_control_RDATA>>((addr%($bits(s_axi_control_RDATA)/8))*8);")
        if a.probe_cycles:
            report.update(kind=report['kind']+'_bounded_probe',probe_cycles=a.probe_cycles,
                          scope=report['scope']+'; bounded bus-activity probe only, no final Golden acceptance')
            monitor='''always @(negedge ap_clk)begin
    if(cycle%10000==0)$display("GDN_PROBE cycle=%0d active=%0d reads=%0d params=%0d writes=%0d ctrl_aw=%b/%b ctrl_ar=%b/%b",cycle,active,feature.read_beats,model_memory.read_beats,feature.write_beats,s_axi_control_AWVALID,s_axi_control_AWREADY,s_axi_control_ARVALID,s_axi_control_ARREADY);
    if(cycle==PROBE_LIMIT)begin $display("GDN_PROBE_COMPLETED");$finish;end
end
'''.replace('PROBE_LIMIT',str(a.probe_cycles))
            tb=tb.replace('endmodule',monitor+'endmodule')
        if re.search(r'@\w+@',tb):raise RuntimeError('unresolved template')
        (out/'frame_axi_test.sv').write_text(tb,encoding='ascii')
        shutil.copy2(tracked_sources['axi_bounded_memory.sv'],out/'axi_bounded_memory.sv')
        report['test_source_sha256']={name:source_hash_at_start[name] for name in
                                      ['frame_axi_test.sv','axi_bounded_memory.sv','frame_rtl_trial.py','ddr_fixture.py']}
        shutil.copy2(Path(__file__),out/'frame_rtl_trial.py')
        shutil.copy2(tracked_sources['ddr_fixture.py'],out/'ddr_fixture.py')
        report['compiled_source_sha256']={name:sha(out/name) for name in
                                          ['frame_axi_test.sv','axi_bounded_memory.sv','frame_rtl_trial.py','ddr_fixture.py']}
        if any(sha(path)!=source_hash_at_start[name] for name,path in tracked_sources.items()):
            raise RuntimeError('A source file changed while preparing the RTL test; refusing ambiguous run identity')
        if a.physical_system:
            dependency=Path(__file__).with_name('grid_physical_path.py')
            report['test_source_sha256'][dependency.name]=sha(dependency)
            shutil.copy2(dependency,out/dependency.name)
        report['case_shape']=[h,w];report['expected_nodes']=expected
        (out/'rtl.prj').write_text(''.join(f'verilog xil_defaultlib "{f.name}"\n' for f in sorted(out.glob('*.v')))+'sv xil_defaultlib "axi_bounded_memory.sv"\nsv xil_defaultlib "frame_axi_test.sv"\n',encoding='ascii')
        (out/'run.tcl').write_text('run all\nquit\n',encoding='ascii')
        cmd=out/'simulate.cmd'
        # Vivado 2025.2 optimizes by default; its documented switches include
        # --O0, not the older xelab -O <level> form.
        cmd.write_text('@echo off\nsetlocal\ncall "'+str(a.vivado/'settings64.bat')+'"\nif errorlevel 1 exit /b 1\ncall "'+str(a.vivado/'bin/xelab.bat')+'" xil_defaultlib.gdn_frame_axi_test '+('xil_defaultlib.glbl ' if netlist_mode else '')+'-prj rtl.prj -L unisims_ver -L unimacro_ver -L secureip -L xpm -relax -mt 2 -s gdn_frame_axi_test\nif errorlevel 1 exit /b 1\ncall "'+str(a.vivado/'bin/xsim.bat')+'" gdn_frame_axi_test -tclbatch run.tcl\nexit /b %errorlevel%\n',encoding='ascii')
        log=run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',cmd],'simulation')
        if a.probe_cycles:
            if 'GDN_PROBE_COMPLETED' not in log or 'Fatal:' in log:raise RuntimeError('Diagnostic probe did not complete')
            report.update(diagnostic_executed=True,negative_control=False,nodes_exact=None,
                          observations=re.findall(r'GDN_PROBE[^\r\n]*',log))
            return
        marker='GDN_RTL_SEQUENCE_PASS frames=2 scope='+('netlist_final_output' if netlist_mode else 'all_320_nodes')+' bad_model=1'
        if marker not in log or 'Fatal:' in log:raise RuntimeError('RTL sequence not completed')
        for i,n in enumerate(expected if not netlist_mode else []):
            actual=out/f'node_{i}.raw'
            if actual.stat().st_size!=n['bytes'] or sha(actual)!=n['sha256']:raise RuntimeError('actual RTL node file mismatch '+str(i))
        final=expected[-1]
        final_reference=(golden/'nodes'/meta['nodes'][-1]['file']).read_bytes()
        def captured_output_matches(data,reference):
            return len(data)==final['bytes'] and data==reference
        for i in [0,1]:
            actual=out/f'output_{i}.raw'
            if not captured_output_matches(actual.read_bytes(),final_reference) or sha(actual)!=final['sha256']:raise RuntimeError('actual RTL final mismatch')
        report['frames']=re.findall(r'GDN_RTL_FRAME_PASS[^\r\n]*',log)
        if netlist_mode:
            # The numerical run already compares two complete actual frames in
            # SV and again byte-for-byte here. Exercise this independent capture
            # comparator with a 1-LSB wrong reference, without claiming another
            # many-hour gate simulation was executed.
            altered=bytearray(final_reference);altered[0]^=1
            detected=not captured_output_matches((out/'output_0.raw').read_bytes(),bytes(altered))
            save(out/'negative_capture_compare.json',dict(detected=detected,changed_byte=0,changed_mask=1,
                 scope='offline raw-output comparator using this actual simulation capture; no additional DUT execution'))
            if not detected:raise RuntimeError('Captured-output negative control failed')
            report.update(pass_result=True,nodes_exact=None,cold_warm_exact=True,negative_control=True,
                          negative_control_scope='offline byte-for-byte capture comparator; RTL-mode SV fault-injection tested separately',
                          negative_capture_sha256=sha(out/'negative_capture_compare.json'),output_sha256=final['sha256'])
            return
        original=(out/'golden.hex').read_text();lines=original.splitlines();changed=starts[319 if netlist_mode else 1];lines[changed]=f'{int(lines[changed],16)^1:04x}'
        try:
            (out/'golden.hex').write_text('\n'.join(lines)+'\n',encoding='ascii')
            negative=run([a.vivado/'bin/xsim.bat','gdn_frame_axi_test','-tclbatch','run.tcl'],'negative_control')
            mismatch='final output mismatch' if netlist_mode else 'node mismatch pass=0 node=1 i=0'
            if mismatch not in negative or 'GDN_RTL_SEQUENCE_PASS' in negative:raise RuntimeError('negative control did not detect mismatch')
        finally:(out/'golden.hex').write_text(original,encoding='ascii')
        if any(sha(path)!=source_hash_at_start[name] for name,path in tracked_sources.items()):
            raise RuntimeError('A source file changed during the RTL run; refusing ambiguous run identity')
        report['source_snapshot_stable']=True
        report.update(pass_result=True,nodes_exact=None if netlist_mode else 320,cold_warm_exact=True,negative_control=True,output_sha256=final['sha256'])
    except Exception as e:
        report['error']=repr(e);raise
    finally:
        save(out/'result.json',report)
        print(json.dumps({k:v for k,v in report.items() if k not in ['rtl_sha256','expected_nodes','physical_replay']},indent=2),flush=True)

if __name__=='__main__':main()
