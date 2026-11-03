"""Exercise the exact derived FIFO/RAM RTL against its frozen parent each cycle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from prepare_fifo_storage_variant import D_NAMES, transform
from run_checks import ivl_runtime


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


FIFO_TB = r'''`timescale 1ns/1ps
module tb;
localparam W=WIDTH;
reg clk=0, reset=1, wce=0, we=0, rce=0, re=0;
reg [W-1:0] din=0;
always #5 clk=~clk;
wire ofull,nfull,oempty,nempty;
wire [5:0] onum,nnum,ocap,ncap;
wire [W-1:0] oq,nq;
original_MODULE old(clk,reset,ofull,wce,we,din,onum,ocap,oempty,rce,re,oq);
MODULE dut(clk,reset,nfull,wce,we,din,nnum,ncap,nempty,rce,re,nq);
integer i,j,full_stall=0,empty_stall=0,both=0,ce_stall=0,reset_busy=0;
reg [31:0] prng=32'h8a3729d1;
initial begin
 for(i=0;i<40000;i=i+1) begin
  @(negedge clk);
  prng=prng ^ (prng << 13); prng=prng ^ (prng >> 17); prng=prng ^ (prng << 5);
  reset=(i<4 || i%997==0);
  if (reset && oempty) reset_busy=reset_busy+1;
  wce=prng[1]; rce=prng[4]; we=prng[8]; re=prng[12];
  if(i%1000<200) begin wce=1; we=1; rce=0; re=0; end
  if(i%1000>=200 && i%1000<400) begin wce=0; we=0; rce=1; re=1; end
  if(i%1000>=400 && i%1000<600) begin wce=1; we=1; rce=1; re=1; end
  for(j=0;j<W;j=j+1) din[j]=prng[j%32] ^ ((i+j)%7==0);
  if(!reset) begin
   if(wce && we && !ofull) full_stall=full_stall+1;
   if(rce && re && !oempty) empty_stall=empty_stall+1;
   if(wce && we && ofull && rce && re && oempty) both=both+1;
   if(!wce || !rce) ce_stall=ce_stall+1;
  end
  @(posedge clk); #1;
  if({ofull,oempty,onum,ocap} !== {nfull,nempty,nnum,ncap})
   $fatal(1,"FIFO controls differ cycle=%0d",i);
  if(oq !== nq) $fatal(1,"FIFO data differs cycle=%0d old=%h new=%h",i,oq,nq);
 end
 if(!full_stall || !empty_stall || !both || !ce_stall || !reset_busy)
  $fatal(1,"Missing FIFO coverage");
 $display("FIFO_STORAGE_EQ_PASS cycles=%0d full=%0d empty=%0d simultaneous=%0d ce=%0d reset_busy=%0d",
 i,full_stall,empty_stall,both,ce_stall,reset_busy);
 $finish;
end
endmodule
'''

RAM_TB = r'''`timescale 1ns/1ps
module tb;
localparam W=WIDTH, AW=ADDRWIDTH, N=DEPTH;
reg clk=0,reset=0,ce0=0,ce1=0,we1=0;
reg [AW-1:0] a0=0,a1=0;
reg [W-1:0] din=0;
wire [W-1:0] oq,nq;
always #5 clk=~clk;
original_MODULE old(a0,ce0,oq,a1,ce1,din,we1,reset,clk);
MODULE dut(a0,ce0,nq,a1,ce1,din,we1,reset,clk);
integer i,j,collisions=0,read_stalls=0,both=0,odd=0,even=0;
reg [31:0] prng=32'h291fab31;
initial begin
 for(i=0;i<N;i=i+1) begin
  @(negedge clk); a1=i; ce1=1; we1=1; din=i*37+5;
  @(posedge clk); #1;
 end
 for(i=0;i<40000;i=i+1) begin
  @(negedge clk);
  prng=prng ^ (prng << 13); prng=prng ^ (prng >> 17); prng=prng ^ (prng << 5);
  a0=prng%N; a1=(prng>>10)%N; ce0=prng[2]; ce1=prng[7]; we1=prng[13]; reset=(i%19==0);
  if(i%7==0) begin a1=a0; ce0=1; ce1=1; we1=1; end
  for(j=0;j<W;j=j+1) din[j]=prng[j%32] ^ ((i+j)%5==0);
  if(ce0 && ce1 && we1 && a0==a1) collisions=collisions+1;
  if(!ce0) read_stalls=read_stalls+1;
  if(ce0 && ce1 && we1) both=both+1;
  if(ce0 && a0[0]) odd=odd+1;
  if(ce0 && !a0[0]) even=even+1;
  @(posedge clk); #1;
  if(oq !== nq) $fatal(1,"RAM data differs cycle=%0d old=%h new=%h",i,oq,nq);
 end
 if(!collisions || !read_stalls || !both || !odd || !even) $fatal(1,"Missing RAM coverage");
 $display("RAM_STORAGE_EQ_PASS cycles=%0d collisions=%0d ce=%0d simultaneous=%0d odd=%0d even=%0d",
 i,collisions,read_stalls,both,odd,even); $finish;
end
endmodule
'''


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(); build=a.build.resolve(); out=a.out.resolve()
    identity=json.loads((build/'fifo_storage_variant.json').read_text())
    baseline=Path(identity['baseline'])
    out.mkdir(parents=True,exist_ok=False)
    result={'pass':False,'build':build.as_posix(),'identity_sha256':sha(build/'fifo_storage_variant.json'),
            'scope':'Exact cycle RTL comparison for the seven changed memory templates; not joint RTL or routed timing',
            'board_operations':0,'tests':[]}
    runtime=ivl_runtime(out,Path('D:/iverilog/install'),Path('D:/m/mingw64/bin'))
    (out/'LUT2.v').write_text('module LUT2 #(parameter [3:0] INIT=0)(input I0,I1,output O); assign O=INIT[{I1,I0}]; endmodule\n')
    def run(name,cmd,marker=None,expected_fail=False):
        p=subprocess.run(list(map(str,cmd)),cwd=out,capture_output=True)
        path=out/(name+'.log'); path.write_bytes(p.stdout+p.stderr)
        text=(p.stdout+p.stderr).decode(errors='replace')
        result['tests'].append({'name':name,'exit_code':p.returncode,'expected_failure':expected_fail,'log_sha256':sha(path)})
        if expected_fail:
            if not p.returncode or 'data differs' not in text: raise RuntimeError('Negative control was not detected')
        elif p.returncode or (marker and marker not in text): raise RuntimeError(name+' failed: '+text[-2000:])
        return text
    try:
        for index,change in enumerate(identity['changes']):
            name=change['path']; before=(baseline/name).read_text(); after=(build/name).read_text()
            if sha(baseline/name)!=change['before_sha256'] or sha(build/name)!=change['after_sha256']:
                raise ValueError('Changed memory source identity')
            if after!=transform(before,fifo=name in D_NAMES): raise ValueError('Undeclared memory edits')
            module=re.search(r'\bmodule\s+(\w+)',before).group(1)
            original=re.sub(r'\b'+re.escape(module)+r'(?=\b|_ram\b)', 'original_'+module,before)
            (out/'original.v').write_text(original)
            (out/'variant.v').write_text(after)
            width=int(re.search(r'(?:DATA_WIDTH\s*=|DataWidth\s*=)\s*(\d+)',before).group(1))
            if name in D_NAMES: tb=FIFO_TB; marker='FIFO_STORAGE_EQ_PASS'
            else:
                aw=re.search(r'AddressWidth\s*=\s*(\d+)',before).group(1)
                depth=re.search(r'AddressRange\s*=\s*(\d+)',before).group(1)
                tb=RAM_TB.replace('ADDRWIDTH',aw).replace('DEPTH',depth); marker='RAM_STORAGE_EQ_PASS'
            tb=tb.replace('MODULE',module).replace('WIDTH',str(width))
            (out/'tb.sv').write_text(tb)
            files=['tb.sv','original.v','variant.v','LUT2.v']
            run(f'compile_{index}',[runtime/'iverilog.exe','-B'+str(runtime),'-g2012','-s','tb','-o','test.vvp',*files])
            log=run(f'sim_{index}',[runtime/'vvp.exe','test.vvp'],marker)
            result['tests'][-1]['memory']=name
            result['tests'][-1]['success_line']=next(x for x in log.splitlines() if x.startswith(marker))
            if index==0:
                (out/'variant.v').write_text(after.replace(".INIT(4'h6)",".INIT(4'h9)"))
                run('negative_compile',[runtime/'iverilog.exe','-B'+str(runtime),'-g2012','-s','tb','-o','negative.vvp',*files])
                run('negative_sim',[runtime/'vvp.exe','negative.vvp'],expected_fail=True)
                (out/'variant.v').write_text(after)
        result['changed_memory_templates']=len(identity['changes'])
        result['cycles_compared']=40000*len(identity['changes'])
        result['pass']=True
    except Exception as e:
        result['error']=str(e); raise
    finally:
        shutil.copy2(__file__,out/Path(__file__).name)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__': main()
