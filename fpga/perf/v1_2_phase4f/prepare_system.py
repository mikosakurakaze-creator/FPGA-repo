"""Prepare exactly eight frames with unchanged scheduling and passive observers.

Only the already-validated Phase 4E writer overlays replace frozen RTL.
Elaboration is simulation compilation, never HLS synthesis/export or implementation.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path('E:/HLS/kv260_three_module_v1_2_phase4')
BASE = ROOT / 'phase4b_build_02'
E = ROOT / 'phase4e_system_02'
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
CONFIG = dict(FRAMES=8, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2,
              DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128, CLOCK_MHZ=100)


def observer():
    writer = 'dut.zero_dce_cnn_top_0.inst.grp_p_anonymous_namespace_group_rowstream_block_fu_420.p_anonymous_namespace_output_writer_U0'
    head = r'''
  // PHASE4F passive observers: no signals driven, no waits inserted.
  integer f_owner_file,f_wait_file,f_occ_file,f_ddr_file,f_drain_file,f_stage_drain_file;
  integer f_prev_owner[0:4][0:1],f_owners[0:4][0:1];
  longint f_occ[0:4][0:1],f_dep[0:2][0:7],f_buffer[0:2][0:7];
  longint f_both[0:2][0:7],f_ready[0:2][0:7];
  integer f_peak[0:4],f_mask,f_previous_mask=-1,f_writer_drains=0;
  integer f_triple_rmax[0:3],f_triple_wmax[0:3];
  longint f_prev_first[0:3],f_prev_b[0:3],f_triple_firstmax[0:3],f_triple_bmax[0:3];
  longint f_triple_cycles=0;
  bit f_dependency,f_buffer_block;
  wire [1:0] f_credit_ws=WRITER.grp_row_axi_writer_fu_171.credit_count;
  wire [1:0] f_credit_out=WRITER.grp_row_axi_writer_2_fu_181.credit_count;
  wire f_writer_done=WRITER.ap_done;
  bit f_previous_writer_done=0;
  task f_ddr_snapshot(input integer mask);
    begin
      for(integer h=0;h<4;h=h+1)
        $fdisplay(f_ddr_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cycle,mask,h,ddr.arcs[h],ddr.awcs[h],ddr.rbeats[h],ddr.wbeats[h],ddr.ar_stalls[h],ddr.aw_stalls[h],ddr.r_stalls[h],ddr.r_backpressure[h],ddr.w_stalls[h],ddr.b_wait[h],ddr.rq_sum[h],ddr.wq_sum[h],ddr.first_r_samples[h],ddr.first_r_sum[h],ddr.first_r_max[h],ddr.b_samples[h],ddr.b_latency_sum[h],ddr.b_latency_max[h],ddr.rc[h],ddr.wc[h],ddr.rq_max[h],ddr.wq_max[h],ddr.service_beats,ddr.contested_cycles,ddr.rw_concurrent_cycles);
      $fflush(f_ddr_file);
    end
  endtask
  task phase4f_finish;
    begin
      if(frames!=8 || completed[0]!=8 || completed[1]!=8 || completed[2]!=8 || frames_checked!=8) $fatal(1,"PHASE4F incomplete eight frames");
      if(f_writer_drains!=56) $fatal(1,"PHASE4F missing CNN writer drains");
      f_ddr_snapshot(-1);
      for(integer b=0;b<5;b=b+1) for(integer s=0;s<2;s=s+1) begin
        if(f_owners[b][s]!=-1) $fatal(1,"PHASE4F retained buffer owner");
        $fdisplay(f_occ_file,"%0d,%0d,%0d,%0d",b,s,f_occ[b][s],f_peak[b]);
      end
      for(integer t=0;t<3;t=t+1) for(integer n=0;n<8;n=n+1)
        $fdisplay(f_wait_file,"%0d,%0d,%0d,%0d,%0d,%0d",t,n,f_dep[t][n],f_buffer[t][n],f_both[t][n],f_ready[t][n]);
      for(integer h=0;h<4;h=h+1) $display("PHASE4F_TRIPLE HP=%0d CYCLES=%0d READ_MAX=%0d WRITE_MAX=%0d FIRST_R_MAX=%0d B_LATENCY_MAX=%0d",h,f_triple_cycles,f_triple_rmax[h],f_triple_wmax[h],f_triple_firstmax[h],f_triple_bmax[h]);
      $display("PHASE4F_PASSIVE_FINAL WRITER_DRAINS=%0d CREDIT_WS=%0d CREDIT_OUT=%0d OWNERS_RELEASED=1",f_writer_drains,f_credit_ws,f_credit_out);
      $fclose(f_owner_file);$fclose(f_wait_file);$fclose(f_occ_file);$fclose(f_ddr_file);$fclose(f_drain_file);$fclose(f_stage_drain_file);
    end
  endtask
  initial begin
    if(!$value$plusargs("OUTPUT_DIR=%s",output_dir)) output_dir=".";
    f_owner_file=$fopen({output_dir,"/ownership_events.csv"},"w");$fdisplay(f_owner_file,"cycle,buffer,slot,previous,owner");
    f_wait_file=$fopen({output_dir,"/wait_stats.csv"},"w");$fdisplay(f_wait_file,"stage,frame,dependency,buffer,both,ready");
    f_occ_file=$fopen({output_dir,"/slot_occupancy.csv"},"w");$fdisplay(f_occ_file,"buffer,slot,occupied_cycles,peak_slots");
    f_ddr_file=$fopen({output_dir,"/ddr_snapshots.csv"},"w");$fdisplay(f_ddr_file,"cycle,mask,hp,ar,aw,r,w,ar_stall,aw_stall,r_stall,r_back,w_stall,b_wait,rq_sum,wq_sum,first_samples,first_sum,first_max,b_samples,b_sum,b_max,rc,wc,rq_max,wq_max,served,contested,rw_concurrent");
    f_drain_file=$fopen({output_dir,"/writer_drains.csv"},"w");$fdisplay(f_drain_file,"cycle,frame,drain,credit_ws,credit_out,ddr_rc,ddr_wc,ddr_wp");
    f_stage_drain_file=$fopen({output_dir,"/stage_drains.csv"},"w");$fdisplay(f_stage_drain_file,"cycle,stage,frame,hp,rc,wc,wp,rvalid,bvalid");
    for(integer b=0;b<5;b=b+1) begin f_peak[b]=0;for(integer s=0;s<2;s=s+1) begin f_prev_owner[b][s]=-1;f_owners[b][s]=-1;f_occ[b][s]=0;end end
    for(integer t=0;t<3;t=t+1) for(integer n=0;n<8;n=n+1) begin f_dep[t][n]=0;f_buffer[t][n]=0;f_both[t][n]=0;f_ready[t][n]=0;end
    for(integer h=0;h<4;h=h+1) begin f_triple_rmax[h]=0;f_triple_wmax[h]=0;f_prev_first[h]=0;f_prev_b[h]=0;f_triple_firstmax[h]=0;f_triple_bmax[h]=0;end
  end
  always @(negedge ap_clk) if(ap_rst_n) begin
    f_mask=(monitoring[0]?1:0)+(monitoring[1]?2:0)+(monitoring[2]?4:0);
    if(f_mask!=f_previous_mask) begin f_ddr_snapshot(f_mask);f_previous_mask=f_mask;end
    if(f_mask==7) f_triple_cycles=f_triple_cycles+1;
    for(integer h=0;h<4;h=h+1) begin
      if(f_mask==7) begin
        if(ddr.rc[h]>f_triple_rmax[h]) f_triple_rmax[h]=ddr.rc[h];
        if(ddr.wc[h]>f_triple_wmax[h]) f_triple_wmax[h]=ddr.wc[h];
        if(ddr.first_r_sum[h]-f_prev_first[h]>f_triple_firstmax[h]) f_triple_firstmax[h]=ddr.first_r_sum[h]-f_prev_first[h];
        if(ddr.b_latency_sum[h]-f_prev_b[h]>f_triple_bmax[h]) f_triple_bmax[h]=ddr.b_latency_sum[h]-f_prev_b[h];
      end
      f_prev_first[h]=ddr.first_r_sum[h];f_prev_b[h]=ddr.b_latency_sum[h];
    end
    for(integer s=0;s<2;s=s+1) begin
      f_owners[0][s]=low_owner[s];f_owners[1][s]=full_owner[s];f_owners[2][s]=enh_owner[s];f_owners[3][s]=input_owner[s];f_owners[4][s]=model_owner[s];
    end
    for(integer b=0;b<5;b=b+1) begin
      if((f_owners[b][0]>=0)+(f_owners[b][1]>=0)>f_peak[b]) f_peak[b]=(f_owners[b][0]>=0)+(f_owners[b][1]>=0);
      for(integer s=0;s<2;s=s+1) begin
        if(f_owners[b][s]!=f_prev_owner[b][s]) begin
          if(f_prev_owner[b][s]>=0 && f_owners[b][s]>=0) $fatal(1,"PHASE4F owner overwritten without release");
          $fdisplay(f_owner_file,"%0d,%0d,%0d,%0d,%0d",cycle,b,s,f_prev_owner[b][s],f_owners[b][s]);f_prev_owner[b][s]=f_owners[b][s];$fflush(f_owner_file);
        end
        if(f_owners[b][s]>=0) f_occ[b][s]=f_occ[b][s]+1;
      end
    end
    for(integer t=0;t<3;t=t+1) if(!running[t] && next_frame[t]<8) begin
      f_dependency=t==0?0:!frame_done[t-1][next_frame[t]];
      // Exclude this frame's reservation while its CSR pointers are programmed.
      // Only a different frame retaining the target slot is consumer backpressure.
      if(t==0) f_buffer_block=(low_owner[next_frame[t]%2]!=-1 && low_owner[next_frame[t]%2]!=next_frame[t]) || (input_owner[next_frame[t]%2]!=-1 && input_owner[next_frame[t]%2]!=next_frame[t]);
      else if(t==1) f_buffer_block=full_owner[next_frame[t]%2]!=-1 && full_owner[next_frame[t]%2]!=next_frame[t];
      else f_buffer_block=(enh_owner[next_frame[t]%2]!=-1 && enh_owner[next_frame[t]%2]!=next_frame[t]) || (model_owner[next_frame[t]%2]!=-1 && model_owner[next_frame[t]%2]!=next_frame[t]);
      if(f_dependency) f_dep[t][next_frame[t]]=f_dep[t][next_frame[t]]+1;
      if(f_buffer_block) f_buffer[t][next_frame[t]]=f_buffer[t][next_frame[t]]+1;
      if(f_dependency && f_buffer_block) f_both[t][next_frame[t]]=f_both[t][next_frame[t]]+1;
      if(!f_dependency && !f_buffer_block) f_ready[t][next_frame[t]]=f_ready[t][next_frame[t]]+1;
    end
  end
  always @(posedge ap_clk) if(ap_rst_n) begin
    if(f_credit_ws>2 || f_credit_out>2) $fatal(1,"PHASE4F credit limit violated");
    if(f_writer_done && !f_previous_writer_done) begin
      if(f_credit_ws!==0 || f_credit_out!==0 || ddr.wc[0]!=0 || ddr.wp[0]!=0 || ddr.bvalid[0]) $fatal(1,"PHASE4F CNN writer response retained");
      f_writer_drains=f_writer_drains+1;
      $fdisplay(f_drain_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cycle,active_frame[0],f_writer_drains,f_credit_ws,f_credit_out,ddr.rc[0],ddr.wc[0],ddr.wp[0]);$fflush(f_drain_file);
    end
    f_previous_writer_done=f_writer_done;
  end
  task phase4f_stage_drained(input integer t,input integer n);
    begin
      for(integer h=0;h<4;h=h+1) if((t==0 && h<=1) || (t>0 && h==t+1)) begin
        if(ddr.rc[h]!=0 || ddr.wc[h]!=0 || ddr.wp[h]!=0 || ddr.rvalid[h] || ddr.bvalid[h]) $fatal(1,"PHASE4F stage response crosses buffer release");
        $fdisplay(f_stage_drain_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cycle,t,n,h,ddr.rc[h],ddr.wc[h],ddr.wp[h],ddr.rvalid[h],ddr.bvalid[h]);$fflush(f_stage_drain_file);
      end
    end
  endtask
'''
    return head.replace('WRITER.', writer + '.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='phase4f_system_01')
    args = parser.parse_args()
    assert args.name.startswith('phase4f_') and args.name.replace('_', '').isalnum()
    out = ROOT / args.name
    assert not out.exists(), out
    frozen = json.loads((BASE / 'source_manifest.json').read_text())
    prior = json.loads((E / 'run_manifest.json').read_text())
    prior_gate = json.loads((E / 'analysis.json').read_text())
    assert prior_gate['numerical']['raw_mismatch'] == 0
    assert prior_gate['stage_gate'] == 'CNN_SYSTEM_STAGE_30FPS_PASS'
    for item in frozen['source_files']:
        assert SHA(Path(item['path'])) == item['sha256'], item['path']
    for name, key in [('shared_axi_ddr.sv', 'ddr_model_sha256'), ('phase4_pl.v', 'pl_wrapper_sha256'), ('system_tb.sv', 'generated_tb_sha256')]:
        assert SHA(BASE / name) == frozen[key]
    for item in prior['substitutions']:
        assert SHA(Path(item['candidate'])) == item['candidate_sha256']
    out.mkdir()
    (out / 'results').mkdir()
    shutil.copy2(Path('E:/github/-/fpga/reports/v1_2_phase4_checkpoint.md'), out / 'checkpoint_before.md')
    for p in BASE.iterdir():
        if p.is_file() and (p.suffix in ('.hex', '.dat') or p.name in ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt')):
            shutil.copy2(p, out / p.name)
    project = (BASE / 'system.prj').read_text().replace(BASE.as_posix(), out.as_posix())
    for item in prior['substitutions']:
        assert project.count('"' + item['original'] + '"') == 1
        project = project.replace('"' + item['original'] + '"', '"' + item['candidate'] + '"')
    (out / 'system.prj').write_text(project)
    tb = (BASE / 'system_tb.sv').read_text()
    assert tb.count('    ddr.print_stats();') == 1
    tb = tb.replace('    ddr.print_stats();', '    phase4f_finish();\n    ddr.print_stats();')
    assert tb.count('            numerical_check(m,f);') == 1
    tb = tb.replace('            numerical_check(m,f);', '            phase4f_stage_drained(m,f);\n            numerical_check(m,f);')
    tb = tb.replace('if(frames<1 || frames>100) $fatal(1,"FRAMES must be 1..100");', 'if(frames!=8) $fatal(1,"PHASE4F requires FRAMES=8");')
    appended = observer()
    assert tb.endswith('endmodule\n')
    (out / 'observer_append.sv').write_text(appended)
    (out / 'system_tb.sv').write_text(tb[:-len('endmodule\n')] + appended + 'endmodule\n')
    (out / 'run.tcl').write_text('run all\nquit\n')
    env = '@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\ncall "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n' + f'cd /d "{out}"\n'
    (out / 'elaborate.cmd').write_text(env + 'call xelab --relax --mt 2 -prj system.prj -f xelab_options.txt xil_defaultlib.phase4_system_tb xil_defaultlib.glbl -s phase4f_system -log elaborate.log\nexit /b %errorlevel%\n')
    parameters = ' '.join('-testplusarg "' + k + '=' + str(v) + '"' for k, v in CONFIG.items() if k != 'CLOCK_MHZ')
    (out / 'simulate.cmd').write_text(env + f'call xsim phase4f_system -tclbatch run.tcl -log system.log {parameters} -testplusarg "OUTPUT_DIR={out.as_posix()}/results"\nexit /b %errorlevel%\n')
    protected = {p.name: SHA(p) for p in out.iterdir() if p.is_file() and (p.suffix in ('.hex', '.dat') or p.name in ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt'))}
    manifest = dict(config=CONFIG, reference=BASE.as_posix(), phase4e_reference=E.as_posix(),
                    substitutions=prior['substitutions'], original_source_manifest=frozen,
                    protected_copies=protected, generated_tb_sha256=SHA(out / 'system_tb.sv'),
                    buffer_map=dict(enumerate(('A_low', 'A_full', 'enhanced', 'cnn_input', 'model_input'))),
                    scheduler='original ping-pong; original full raw/guard/access/IRQ checks; passive observers only',
                    repeated_input='same real night_01 frame in both preloaded input slots; no simulated host transfer',
                    observer_phase='owners/waits sampled negedge after original posedge events; DDR snapshots at active-mask transitions; own CSR reservation excluded from buffer wait',
                    mask='bit0=CNN bit1=Bilinear bit2=Curve, actual internal ap_start/ap_done monitoring',
                    scope='exactly eight complete frames; no HLS, implementation, optimization or Git writes')
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(dict(prepared=out.as_posix(), config=CONFIG, source_files=len(frozen['source_files']), protected_copies=len(protected))))


if __name__ == '__main__':
    main()
