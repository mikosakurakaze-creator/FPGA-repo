"""Verify the exact declared RTL changes before adopting a timing variant.

The D test checks its real top controller with a deterministic frame stub;
it is not a simulation of the convolution datapath or an end-to-end FPS test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from run_checks import ivl_runtime, vendor_runtime


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument('--build', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    root, out = a.build.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    identity = json.loads((root / 'timing_variant.json').read_text())
    baseline = Path(identity['baseline'])
    result = {'pass': False, 'build': root.as_posix(), 'identity_sha256': sha(root/'timing_variant.json'),
              'tests': [], 'board_operations': 0, 'scope': 'RTL change equivalence; D frame datapath stubbed'}
    runtime = ivl_runtime(out, Path('D:/iverilog/install'), Path('D:/m/mingw64/bin'))
    vendor_env = None

    def run(name, command, marker=None):
        if command[0] == 'iverilog':
            command = [runtime/'iverilog.exe', '-B'+str(runtime), *command[1:]]
        elif command[0] == 'vvp':
            command = [runtime/'vvp.exe', *command[1:]]
        elif command[0] in {'xvlog','xelab','xsim'}:
            command = [sys.executable, '-E', baseline/'run_windows_desktop.py','--',
                       out/'vendor_runtime'/(command[0]+'.exe'), *command[1:]]
        p = subprocess.run([str(x) for x in command], cwd=out, capture_output=True,
                           env=vendor_env if name.startswith('d_') else None)
        log = out / (name+'.log')
        log.write_bytes(p.stdout+p.stderr)
        result['tests'].append({'name': name, 'exit_code': p.returncode, 'log_sha256': sha(log),
                                'command': [str(x) for x in command]})
        if p.returncode or (marker and marker not in p.stdout.decode(errors='replace')):
            raise RuntimeError(name+' failed: '+(p.stdout+p.stderr).decode(errors='replace')[-1800:])

    try:
        for change in identity['changes']:
            if sha(root/change['path']) != change['after_sha256'] or sha(baseline/change['path']) != change['before_sha256']:
                raise ValueError('RTL identity changed')
        # Prove no changes other than the declared connections/attribute exist.
        dname = 'ip/compact_d/hdl/verilog/compact_d_top.v'
        before, after = (baseline/dname).read_text(), (root/dname).read_text()
        restored = after.replace('// Bounds were checked with the full 32-bit values before frame starts.\n    ', '')
        restored = restored.replace(".h({22'd0, height_read_reg_282[9:0]}),", '.h(height_read_reg_282),')
        restored = restored.replace(".w({21'd0, width_read_reg_276[10:0]}),", '.w(width_read_reg_276),')
        if before != restored:
            raise ValueError('Unreviewed D changes')
        for anchor in ["((add_ln334_fu_244_p2 > 32'd719)", "((add_ln334_1_fu_255_p2 > 32'd1279)",
                       "ap_predicate_op46_call_state3 = ((or_ln334_reg_302 == 1'd0) & (icmp_ln333_reg_298 == 1'd1))"]:
            if anchor not in before:
                raise ValueError('Frozen bounds/dispatch guard no longer matches')
        checked = 0
        for h in range(1, 721):
            for w in range(1, 1281):
                if (h & 1023) != h or (w & 2047) != w or (h & 1023)*(w & 2047) != h*w:
                    raise ValueError('Legal dimension value changes')
                checked += 1
        result['all_legal_dimension_pairs'] = checked

        cnnname = 'ip/cnn/hdl/verilog/zero_dce_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1.v'
        cnn_before, cnn_after = (baseline/cnnname).read_text(), (root/cnnname).read_text()
        cnn_restored = cnn_after.replace('// Small unpacker address arithmetic: identical pipeline/CE/reset semantics.\n','').replace(', use_dsp="no"','')
        if cnn_restored != cnn_before:
            raise ValueError('CNN change is not only the mapping attribute')
        (out/'cnn_original.v').write_text(cnn_before.replace('zero_dce_cnn_top_', 'reference_cnn_top_'))
        shutil.copy2(root/cnnname, out/'cnn_variant.v')
        cnn_tb = r'''`timescale 1ns/1ps
module tb;
reg clk=0, ce=0, rst=1;
always #5 clk=~clk;
reg [5:0] a=0,b=0,c=0; reg [1:0] d=0;
wire [10:0] oldq,newq;
reference_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1_DSP48_0 old(clk,rst,ce,a,d,b,c,oldq);
zero_dce_cnn_top_ama_addmuladd_6ns_2ns_6ns_6ns_11_4_1_DSP48_0 dut(clk,rst,ce,a,d,b,c,newq);
integer i,checked=0;
initial begin
  for(i=0;i<1048576+8192;i=i+1) begin
    @(negedge clk);
    if(i<1048576) begin {a,d,b,c}=i; ce=1; rst=(i%17==0); end
    else begin {a,d,b,c}=$random; ce=(i%7!=0 && i%7!=1); rst=(i%13==0); end
    @(posedge clk); #1;
    if(newq !== oldq) $fatal(1,"CNN differs cycle=%0d old=%h new=%h",i,oldq,newq);
    if(i>3 && ce) checked=checked+1;
  end
  $display("CNN_ADDRESS_EQ_PASS cycles=%0d",i); $finish;
end
endmodule
'''
        (out/'cnn_tb.sv').write_text(cnn_tb)
        run('cnn_compile', ['iverilog','-g2012','-s','tb','-o','cnn.vvp','cnn_tb.sv','cnn_original.v','cnn_variant.v'])
        run('cnn_sim', ['vvp','cnn.vvp'], 'CNN_ADDRESS_EQ_PASS')

        dwname = 'ip/cnn/hdl/verilog/zero_dce_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1.v'
        declared = {x['path'] for x in identity['changes']}
        expected = {dname, cnnname}
        if identity['variant'] == 'bounded_dimensions_fabric_addresses_hold_v2':
            expected.add(dwname)
            dw_before, dw_after = (baseline/dwname).read_text(), (root/dwname).read_text()
            restored_dw = dw_after.replace('// Small DW window address arithmetic: preserve every register and CE.\n','').replace(', use_dsp="no"','')
            if restored_dw != dw_before:
                raise ValueError('DW address change is not only the mapping attribute')
            (out/'dw_original.v').write_text(dw_before.replace('zero_dce_cnn_top_', 'reference_cnn_top_'))
            shutil.copy2(root/dwname, out/'dw_variant.v')
            (out/'dw_tb.sv').write_text(r'''`timescale 1ns/1ps
module tb;
reg clk=0, ce=0, rst=1;
always #5 clk=~clk;
reg [4:0] a=0; reg [1:0] b=0; reg [5:0] c=0;
wire [10:0] oldq,newq;
reference_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1_DSP48_0 old(clk,rst,ce,a,b,c,oldq);
zero_dce_cnn_top_am_addmul_5ns_2ns_6ns_11_4_1_DSP48_0 dut(clk,rst,ce,a,b,c,newq);
integer i;
initial begin
  for(i=0;i<16384;i=i+1) begin
    @(negedge clk);
    if(i<8192) begin {a,b,c}=i; ce=1; rst=(i%17==0); end
    else begin {a,b,c}=$random; ce=(i%7!=0 && i%7!=1); rst=(i%13==0); end
    @(posedge clk); #1;
    if(newq !== oldq) $fatal(1,"DW address differs cycle=%0d old=%h new=%h",i,oldq,newq);
  end
  $display("DW_ADDRESS_EQ_PASS cycles=%0d",i); $finish;
end
endmodule
''')
            run('dw_compile', ['iverilog','-g2012','-s','tb','-o','dw.vvp','dw_tb.sv','dw_original.v','dw_variant.v'])
            run('dw_sim', ['vvp','dw.vvp'], 'DW_ADDRESS_EQ_PASS')
        if declared != expected:
            raise ValueError('Unexpected set of RTL changes')

        ddir = baseline/'ip/compact_d/hdl/verilog'
        frame = (ddir/'compact_d_top_frame.v').read_text()
        header = re.search(r'module compact_d_top_frame\s*\(.*?\);', frame, re.S).group()
        decls = re.findall(r'^(?:input|output)\s+.*?;', frame, re.M)
        outputs = [re.search(r'(\w+)\s*;', x).group(1) for x in decls if x.startswith('output')]
        controlled = {'ap_done','ap_ready','ap_idle','work_cycles_ap_vld','input_cycles_ap_vld'}
        assigns = '\n'.join('assign '+n+" = '0;" for n in outputs if n not in controlled)
        stub = header+'\n'+'\n'.join(decls)+'\n'+assigns+r'''
reg busy=0,done=0; integer ticks=0;
assign ap_done=done; assign ap_ready=done; assign ap_idle=!busy && !done;
assign work_cycles_ap_vld=done; assign input_cycles_ap_vld=done;
always @(posedge ap_clk) begin
  if(ap_rst) begin busy<=0; done<=0; ticks<=0; end
  else begin
    if(ap_continue) done<=0;
    if(!busy && !done && ap_start) begin busy<=1; ticks<=3; end
    else if(busy) begin
      if(ticks==0) begin busy<=0; done<=1; end else ticks<=ticks-1;
    end
  end
end
endmodule
'''
        (out/'frame_stub.v').write_text(stub)
        # The generated simulation-only deadlock monitor probes the full frame
        # hierarchy. Strip it identically from both controller-only test copies;
        # it is not synthesized and the frame is intentionally a stub here.
        def controller_only(text):
            return re.sub(r'// synthesis translate_off.*?// synthesis translate_on',
                          '// synthesis-only controller test: omit simulation monitor', text, flags=re.S)
        (out/'d_original.v').write_text(controller_only(before).replace('module compact_d_top (','module reference_d_top ('))
        (out/'d_variant.v').write_text(controller_only(after))
        if 'module reference_d_top (' not in (out/'d_original.v').read_text():
            raise ValueError('Could not rename original D top')
        tb = r'''`timescale 1ns/1ps
module tb;
reg clk=0,rstn=0,start=0;
reg [31:0] h=1,w=1,cookie=32'd1145253937;
always #5 clk=~clk;
reference_d_top old(.ap_clk(clk),.ap_rst_n(rstn));
compact_d_top dut(.ap_clk(clk),.ap_rst_n(rstn));
integer seen=0,transactions=0,i; reg [31:0] expected;
initial begin
 force old.height=h; force dut.height=h;
 force old.width=w; force dut.width=w;
 force old.abi_cookie=cookie; force dut.abi_cookie=cookie;
 force old.ap_start=start; force dut.ap_start=start;
end
always @(posedge clk) begin
 #1;
 if(rstn) begin
  if({old.ap_done,old.ap_idle,old.ap_ready,old.ap_return} !== {dut.ap_done,dut.ap_idle,dut.ap_ready,dut.ap_return})
    $fatal(1,"D top controller differs");
  if(old.grp_frame_fu_190_ap_start !== dut.grp_frame_fu_190_ap_start) $fatal(1,"Frame scheduling differs");
  if(dut.grp_frame_fu_190_ap_start) begin
    if(expected!=0) $fatal(1,"Invalid request entered frame");
    if({old.grp_frame_fu_190.h,old.grp_frame_fu_190.w} !== {dut.grp_frame_fu_190.h,dut.grp_frame_fu_190.w})
       $fatal(1,"Frame dimension inputs differ");
    seen=seen+1;
  end
 end
end
task request(input [31:0] hh,ww,cc);
 integer n;
 begin
  @(negedge clk); h=hh; w=ww; cookie=cc; seen=0;
  expected=cc!=32'd1145253937 ? 32'hffffffff : ((hh<1 || hh>720 || ww<1 || ww>1280) ? 32'hfffffffe:0);
  start=1;
  begin : wait_done
    for(n=0;n<80;n=n+1) begin
      @(posedge clk); #2;
      if(dut.ap_done) begin
        if(dut.ap_return!==expected) $fatal(1,"Wrong status h=%h w=%h got=%h expected=%h",hh,ww,dut.ap_return,expected);
        if(expected==0 && seen==0) $fatal(1,"Valid request never entered frame");
        if(expected!=0 && seen!=0) $fatal(1,"Invalid request entered frame");
        disable wait_done;
      end
    end
    $fatal(1,"Controller timeout");
  end
  @(negedge clk); start=0;
  repeat(5) @(posedge clk);
  transactions=transactions+1;
 end
endtask
initial begin
 repeat(4) @(negedge clk); rstn=1;
 request(1,1,1145253937); request(720,1272,1145253937); request(720,1280,1145253937);
 request(0,1,1145253937); request(1,0,1145253937); request(721,1280,1145253937);
 request(720,1281,1145253937); request(1024,2048,1145253937);
 request(32'hffffffff,1,1145253937); request(1,32'hffffffff,1145253937);
 request(32'h80000001,1,1145253937); request(1,32'h80000001,1145253937);
 request(720,1272,0); request(0,0,0);
 for(i=0;i<512;i=i+1) begin
   request(1+(i*131)%720,1+(i*251)%1280,1145253937);
   request($random,$random,1145253937);
 end
 $display("D_CONTROLLER_EQ_PASS transactions=%0d",transactions); $finish;
end
endmodule
'''
        (out/'d_tb.sv').write_text(tb)
        # Unused convolution modules are not elaborated: frame() is the stub.
        others = [ddir/n for n in ('compact_d_top_control_s_axi.v',
                                  'compact_d_top_gmem_in_m_axi.v',
                                  'compact_d_top_gmem_out_m_axi.v')]
        files = ['d_tb.sv','d_original.v','d_variant.v','frame_stub.v', *[p.as_posix() for p in others]]
        if any(' ' in p for p in files):
            raise ValueError('Icarus file-list paths must be staged without spaces')
        (out/'d_files.f').write_text('\n'.join(files)+'\n')
        _, vendor_env = vendor_runtime(out, Path('D:/vivado/2025.2/Vivado'))
        vendor_env.pop('SHELL', None)
        for tool in ('xvlog','xelab','xsim'):
            shutil.copy2(Path('D:/vivado/2025.2/Vivado/bin/unwrapped/win64.o')/(tool+'.exe'),
                         out/'vendor_runtime'/(tool+'.exe'))
        run('d_compile', ['xvlog','--sv', *files])
        run('d_elaborate', ['xelab','tb','--snapshot','d_equivalence','--debug','off','--mt','2'])
        run('d_sim', ['xsim','d_equivalence','-runall'], 'D_CONTROLLER_EQ_PASS')
        result['pass'] = True
        result['rtl_semantics'] = 'Only bounded frame arguments and declared synthesis mapping attributes differ; no latency/CE/reset/handshake edits.'
        result['not_tested'] = ['Full six-core RTL simulation','Post-route hardware equivalence','Board image accuracy','Board FPS']
    except Exception as e:
        result['error'] = str(e)
        raise
    finally:
        shutil.copy2(__file__, out/'verify_timing_variant.py')
        result['evidence'] = {p.name: sha(p) for p in out.iterdir() if p.suffix in {'.sv','.v','.log','.py'}}
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in {'tests','evidence'}}, indent=2))


if __name__ == '__main__':
    main()
