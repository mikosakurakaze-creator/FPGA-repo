"""Validate a generated SmartConnect output-register variant through AXI bursts.

Both generated designs use the same vendor core and independent AXI drivers /
DDR models. Compare transaction data/order/IDs under backpressure, not latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from run_checks import vendor_runtime
from targeted_fifo_mapping import bram_output, buffered_payload, output_register_off, parameter

INSTALL=Path('D:/vivado/2025.2/Vivado')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


EXERCISE = r'''
integer cycle=0,write_beats=0,read_beats=0,overlap=0;
reg wa_busy=0,ra_busy=0;
integer wa_base=0,wa_len=0,wa_index=0,ra_base=0,ra_len=0,ra_index=0;
reg [127:0] memory[0:16383];
function automatic [127:0] pattern(input integer seed,input integer index);
 pattern={32'hcf731204 ^ seed,32'h7921eab3+index,32'h1ed8c427 ^ (seed*37+index),32'h9a0fd521+seed+index*3};
endfunction
always @(posedge aclk) begin
 if(!aresetn) begin
  cycle<=0; wa_busy<=0; ra_busy<=0; M00_AXI_0_bvalid<=0; M00_AXI_0_rvalid<=0;
  M00_AXI_0_rdata<=0; M00_AXI_0_rresp<=0; M00_AXI_0_rlast<=0; M00_AXI_0_bresp<=0;
 end else begin
  cycle<=cycle+1;
  if(M00_AXI_0_awvalid && M00_AXI_0_awready) begin
   if(M00_AXI_0_awburst!=1 || M00_AXI_0_awsize!=4) $fatal(1,"Bad AW transport");
   wa_busy<=1; wa_base<=M00_AXI_0_awaddr[15:4]; wa_len<=M00_AXI_0_awlen; wa_index<=0;
  end
  if(M00_AXI_0_wvalid && M00_AXI_0_wready) begin
   if(M00_AXI_0_wlast !== (wa_index==wa_len)) $fatal(1,"Incorrect WLAST");
   if(M00_AXI_0_wstrb!==16'hffff) $fatal(1,"Incorrect WSTRB");
   memory[wa_base+wa_index]<=M00_AXI_0_wdata;
   wa_index<=wa_index+1; write_beats<=write_beats+1;
   if(M00_AXI_0_wlast) begin wa_busy<=0; M00_AXI_0_bvalid<=1; end
  end
  if(M00_AXI_0_bvalid && M00_AXI_0_bready) M00_AXI_0_bvalid<=0;
  if(M00_AXI_0_arvalid && M00_AXI_0_arready) begin
   if(M00_AXI_0_arburst!=1 || M00_AXI_0_arsize!=4) $fatal(1,"Bad AR transport");
   ra_busy<=1; ra_base<=M00_AXI_0_araddr[15:4]; ra_len<=M00_AXI_0_arlen; ra_index<=0;
  end
  if(M00_AXI_0_rvalid && M00_AXI_0_rready) M00_AXI_0_rvalid<=0;
  if(ra_busy && (!M00_AXI_0_rvalid || M00_AXI_0_rready) && cycle%11!=0 && cycle%11!=1) begin
   M00_AXI_0_rvalid<=1; M00_AXI_0_rdata<=memory[ra_base+ra_index];
   M00_AXI_0_rlast<=(ra_index==ra_len); M00_AXI_0_rresp<=0;
   ra_index<=ra_index+1;
   if(ra_index==ra_len) ra_busy<=0;
  end
  if(M00_AXI_0_rvalid && M00_AXI_0_rready) read_beats<=read_beats+1;
  if(M00_AXI_0_rvalid && M00_AXI_0_wvalid) overlap<=overlap+1;
 end
end
always @(negedge aclk) begin
 M00_AXI_0_awready=aresetn && !wa_busy && !M00_AXI_0_bvalid && cycle%7!=0;
 M00_AXI_0_wready=aresetn && wa_busy && cycle%13!=0 && cycle%13!=1 && cycle%13!=2;
 M00_AXI_0_arready=aresetn && !ra_busy && !M00_AXI_0_rvalid && cycle%5!=0;
 S00_AXI_0_bready=aresetn && cycle%37>=17;
 S00_AXI_0_rready=aresetn && cycle%29>=9;
end
task automatic write_burst(input integer addr,input integer count,input integer seed,input bit id);
 fork
  begin
   @(negedge aclk);
   S00_AXI_0_awaddr=32'h44a00000+addr; S00_AXI_0_awlen=count-1; S00_AXI_0_awsize=4; S00_AXI_0_awburst=1;
   S00_AXI_0_awid=id; S00_AXI_0_awvalid=1;
   do @(posedge aclk); while(!S00_AXI_0_awready);
   @(negedge aclk); S00_AXI_0_awvalid=0;
  end
  begin
   for(integer k=0;k<count;k=k+1) begin
    @(negedge aclk);
    S00_AXI_0_wvalid=1; S00_AXI_0_wdata=pattern(seed,k); S00_AXI_0_wstrb=16'hffff;
    S00_AXI_0_wlast=(k==count-1);
    do @(posedge aclk); while(!S00_AXI_0_wready);
    @(negedge aclk); S00_AXI_0_wvalid=0;
   end
  end
  begin
   do @(posedge aclk); while(!(S00_AXI_0_bvalid && S00_AXI_0_bready));
   if(S00_AXI_0_bresp!==0 || S00_AXI_0_bid!==id) $fatal(1,"Incorrect B response=%h ID=%h expected=%h",S00_AXI_0_bresp,S00_AXI_0_bid,id);
  end
 join
endtask
task automatic read_burst(input integer addr,input integer count,input integer seed,input bit id);
 @(negedge aclk);
 S00_AXI_0_araddr=32'h44a00000+addr; S00_AXI_0_arlen=count-1; S00_AXI_0_arsize=4; S00_AXI_0_arburst=1;
 S00_AXI_0_arid=id; S00_AXI_0_arvalid=1;
 do @(posedge aclk); while(!S00_AXI_0_arready);
 @(negedge aclk); S00_AXI_0_arvalid=0;
 for(integer k=0;k<count;k=k+1) begin
  do @(posedge aclk); while(!(S00_AXI_0_rvalid && S00_AXI_0_rready));
  if(S00_AXI_0_rdata!==pattern(seed,k) || S00_AXI_0_rresp!==0 || S00_AXI_0_rid!==id || S00_AXI_0_rlast!==(k==count-1))
   $fatal(1,"Read data/order/ID/LAST mismatch k=%0d got=%h expected=%h",k,S00_AXI_0_rdata,pattern(seed,k));
 end
endtask
integer counts[0:7];
initial begin
 counts[0]=1;counts[1]=2;counts[2]=16;counts[3]=17;counts[4]=32;counts[5]=64;counts[6]=127;counts[7]=256;
 done=0; aresetn=0;
 repeat(12) @(negedge aclk); aresetn=1; repeat(32) @(posedge aclk);
 for(integer batch=0;batch<3;batch=batch+1) begin
  for(integer n=0;n<8;n=n+1) begin
   write_burst(n*4096,counts[n],batch*19+n,n%2);
   fork
    read_burst(n*4096,counts[n],batch*19+n,n%2);
    write_burst((n+8)*4096,counts[7-n],batch*43+n+7,(n+1)%2);
   join
   read_burst((n+8)*4096,counts[7-n],batch*43+n+7,(n+1)%2);
  end
  @(negedge aclk); aresetn=0;
  repeat(12) @(negedge aclk); aresetn=1; repeat(32) @(posedge aclk);
 end
 if(!overlap || write_beats!=read_beats) $fatal(1,"Missing full-duplex/beat coverage");
 $display("SC_FIFO_OUTPUT_AXI_PASS case=CASE_NAME writes=%0d reads=%0d overlap=%0d",write_beats,read_beats,overlap);
 done=1;
end
'''


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--generated',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--si-width', type=int, choices=(32,128), default=128)
    ap.add_argument('--fifo-mode', choices=('output-register-off', 'bram', 'targeted'), default='output-register-off')
    ap.add_argument('--check-saturation', action='store_true', help='Require continuous read beats after 16-beat warmup')
    a=ap.parse_args(); generated=a.generated.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'pass':False,'scope':f'Generated {a.si_width}-bit SI / 128-bit MI SmartConnect AXI transactions; not complete six-core or all clock conversions',
            'fifo_mode':a.fifo_mode,'saturation_checked':a.check_saturation,'board_operations':0,'steps':[],'source_files':{}}
    sim=[p for p in generated.rglob('*') if p.suffix in ('.v','.sv') and p.parent.name=='sim']
    if not sim: raise ValueError('No generated simulation targets')
    # A generated BD file contains several hierarchy modules. Every identifier
    # must be unique per design, otherwise the second copy silently replaces
    # the first copy's nested modules and destroys independent comparison.
    modules={name for p in sim for name in re.findall(r'(?m)^\s*module\s+(\w+)',p.read_text())}
    top=next(p for p in sim if p.name=='fifo_probe.v')
    ports=re.findall(r'\b(input|output)\s*(\[[^]]+\])?\s*(\w+)\s*;',top.read_text())
    if len(ports)<60: raise ValueError('AXI port extraction failed')
    files=[]; changed=0
    for label in ('reference','variant'):
        folder=out/label;folder.mkdir()
        for p in sim:
            original=p.read_text(); content=original
            is_node='.C_FIFO_TYPE(0)' in content and '.C_FIFO_SIZE(5)' in content
            if a.fifo_mode=='targeted' and is_node:
                # Compare against the just-routed OUTPUT_REG=0 structure.
                content=output_register_off(content)
            if label=='variant':
                if a.fifo_mode=='targeted' and is_node:
                    channel=parameter(content,'C_CHANNEL')
                    if channel==0:
                        content=bram_output(content);changed+=1
                    elif channel in (2,4):
                        content=buffered_payload(content);changed+=1
                elif a.fifo_mode=='bram' and '.C_FIFO_TYPE(0)' in content and '.C_FIFO_SIZE(5)' in content \
                   and re.search(r'\.C_CHANNEL\([01]\)',content):
                    if '.C_FIFO_OUTPUT_REG(1)' not in content or '.C_FIFO_IP(0)' not in content:
                        raise ValueError('Unexpected original BRAM probe node contract')
                    content=content.replace('.C_FIFO_TYPE(0)','.C_FIFO_TYPE(1)').replace('C_FIFO_TYPE=0,','C_FIFO_TYPE=1,')
                    content=content.replace('.C_FIFO_SIZE(5)','.C_FIFO_SIZE(9)').replace('C_FIFO_SIZE=5,','C_FIFO_SIZE=9,')
                    content=content.replace('.C_FIFO_IP(0)','.C_FIFO_IP(2)').replace('C_FIFO_IP=0,','C_FIFO_IP=2,')
                    changed+=1
                elif a.fifo_mode=='output-register-off' and '.C_FIFO_OUTPUT_REG(1)' in content:
                    content=content.replace('.C_FIFO_OUTPUT_REG(1)','.C_FIFO_OUTPUT_REG(0)')
                    changed+=1
            # Rename only generated module identifiers, keeping vendor library symbols.
            content=re.sub(r'\b(?:'+ '|'.join(sorted(map(re.escape,modules),key=len,reverse=True))+r')\b',
                           lambda m:label+'_'+m.group(0),content)
            dest=folder/p.name;dest.write_text(content,encoding='utf-8');files.append(dest)
            result['source_files'][dest.relative_to(out).as_posix()]=sha(dest)
    expected_changes={'bram':2,'targeted':3,'output-register-off':5}[a.fifo_mode]
    if changed!=expected_changes: raise ValueError(f'Expected {expected_changes} generated channel FIFO nodes, found {changed}')
    benches=[]
    for label in ('reference','variant'):
        declarations=[]
        for direction,width,name in ports:
            typ='reg' if direction=='input' else 'wire'
            declarations.append(f'{typ} {width or ""} {name}'+('=0;' if typ=='reg' else ';'))
        declarations.append('always #5 aclk=~aclk;')
        connections=',\n'.join(f'.{name}({name})' for _,_,name in ports)
        body=f'module {label}_case(output reg done);\n'+ '\n'.join(declarations)
        body+=f'\n{label}_fifo_probe dut({connections});\n'
        exercise=EXERCISE
        if a.check_saturation:
            exercise='reg saturation=0;\n'+exercise
            exercise=exercise.replace('&& cycle%11!=0 && cycle%11!=1)',
                                      '&& (saturation || (cycle%11!=0 && cycle%11!=1)))')
            exercise=exercise.replace('S00_AXI_0_rready=aresetn && cycle%29>=9;',
                                      'S00_AXI_0_rready=aresetn && (saturation || cycle%29>=9);')
            exercise=exercise.replace('task automatic read_burst(input integer addr,input integer count,input integer seed,input bit id);',
                'task automatic read_burst(input integer addr,input integer count,input integer seed,input bit id);\ninteger previous_read_cycle;')
            exercise=exercise.replace('if(S00_AXI_0_rdata!==pattern(seed,k)',
                'if(saturation && k>=16 && cycle!=previous_read_cycle+1) $fatal(1,"Read throughput regressed k=%0d gap=%0d",k,cycle-previous_read_cycle);\n'
                '  previous_read_cycle=cycle;\n  if(S00_AXI_0_rdata!==pattern(seed,k)')
            exercise=exercise.replace(' if(!overlap || write_beats!=read_beats)',
                ' write_burst(0,256,417,0);\n saturation=1;\n read_burst(0,256,417,1);\n'
                ' @(negedge aclk); saturation=0;\n'
                ' $display("SATURATED_AXI_READ_PASS case=CASE_NAME consecutive_beats=240");\n'
                ' if(!overlap || write_beats!=read_beats)')
        if a.si_width==32:
            exercise=exercise.replace('function automatic [127:0] pattern', 'function automatic [31:0] pattern')
            exercise=exercise.replace('integer wa_base=0,wa_len=0,wa_index=0,ra_base=0,ra_len=0,ra_index=0;',
                'integer wa_base=0,wa_len=0,wa_index=0,ra_base=0,ra_len=0,ra_index=0,wa_size=0,ra_size=0;')
            exercise=exercise.replace('M00_AXI_0_awsize!=4', 'M00_AXI_0_awsize>4')
            exercise=exercise.replace('M00_AXI_0_arsize!=4', 'M00_AXI_0_arsize>4')
            exercise=exercise.replace('wa_index<=0;', 'wa_index<=0; wa_size<=M00_AXI_0_awsize;')
            exercise=exercise.replace('ra_index<=0;', 'ra_index<=0; ra_size<=M00_AXI_0_arsize;')
            exercise=exercise.replace('if(M00_AXI_0_wstrb!==16\'hffff) $fatal(1,"Incorrect WSTRB");',
                'if(!M00_AXI_0_wstrb) $fatal(1,"Empty WSTRB");')
            exercise=exercise.replace('memory[wa_base+wa_index]<=M00_AXI_0_wdata;',
                'for(integer byte_index=0;byte_index<16;byte_index=byte_index+1) '
                'if(M00_AXI_0_wstrb[byte_index]) '
                'memory[wa_base+((wa_index<<wa_size)>>4)][byte_index*8+:8]<=M00_AXI_0_wdata[byte_index*8+:8];')
            exercise=exercise.replace('memory[ra_base+ra_index]', 'memory[ra_base+((ra_index<<ra_size)>>4)]')
            exercise=exercise.replace('S00_AXI_0_awsize=4', 'S00_AXI_0_awsize=2')
            exercise=exercise.replace('S00_AXI_0_arsize=4', 'S00_AXI_0_arsize=2')
            exercise=exercise.replace("S00_AXI_0_wstrb=16'hffff", "S00_AXI_0_wstrb=4'hf")
            # Packing may yield fewer downstream beats than upstream beats;
            # transaction scoreboard, LAST and all upstream data remain checked.
            exercise=exercise.replace('!overlap || write_beats!=read_beats', '!overlap || !write_beats || !read_beats')
        body+=exercise.replace('CASE_NAME',label)+'\nendmodule\n'
        benches.append(body)
    tb='`timescale 1ns/1ps\n'+'\n'.join(benches)+'''
module tb;
wire a,b;
reference_case reference_dut(a); variant_case variant_dut(b);
initial begin wait(a && b); $display("SC_FIFO_OUTPUT_ALL_PASS"); $finish; end
initial begin #10000000; $fatal(1,"AXI verification timeout"); end
endmodule
'''
    (out/'tb.sv').write_text(tb)
    result['source_files']['tb.sv']=sha(out/'tb.sv')
    shutil.copy2(INSTALL/'data/verilog/src/glbl.v',out/'glbl.v')
    result['source_files']['glbl.v']=sha(out/'glbl.v')
    vhdl=[]
    for p in generated.rglob('*.vhd'):
        if p.parent.name!='sim': continue
        dest=out/p.name; shutil.copy2(p,dest); vhdl.append(dest)
        result['source_files'][dest.name]=sha(dest)
    _,env=vendor_runtime(out,INSTALL)
    result['verification_sources']={Path(__file__).name:sha(__file__),
        'targeted_fifo_mapping.py':sha(Path(__file__).parent/'targeted_fifo_mapping.py')}
    for name in result['verification_sources']:
        shutil.copy2(Path(__file__).parent/name,out/name)
    for tool in ('xvlog','xvhdl','xelab','xsim'):
        shutil.copy2(INSTALL/'bin/unwrapped/win64.o'/f'{tool}.exe',out/'vendor_runtime'/f'{tool}.exe')
    helper=Path('D:/weather_builds/joint_prepare_pipeline01_20261101/run_windows_desktop.py')
    def run(name,tool,args,marker=None):
        cmd=[sys.executable,'-E',str(helper),'--',str(out/'vendor_runtime'/f'{tool}.exe'),*map(str,args)]
        with (out/(name+'.log')).open('wb') as log:
            p=subprocess.run(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
        content=(out/(name+'.log')).read_text(errors='replace')
        result['steps'].append({'name':name,'exit_code':p.returncode,'log_sha256':sha(out/(name+'.log'))})
        if p.returncode or (marker and marker not in content) or 'overwriting previous definition of module' in content:
            raise RuntimeError(name+' failed: '+content[-2400:])
    try:
        libraries=['smartconnect_v1_0','proc_sys_reset_v5_0_17','axi_infrastructure_v1_1_0','axi_register_slice_v2_1_36',
                   'unisims_ver','unimacro_ver','secureip','xpm']
        run('compile','xvlog',['--sv','-L','smartconnect_v1_0',*files,out/'tb.sv',out/'glbl.v'])
        if vhdl: run('compile_vhdl','xvhdl',['--relax',*vhdl])
        run('elaborate','xelab',['tb','glbl',*[v for lib in libraries for v in ('-L',lib)],'--snapshot','fifo_axi','--debug','off','--mt','2'])
        run('simulate','xsim',['fifo_axi','-runall'],'SC_FIFO_OUTPUT_ALL_PASS')
        result['changed_channel_nodes']=changed;result['pass']=True
    except Exception as e: result['error']=str(e);raise
    finally:
        shutil.copy2(__file__,out/Path(__file__).name)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'pass':result['pass'],'out':out.as_posix(),'error':result.get('error')}),flush=True)


if __name__=='__main__':main()
