"""Bounded old/new writer RTL comparison using unchanged adapters and DDR v2.

No CNN math, SmartConnect, or full CNN simulation is run here. The actual HLS
output_writer controls 120 workspace / 180 A_low row sends. A testbench-only
lane placement connects its unchanged AXI32 adapters to the unchanged DDR v2.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[3]
FROZEN = Path('E:/HLS/cnn_v1_2_phase3b_r4/cnn_component/hls/syn/verilog')
CANDIDATE = REPO/'fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4_writecredit/rtl'
DEFAULT = Path('E:/HLS/kv260_three_module_v1_2_phase4/phase4e_writer_probe_01')
PORTABLE = Path('E:/HLS/kv260_three_module_v1_2_phase4/portable_verilator_5_050/ucrt64')
DDR = REPO/'fpga/perf/v1_2_phase4b/shared_axi_ddr_v2.sv'
WORDS = 4096


def ports(path):
    result = []
    for direction, width, name in re.findall(r'^(input|output)\s+(?:wire\s+|reg\s+)?(\[[^\]]+\]\s*)?(\w+)\s*;', path.read_text(), re.M):
        result.append((direction, width.strip(), name))
    return result


def make_tb():
    writer = 'zero_dce_cnn_top_p_anonymous_namespace_output_writer'
    declarations, connections, adapters, lane_mapping = [], [], [], []
    special = {'ap_clk':'clk','ap_rst':'!rst_n','ap_start':'start','ap_continue':"1'b1",'ap_done':'done',
        'output_r':'64\'h10000000+residue','workspace':'64\'h10000000+residue','block_r':'block_number[2:0]',
        'p_loc5_c_dout':'channels[6:0]','p_loc5_c_empty_n':"1'b1",'p_loc5_c_num_data_valid':"3'd1",'p_loc5_c_fifo_cap':"3'd1",
        'result_dout':'sample(sample_index)','result_empty_n':"1'b1",'result_num_data_valid':"9'd256",'result_fifo_cap':"9'd256"}
    for direction, width, name in ports(FROZEN/f'{writer}.v'):
        if name in special:
            connections.append(f'.{name}({special[name]})')
        elif name.startswith('m_axi_'):
            declarations.append(f'wire {width} {name};')
            if direction == 'input' and name.endswith(('_RLAST','_RID','_RUSER','_RRESP','_BRESP','_BID','_BUSER')):
                declarations.append(f'assign {name}=0;')
            connections.append(f'.{name}({name})')
        else:
            declarations.append(f'wire {width} {name};')
            connections.append(f'.{name}({name})')
    for p, label, rfifo in [(0,'workspace',12),(1,'output',10)]:
        pre=f'm_axi_gmem_{label}_0_'
        tag=f'bus{p}_'
        declarations += [f'wire [63:0] {tag}AWADDR;',f'wire [7:0] {tag}AWLEN;',f'wire [2:0] {tag}AWSIZE;',
            f'wire [1:0] {tag}AWBURST;',f'wire [31:0] {tag}WDATA;',f'wire [3:0] {tag}WSTRB;',
            f'wire {tag}AWID, {tag}AWVALID, {tag}WVALID, {tag}WLAST, {tag}BREADY;']
        acon={n:tag+n for n in ['AWADDR','AWLEN','AWSIZE','AWBURST','AWID','AWVALID','WDATA','WSTRB','WVALID','WLAST','BREADY']}
        acon.update(AWREADY=f'awready[{p}]',WREADY=f'wready[{p}]',BVALID=f'bvalid[{p}]',BID=f'bid[{p}][0:0]',
            BRESP="2'd0",BUSER="1'd0",ACLK='clk',ARESET='!rst_n',ACLK_EN="1'b1",
            ARREADY="1'b0",RDATA="32'd0",RID="1'b0",RRESP="2'd0",RLAST="1'b0",RVALID="1'b0",RUSER="1'b0")
        for n in ['AWADDR','AWLEN','AWVALID','AWREADY','WDATA','WSTRB','WVALID','WREADY','BVALID','BREADY',
                  'ARADDR','ARLEN','ARVALID','ARREADY','RDATA','RVALID','RREADY','RFIFONUM']:
            acon['I_CH0_'+n]=pre+n
        adapters.append(f'''zero_dce_cnn_top_gmem_{label}_m_axi #(
          .C_M_AXI_ADDR_WIDTH(64),.C_M_AXI_DATA_WIDTH(32),.CH0_USER_DW(16),.CH0_USER_AW(64),
          .MAX_READ_BURST_LENGTH({64 if p==0 else 16}),.MAX_WRITE_BURST_LENGTH(64),
          .USER_MAXREQS({7 if p==0 else 4}),.CH0_NUM_READ_OUTSTANDING(16),.CH0_NUM_WRITE_OUTSTANDING(16),
          .CH0_USER_RFIFONUM_WIDTH({rfifo}),.NUM_READ_OUTSTANDING({16 if p==0 else 0}),.NUM_WRITE_OUTSTANDING(16)) adapter{p}(
          {','.join('.'+k+'('+v+')' for k,v in acon.items())});''')
        lane_mapping.append(f'''assign awaddr[{p}]={tag}AWADDR[48:0]; assign awlen[{p}]={tag}AWLEN;
          assign awsize[{p}]={tag}AWSIZE;assign awburst[{p}]={tag}AWBURST;assign awid[{p}]={{5'd0,{tag}AWID}};
          assign awvalid[{p}]={tag}AWVALID;assign wvalid[{p}]={tag}WVALID;assign wlast[{p}]={tag}WLAST;
          assign bready[{p}]={tag}BREADY;
          assign wdata[{p}]={{96'd0,{tag}WDATA}} << (8*ddr.write_address[{p}][3:0]);
          assign wstrb[{p}]={{12'd0,{tag}WSTRB}} << ddr.write_address[{p}][3:0];''')
    declarations += ['wire [63:0] logical_addr[0:1];wire [31:0] logical_len[0:1];wire [1:0] logical_aw, logical_b, logical_w;']
    for p,label in [(0,'workspace'),(1,'output')]:
        pre=f'm_axi_gmem_{label}_0_'
        lane_mapping += [f'assign logical_addr[{p}]={pre}AWADDR;assign logical_len[{p}]={pre}AWLEN;',
            f'assign logical_aw[{p}]={pre}AWVALID && {pre}AWREADY;',
            f'assign logical_b[{p}]={pre}BVALID && {pre}BREADY;',
            f'assign logical_w[{p}]={pre}WVALID && {pre}WREADY;']
    return '''`timescale 1ns/1ps
module writer_probe;
reg clk=0;always #5 clk=~clk;
reg rst_n=0,start=0;wire done;
integer block_number=1,channels=2,residue=0,sample_index=0,cycle=0,start_cycle=0,fd,errors=0;
integer row_issue[0:1], row_retire[0:1], credits[0:1],peak[0:1],aw_count[0:1],wl_count[0:1],b_count[0:1];
integer logical_wcount[0:1],logical_wrow[0:1];
reg [127:0] expected[0:''' + str(WORDS-1) + '''];
function automatic [15:0] sample(input integer n);sample=(n*73+16'h2345)&16'hffff;endfunction
wire [48:0] araddr[0:3],awaddr[0:3];wire [7:0] arlen[0:3],awlen[0:3];
wire [2:0] arsize[0:3],awsize[0:3];wire [1:0] arburst[0:3],awburst[0:3],rresp[0:3],bresp[0:3];
wire [5:0] arid[0:3],awid[0:3],rid[0:3],bid[0:3];
wire [3:0] arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
wire [127:0] rdata[0:3],wdata[0:3];wire [15:0] wstrb[0:3];
''' + '\n'.join(declarations) + '\n' + writer + ' dut(' + ','.join(connections) + ''');
''' + '\n'.join(adapters+lane_mapping) + '''
generate for(genvar p=0;p<4;p=p+1) begin:idle_reads
assign araddr[p]=0;assign arlen[p]=0;assign arsize[p]=0;assign arburst[p]=1;
assign arid[p]=0;assign arvalid[p]=0;assign rready[p]=0;
if(p>=2) begin
assign awaddr[p]=0;assign awlen[p]=0;assign awsize[p]=0;assign awburst[p]=1;assign awid[p]=0;
assign awvalid[p]=0;assign wdata[p]=0;assign wstrb[p]=0;assign wvalid[p]=0;assign wlast[p]=0;assign bready[p]=0;
end end endgenerate
shared_axi_ddr #(.WORDS(''' + str(WORDS) + '''),.BASE(49'h10000000),.READ_OUTSTANDING(2),.WRITE_OUTSTANDING(2)) ddr(
.clk(clk),.rst_n(rst_n),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arid(arid),.arvalid(arvalid),.arready(arready),
.rdata(rdata),.rid(rid),.rlast(rlast),.rvalid(rvalid),.rready(rready),.rresp(rresp),
.awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awid(awid),.awvalid(awvalid),.awready(awready),
.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),.bid(bid),.bvalid(bvalid),.bready(bready),.bresp(bresp));
initial begin
if(!$value$plusargs("BLOCK=%d",block_number)) block_number=1;
if(!$value$plusargs("CHANNELS=%d",channels)) channels=2;
if(!$value$plusargs("RESIDUE=%d",residue)) residue=0;
$readmemh("expected.hex",expected);
fd=$fopen("timeline.csv","w");$fdisplay(fd,"cycle,event,port,row,address,length,data,strb,credit");
for(integer p=0;p<2;p=p+1) begin
row_issue[p]=0;row_retire[p]=0;credits[p]=0;peak[p]=0;aw_count[p]=0;wl_count[p]=0;b_count[p]=0;
logical_wcount[p]=0;logical_wrow[p]=0;
end
repeat(8) @(negedge clk);rst_n=1;
repeat(2) @(negedge clk);start=1;start_cycle=cycle;
wait(done);@(negedge clk);start=0;
if(sample_index!=channels*60*106) $fatal(1,"sample count mismatch %0d",sample_index);
for(integer p=0;p<2;p=p+1) begin
if(credits[p]!=0 || row_issue[p]!=row_retire[p] || aw_count[p]!=b_count[p] || aw_count[p]!=wl_count[p])
 $fatal(1,"not drained port=%0d credit=%0d AW=%0d WLAST=%0d B=%0d",p,credits[p],aw_count[p],wl_count[p],b_count[p]);
$display("WRITER_PORT PORT=%0d ROWS=%0d PEAK=%0d FINAL_CREDIT=%0d AW=%0d WLAST=%0d B=%0d",p,row_issue[p],peak[p],credits[p],aw_count[p],wl_count[p],b_count[p]);
end
for(integer n=0;n<''' + str(WORDS) + ''';n=n+1) if(ddr.mem[n]!==expected[n]) errors=errors+1;
if(errors) $fatal(1,"writer data/guard mismatch %0d",errors);
ddr.print_stats();
$writememh("actual.hex",ddr.mem);$fclose(fd);
$display("WRITER_PROBE_PASS BLOCK=%0d CHANNELS=%0d RESIDUE=%0d CYCLES=%0d RAW_MISMATCH=0 GUARD=0 FINAL_CREDIT=0",block_number,channels,residue,cycle-start_cycle);
$finish;
end
always @(posedge clk) begin
cycle<=cycle+1;
if(cycle>200000) $fatal(1,"writer probe timeout");
if(rst_n) begin
if(result_read) sample_index<=sample_index+1;
for(integer p=0;p<2;p=p+1) begin
if(logical_aw[p]) begin
$fdisplay(fd,"%0d,ROW_AW,%0d,%0d,%0d,%0d,0,0,%0d",cycle,p,row_issue[p],logical_addr[p],logical_len[p],credits[p]+1);
row_issue[p]=row_issue[p]+1;
end
if(logical_b[p]) begin
if(credits[p]<=0) $fatal(1,"unexpected logical B");
$fdisplay(fd,"%0d,ROW_B,%0d,%0d,0,0,0,0,%0d",cycle,p,row_retire[p],credits[p]-1);row_retire[p]=row_retire[p]+1;
end
if(logical_w[p]) begin
logical_wcount[p]=logical_wcount[p]+1;
if(logical_wcount[p]==106) begin
$fdisplay(fd,"%0d,ROW_WEND,%0d,%0d,0,0,0,0,%0d",cycle,p,logical_wrow[p],credits[p]);
logical_wcount[p]=0;logical_wrow[p]=logical_wrow[p]+1;
end end
credits[p]=credits[p]+logical_aw[p]-logical_b[p];
if(credits[p]<0 || credits[p]>2) $fatal(1,"row credit exceeds 2");
if(credits[p]>peak[p]) peak[p]=credits[p];
if(awvalid[p] && awready[p]) begin
$fdisplay(fd,"%0d,AW,%0d,%0d,%0d,%0d,0,0,%0d",cycle,p,aw_count[p],awaddr[p],awlen[p]+1,credits[p]);aw_count[p]=aw_count[p]+1;
end
if(wvalid[p] && wready[p]) begin
if(p==0) $fdisplay(fd,"%0d,W,%0d,%0d,%0d,1,%h,%h,%0d",cycle,p,wl_count[p],ddr.write_address[p],bus0_WDATA,bus0_WSTRB,credits[p]);
else $fdisplay(fd,"%0d,W,%0d,%0d,%0d,1,%h,%h,%0d",cycle,p,wl_count[p],ddr.write_address[p],bus1_WDATA,bus1_WSTRB,credits[p]);
if(wlast[p]) begin
$fdisplay(fd,"%0d,WLAST,%0d,%0d,%0d,0,0,0,%0d",cycle,p,wl_count[p],ddr.write_address[p],credits[p]);wl_count[p]=wl_count[p]+1;
end end
if(bvalid[p] && bready[p]) begin
$fdisplay(fd,"%0d,B,%0d,%0d,0,0,0,0,%0d",cycle,p,b_count[p],credits[p]);b_count[p]=b_count[p]+1;
end end end end
endmodule
'''


def memories(out, channels, residue):
    initial = bytearray([0xA5]*(WORDS*16)); expected=initial.copy(); mask=bytearray(len(initial))
    sample_index=0
    # Actual output_writer order: band, channel, 4 rows. Block1 slot base is 0;
    # block7 writes output with the same planar row addressing.
    for band in range(15):
        for channel in range(channels):
            for r in range(4):
                address=residue+2*(channel*6360+(band*4+r)*106)
                for x in range(106):
                    value=(sample_index*73+0x2345)&0xffff
                    expected[address+2*x:address+2*x+2]=value.to_bytes(2,'little')
                    mask[address+2*x:address+2*x+2]=b'\x01\x01'
                    sample_index+=1
    for name,data in [('shared_ddr.hex',initial),('expected.hex',expected)]:
        (out/name).write_text(''.join(data[i:i+16][::-1].hex()+'\n' for i in range(0,len(data),16)))
    return mask


def analyze(run, mask):
    log=(run/'run.log').read_text()
    match=re.search(r'WRITER_PROBE_PASS.*CYCLES=(\d+)',log)
    assert match and not any(s in log for s in ['Assertion failed','%Error','cannot be opened'])
    rows=list(csv.DictReader((run/'timeline.csv').open()))
    for row in rows:
        for key in ['cycle','port','row','address','length','credit']: row[key]=int(row[key])
        for key in ['data','strb']: row[key]=int(row[key],16)
    issued=[r for r in rows if r['event']=='ROW_AW'];retired=[r for r in rows if r['event']=='ROW_B']
    aw=[r for r in rows if r['event']=='AW']; wl=[r for r in rows if r['event']=='WLAST'];b=[r for r in rows if r['event']=='B']
    writes=[r for r in rows if r['event']=='W']
    assert len(aw)==len(wl)==len(b) and len(issued)==len(retired)
    intervals=[issued[i+1]['cycle']-issued[i]['cycle'] for i in range(len(issued)-1)]
    overlap=[dict(row=i+1,previous_B=retired[i]['cycle'],next_AW=issued[i+1]['cycle'])
        for i in range(len(issued)-1) if issued[i+1]['cycle']<retired[i]['cycle']]
    for request in aw:
        assert (request['address']&~3)%4096+request['length']*4<=4096
    # The exact byte mask for each physical burst is derived independently from
    # the row's nominal start and end, including halfword edge masks.
    physical_row={};logical_index=0;row_physical_b={}
    for index,request in enumerate(aw):
        logical=issued[logical_index]
        physical_row[index]=logical
        row_physical_b[logical_index]=b[index]['cycle']
        last_address=(request['address']&~3)+request['length']*4
        if last_address >= ((logical['address']*2+logical['length']*2+3)&~3): logical_index+=1
    assert logical_index==len(issued)
    row_physical_first_w={};row_physical_last_w={}
    for write in writes:
        base=write['address']-0x10000000
        logical=physical_row[write['row']]
        row_physical_first_w.setdefault(logical['row'],write['cycle'])
        row_physical_last_w[logical['row']]=write['cycle']
        begin=logical['address']*2;end=begin+logical['length']*2
        expected_strb=sum(int(begin<=write['address']+lane<end)<<lane for lane in range(4))
        assert write['strb']==expected_strb, ('WSTRB mismatch',write,expected_strb)
        assert all(mask[base+lane] for lane in range(4) if write['strb']&(1<<lane))
    data_overlap=[dict(row=i+1,previous_final_physical_B=row_physical_b[i],
        next_first_physical_W=row_physical_first_w[i+1],next_last_physical_W=row_physical_last_w[i+1])
        for i in range(len(issued)-1) if row_physical_first_w[i+1]<row_physical_b[i]]
    split_rows=[];row_timeline=[]
    for index,logical in enumerate(issued):
        bursts=[n for n in physical_row if physical_row[n]['row']==index]
        if len(bursts)>1: split_rows.append(index)
        if index<3 or len(bursts)>1 and not any(r['split'] for r in row_timeline):
            row_timeline.append(dict(row=index,logical_aw_cycle=logical['cycle'],logical_b_cycle=retired[index]['cycle'],
                physical_first_w_cycle=row_physical_first_w[index],physical_last_w_cycle=row_physical_last_w[index],
                split=len(bursts)>1,physical_bursts=[dict(aw_cycle=aw[n]['cycle'],address=aw[n]['address'],
                    beats=aw[n]['length'],wlast_cycle=wl[n]['cycle'],b_cycle=b[n]['cycle']) for n in bursts]))
    return dict(total_writer_cycles=int(match[1]),row_count=len(issued),row_credit_peak=max(r['credit'] for r in rows),
        final_credit=0,physical_aw=len(aw),physical_wlast=len(wl),physical_b=len(b),raw_mismatch=0,guard=0,
        row_interval_min=min(intervals),row_interval_max=max(intervals),row_interval_mean=sum(intervals)/len(intervals),
        row_interval_median=statistics.median(intervals),split_rows=len(split_rows),row_timeline=row_timeline,
        write_strobe_histogram={str(strobe):sum(r['strb']==strobe for r in writes) for strobe in sorted({r['strb'] for r in writes})},
        overlap_rows=len(overlap),first_overlap=overlap[:8],first_row_timeline=[r for r in rows if r['event']!='W'][:30],
        actual_data_overlap_rows=len(data_overlap),first_actual_data_overlap=data_overlap[:8],
        footprint=[{k:r[k] for k in ['event','port','address','length','data','strb']} for r in rows if r['event'] in ['AW','W']],
        row_aw_cycles=[r['cycle'] for r in issued],row_b_cycles=[r['cycle'] for r in retired],
        aw_cycles=[r['cycle'] for r in aw],wlast_cycles=[r['cycle'] for r in wl],b_cycles=[r['cycle'] for r in b])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DEFAULT)
    parser.add_argument('--simulator',choices=['xsim','verilator'],default='xsim')
    args=parser.parse_args();out=args.out
    out.mkdir(exist_ok=False,parents=True)
    (out/'writer_probe.sv').write_text(make_tb())
    env=os.environ.copy();env['PATH']='C:/msys64/ucrt64/bin;C:/msys64/usr/bin;'+env['PATH'];env['VERILATOR_ROOT']=str(PORTABLE/'share/verilator')
    all_results={}
    for name,overlays in [('old',{}),('new',{p.name:p for p in CANDIDATE.glob('*.v')})]:
        build=out/name;build.mkdir()
        files=[overlays.get(p.name,p) for p in FROZEN.glob('*.v')]+[DDR,out/'writer_probe.sv']
        (build/'sources.f').write_text('\n'.join('"'+p.as_posix()+'"' for p in files)+'\n')
        (build/'source_manifest.json').write_text(json.dumps([dict(path=p.as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],indent=2))
        print(f'Building bounded {name} writer probe',flush=True)
        if args.simulator=='verilator':
            cmd=[str(PORTABLE/'bin/verilator_bin.exe'),'--binary','--timing','--compiler','gcc','-j','4','--top-module','writer_probe','-Wno-fatal','-f','sources.f']
        else:
            (build/'probe.prj').write_text('\n'.join(('sv' if p.suffix=='.sv' else 'verilog')+' xil_defaultlib "'+p.as_posix()+'"' for p in files)+'\nnosort\n')
            (build/'build.cmd').write_text('@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
                'call "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n'+f'cd /d "{build}"\n'
                'call xelab -prj probe.prj xil_defaultlib.writer_probe -s writer_probe -mt 4 -log compile.log\nexit /b %errorlevel%\n')
            (build/'run.tcl').write_text('run all\nquit\n')
            cmd=['cmd','/c',str(build/'build.cmd')]
        with (build/'build.log').open('w') as log: subprocess.run(cmd,cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        for block,channels in [(1,2),(7,3)]:
            for residue in [0,4090]:
                scenario=f'b{block}_r{residue}';run=build/scenario;run.mkdir();mask=memories(run,channels,residue)
                plusargs=[f'BLOCK={block}',f'CHANNELS={channels}',f'RESIDUE={residue}',
                    'READ_OUTSTANDING=2','WRITE_OUTSTANDING=2','DDR_DELAY=16','SERVICE_PERIOD=1']
                if args.simulator=='verilator':
                    command=[str(build/'obj_dir/Vwriter_probe.exe')]+['+'+p for p in plusargs];cwd=run
                else:
                    for filename in ['shared_ddr.hex','expected.hex']: shutil.copy2(run/filename,build/filename)
                    (build/'run.cmd').write_text('@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
                        'call "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n'+f'cd /d "{build}"\n'
                        'call xsim writer_probe -tclbatch run.tcl -log xsim_run.log '+
                        ' '.join('-testplusarg "'+p+'"' for p in plusargs)+'\nexit /b %errorlevel%\n')
                    command=['cmd','/c',str(build/'run.cmd')];cwd=build
                with (run/'run.log').open('w') as log: subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
                if args.simulator=='xsim':
                    for filename in ['timeline.csv','actual.hex','xsim_run.log']: shutil.copy2(build/filename,run/filename)
                result=analyze(run,mask);all_results[name,scenario]=result
                public={k:v for k,v in result.items() if k!='footprint'}
                (run/'evidence.json').write_text(json.dumps(public,indent=2))
                print(name,scenario,result['total_writer_cycles'],result['overlap_rows'],flush=True)
    comparison={}
    for name in ['old','new']:
        for entry in json.loads((out/name/'source_manifest.json').read_text()):
            assert hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()==entry['sha256'],'probe source changed during runs'
    for scenario in [f'b{block}_r{residue}' for block in [1,7] for residue in [0,4090]]:
        old=all_results['old',scenario];new=all_results['new',scenario]
        for event in ['AW','W']:
            assert [r for r in old['footprint'] if r['event']==event]==[r for r in new['footprint'] if r['event']==event],'external write footprint/data/strobe changed'
        assert old['actual_data_overlap_rows']==0 and new['actual_data_overlap_rows']>0 and new['row_credit_peak']==2
        comparison[scenario]=dict(old_cycles=old['total_writer_cycles'],new_cycles=new['total_writer_cycles'],
            saved_cycles=old['total_writer_cycles']-new['total_writer_cycles'],
            old_row_interval_mean=old['row_interval_mean'],new_row_interval_mean=new['row_interval_mean'],
            old_row_interval_median=old['row_interval_median'],new_row_interval_median=new['row_interval_median'],
            row_credit_peak=new['row_credit_peak'],overlap_rows=new['overlap_rows'],
            actual_data_overlap_rows=new['actual_data_overlap_rows'],first_actual_data_overlap=new['first_actual_data_overlap'],
            external_footprint_data_strobes_identical=True,numerical_and_protocol_pass=True,
            physical_aw=new['physical_aw'],physical_wlast=new['physical_wlast'],physical_b=new['physical_b'],
            split_rows=new['split_rows'],write_strobe_histogram=new['write_strobe_histogram'],
            old_row_timeline=old['row_timeline'],new_row_timeline=new['row_timeline'],
            old_timeline=old['first_row_timeline'],new_timeline=new['first_row_timeline'])
    (out/'comparison.json').write_text(json.dumps(dict(scope=__doc__,ddr_delay=16,write_outstanding=2,
        ddr_sha256=hashlib.sha256(DDR.read_bytes()).hexdigest(),simulator=args.simulator,
        source_manifest_reverified_after_runs=True,complete=True,scenarios=comparison),indent=2))
    print('BOUNDED_WRITER_OVERLAP_GATE_PASS',flush=True)


if __name__=='__main__':main()
