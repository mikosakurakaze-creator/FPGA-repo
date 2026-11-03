"""Probe an explicit bounded h*w multiplier without changing an active build.

This creates only an isolated candidate and local evidence. It cannot export
a hardware delivery, and its OOC results are not full-system timing signoff.
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

FILES = [f'compact_d_top_add_relu_{i}_s.v' for i in range(3)] + [
    'compact_d_top_finish_r.v', 'compact_d_top_pack_input.v',
    *[f'compact_d_top_relu_{i}_s.v' for i in (14, 2, 4, 9)],
    *[f'compact_d_top_residual_block_{i}_Block_entry_proc.v' for i in range(3)]]
CORE = 'compact_d_top_mul_32s_32s_32_1_1'

TB = r'''module tb;
reg [31:0] h, w;
wire [31:0] original, narrowed;
integer hi, wi, checked;
compact_d_top_mul_32s_32s_32_1_1 #(.din0_WIDTH(32), .din1_WIDTH(32), .dout_WIDTH(32))
old_mul(.din0(w), .din1(h), .dout(original));
compact_d_top_mul_32s_32s_32_1_1 #(.din0_WIDTH(12), .din1_WIDTH(11), .dout_WIDTH(32))
new_mul(.din0({1'b0,w[10:0]}), .din1({1'b0,h[9:0]}), .dout(narrowed));
initial begin
  checked=0;
  for(hi=1;hi<=720;hi=hi+1) begin
    for(wi=1;wi<=1280;wi=wi+1) begin
      h=hi; w=wi; #1;
      if(original !== narrowed || narrowed !== hi*wi)
        $fatal(1,"DIMENSION_MISMATCH h=%d w=%d original=%d narrowed=%d",h,w,original,narrowed);
      checked=checked+1;
    end
  end
  $display("DIMENSION_MULTIPLIER_EQ_PASS pairs=%0d",checked);
  $finish;
end
endmodule
'''

PROBE = r'''module dimension_mul_probe(input clk, input [31:0] h, w,
 output reg [31:0] old_result, narrow_result);
reg [31:0] h_reg, w_reg;
wire [31:0] old_product, narrow_product;
always @(posedge clk) begin
 h_reg<=h; w_reg<=w; old_result<=old_product; narrow_result<=narrow_product;
end
compact_d_top_mul_32s_32s_32_1_1 #(.din0_WIDTH(32), .din1_WIDTH(32), .dout_WIDTH(32))
original(.din0(w_reg), .din1(h_reg), .dout(old_product));
compact_d_top_mul_32s_32s_32_1_1 #(.din0_WIDTH(12), .din1_WIDTH(11), .dout_WIDTH(32))
narrow(.din0({1'b0,w_reg[10:0]}), .din1({1'b0,h_reg[9:0]}), .dout(narrow_product));
endmodule
'''

TCL = r'''set_param general.maxThreads 2
read_verilog [list compact_d_top_mul_32s_32s_32_1_1.v dimension_mul_probe.v]
synth_design -mode out_of_context -top dimension_mul_probe -part xck26-sfvc784-2LV-c -flatten_hierarchy none
create_clock -period 5.0 [get_ports clk]
report_utilization -hierarchical -file utilization.rpt
report_timing_summary -delay_type min_max -file estimated_timing.rpt
# Vivado expands each DSP48E2 into internal DSP_* cells. In this pure
# multiplier probe, one DSP_MULTIPLIER cell identifies one used DSP block.
set old [get_cells -hierarchical -filter {NAME =~ original/* && REF_NAME == DSP_MULTIPLIER}]
set new [get_cells -hierarchical -filter {NAME =~ narrow/* && REF_NAME == DSP_MULTIPLIER}]
puts "DIMENSION_DSP_MAPPING original=[llength $old] narrow=[llength $new]"
if {[llength $new] != 1 || [llength $old] <= [llength $new]} {error {Expected one bounded multiplier DSP and a reduction from the original}}
puts {DIMENSION_MAPPING_PROBE_PASS}
exit
'''


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--source-build', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--ivl-runtime', required=True, type=Path)
    p.add_argument('--synthesize', action='store_true')
    a = p.parse_args()
    source, out = a.source_build.resolve(), a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'pass': False, 'export_allowed': False, 'changes': [], 'steps': [],
              'source_build': source.as_posix(), 'scope': 'Bounded combinational product and OOC mapping only',
              'not_tested': ['Full D simulation', 'Joint routed timing', 'Board behavior']}
    shutil.copy2(__file__, out/'probe_dimension_multiplier.py')

    def run(name, command, env=None):
        with (out/(name+'.log')).open('xb') as log:
            proc = subprocess.run([str(v) for v in command], cwd=out, env=env,
                                  stdout=log, stderr=subprocess.STDOUT)
        result['steps'].append({'name': name, 'command': [str(v) for v in command],
                                'exit_code': proc.returncode, 'log_sha256': sha(out/(name+'.log'))})
        if proc.returncode:
            raise RuntimeError(name+' failed')
        return (out/(name+'.log')).read_text(errors='replace')

    try:
        manifest = json.loads((source/'inputs.json').read_text())
        prefix = 'ip/compact_d/hdl/verilog/'
        for name in [*FILES, CORE+'.v']:
            old = source/prefix/name
            if sha(old) != manifest['source_files'][prefix+name]:
                raise ValueError('Source identity changed: '+name)
            if name == CORE+'.v':
                shutil.copy2(old, out/name)
                result['multiplier_core_sha256'] = sha(old)
                continue
            text = old.read_text()
            matches = re.findall(r'(?s)'+CORE+r' #\(.*?\);', text)
            if len(matches) != 1 or '.din0(w),' not in matches[0] or '.din1(h),' not in matches[0]:
                raise ValueError('Unexpected dimension multiplier: '+name)
            block = matches[0]
            new = block.replace('.din0_WIDTH( 32 )', '.din0_WIDTH( 12 )').replace(
                '.din1_WIDTH( 32 )', '.din1_WIDTH( 11 )').replace(
                '.din0(w),', ".din0({1'b0, w[10:0]}),").replace(
                '.din1(h),', ".din1({1'b0, h[9:0]}),")
            (out/name).write_text(text.replace(block,new), encoding='utf-8', newline='\n')
            result['changes'].append({'path': prefix+name, 'before_sha256': sha(old),
                                      'after_sha256': sha(out/name)})
        (out/'tb.sv').write_text(TB,encoding='utf-8')
        (out/'dimension_mul_probe.v').write_text(PROBE,encoding='utf-8')
        (out/'probe.tcl').write_text(TCL,encoding='utf-8')
        runtime = a.ivl_runtime.resolve()
        run('compile',[runtime/'iverilog.exe','-B'+str(runtime),'-g2012','-s','tb','-o','test.vvp','tb.sv',CORE+'.v'])
        sim = run('simulation',[runtime/'vvp.exe','test.vvp'])
        if 'DIMENSION_MULTIPLIER_EQ_PASS pairs=921600' not in sim:
            raise ValueError('Missing exhaustive equivalence completion marker')
        result['legal_dimension_pairs_checked'] = 921600
        if a.synthesize:
            exe, env = vendor_runtime(out,Path('D:/vivado/2025.2/Vivado'))
            env.pop('SHELL',None)
            log = run('synthesis',[sys.executable,'-E','D:/weather_builds/joint_prepare_pipeline01_20261101/run_windows_desktop.py',
                      '--',exe,'-mode','batch','-log',out/'vivado.log','-journal',out/'vivado.jou','-source',out/'probe.tcl'],env)
            if re.search(r'^ERROR:',log,re.M) or 'DIMENSION_MAPPING_PROBE_PASS' not in log.splitlines():
                raise ValueError('OOC mapping probe failed')
            match = re.search(r'^DIMENSION_DSP_MAPPING original=(\d+) narrow=(\d+)$',log,re.M)
            if not match:
                raise ValueError('Missing DSP mapping counts')
            result['ooc_dsp_count'] = {'original':int(match[1]),'narrow':int(match[2])}
        result['pass'] = True
    except Exception as e:
        result['error'] = str(e)
        raise
    finally:
        result['evidence'] = {f.name:sha(f) for f in out.iterdir() if f.is_file() and f.suffix in ('.v','.sv','.tcl','.py','.log','.rpt')}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='evidence'},indent=2),flush=True)


if __name__ == '__main__':
    main()
