"""Prepare a separate single-CNN XSIM system gate using a three-file RTL overlay.

Preparation does not launch simulation. The frozen DDR, PL wrapper, oracle and
all non-writer source files are hash checked and preserved.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path('E:/HLS/kv260_three_module_v1_2_phase4')
BASE = ROOT / 'phase4b_build_02'
TOP = 'dut.zero_dce_cnn_top_0.inst'
GROUP = TOP + '.grp_p_anonymous_namespace_group_rowstream_block_fu_420'
WRITER = GROUP + '.p_anonymous_namespace_output_writer_U0'
OVERLAY_NAMES = ('zero_dce_cnn_top_row_axi_writer.v',
                 'zero_dce_cnn_top_row_axi_writer_2.v',
                 'zero_dce_cnn_top_p_anonymous_namespace_output_writer.v')
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def observer():
    funcs = [('group_block', GROUP), ('output_writer', WRITER),
             ('row_workspace', WRITER + '.grp_row_axi_writer_fu_171'),
             ('row_output', WRITER + '.grp_row_axi_writer_2_fu_181'),
             ('source_reader', GROUP + '.p_anonymous_namespace_source_reader_U0'),
             ('depth_actor', GROUP + '.p_anonymous_namespace_depth_band_actor_U0'),
             ('point_compute', GROUP + '.p_anonymous_namespace_point_tile_compute_actor_U0'),
             ('output_assembler', GROUP + '.p_anonymous_namespace_output_assembler_U0'),
             ('output_packer', GROUP + '.p_anonymous_namespace_output_packer_U0')]
    buses = [('workspace', TOP + '.m_axi_gmem_workspace_', 32),
             ('output', TOP + '.m_axi_gmem_output_', 32),
             ('hp0', 'hp0_', 128),
             ('logical_workspace', WRITER + '.grp_row_axi_writer_fu_171.m_axi_gmem_workspace_0_', 16),
             ('logical_output', WRITER + '.grp_row_axi_writer_2_fu_181.m_axi_gmem_output_0_', 16)]
    o = ['\n  // PHASE4E: passive protocol/credit monitor; original CNN BFM/oracle retained.',
         f'  localparam integer EB={len(buses)}, EF={len(funcs)};',
         '  integer e_busfile,e_funfile,e_drainfile,e_statsfile,e_creditfile;',
         '  string e_dir; integer e_block=-1,e_group_drains=0,e_writer_drains=0;',
         '  wire [EB-1:0] e_av,e_ar,e_wv,e_wr,e_wl,e_bv,e_br;',
         '  wire [63:0] e_addr[0:EB-1]; wire [31:0] e_len[0:EB-1];',
         '  wire [2:0] e_size[0:EB-1]; wire [1:0] e_burst[0:EB-1],e_resp[0:EB-1];',
         '  wire [15:0] e_strb[0:EB-1]; wire [EF-1:0] e_start,e_done;',
         '  reg [EF-1:0] e_prev_start=0,e_prev_done=0;',
         '  longint e_aw[0:EB-1],e_wlast[0:EB-1],e_b[0:EB-1],e_w[0:EB-1];',
         '  longint e_wstall[0:EB-1],e_awstall[0:EB-1],e_btail[0:EB-1];',
         '  integer e_beats[0:EB-1][0:7],e_head[0:EB-1],e_tail[0:EB-1],e_beat[0:EB-1],e_pending[0:EB-1],e_max[0:EB-1];',
         '  wire [1:0] e_credit[0:1]; wire [1:0] e_credit_wait;',
         '  integer e_prev_credit[0:1],e_credit_max[0:1];',
         '  longint e_credit_full[0:1],e_credit_barrier[0:1],e_terminal_drain=0;',
         f'  wire e_terminal_wait={WRITER}.ap_CS_fsm_state6 && {WRITER}.icmp_ln245_fu_214_p2 && !{WRITER}.all_write_credits_empty;',
         '  task e_snapshot;',
         '    begin for(integer q=0;q<EB;q=q+1) $fdisplay(e_statsfile,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cycle,q,e_aw[q],e_wlast[q],e_b[q],e_w[q],e_pending[q],e_max[q],e_awstall[q],e_wstall[q],e_btail[q]);',
         '      $fflush(e_statsfile);$fflush(e_funfile);$fflush(e_busfile);$fflush(e_creditfile);$fflush(e_drainfile); end',
         '  endtask',
         '  task e_assert_drained(input integer event_kind);',
         '    begin',
         '      if(e_credit[0]!==0 || e_credit[1]!==0) $fatal(1,"PHASE4E block retained logical row credit");',
         '      for(integer q=0;q<EB;q=q+1) if(e_aw[q]!=e_wlast[q] || e_aw[q]!=e_b[q] || e_pending[q]!=0) $fatal(1,"PHASE4E AW/W/B not drained bus=%0d",q);',
         '      if(ddr.wc[0]!=0 || ddr.wp[0]!=0 || ddr.bvalid[0]) $fatal(1,"PHASE4E HP0 DDR not drained");',
         '      $fdisplay(e_drainfile,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cycle,e_block,event_kind,e_credit[0],e_credit[1],e_aw[0],e_wlast[0],e_b[0],e_aw[1],e_wlast[1],e_b[1],ddr.wc[0]);',
         '      $fflush(e_drainfile);',
         '    end',
         '  endtask',
         '  task phase4e_finish;',
         '    begin',
         '      if(frames!=1 || completed[0]!=1 || completed[1]!=0 || completed[2]!=0) $fatal(1,"PHASE4E scope error");',
         '      e_assert_drained(2);e_snapshot();ddr.print_stats();',
         '      if(e_group_drains!=7 || e_writer_drains!=7) $fatal(1,"PHASE4E missing seven block drains");',
         '      if(mismatch_total || guard_errors || hazard_errors) $fatal(1,"PHASE4E CNN numerical/guard/hazard failure");',
         '      $display("PHASE4E_CNN_FINAL FRAMES=1 RAW_MISMATCHES=%0d GUARD_ERRORS=%0d HAZARD_ERRORS=%0d SCALARS=19080 GROUP_DRAINS=%0d WRITER_DRAINS=%0d CREDIT_MAX_WS=%0d CREDIT_MAX_OUT=%0d CREDIT_FINAL_WS=%0d CREDIT_FINAL_OUT=%0d CREDIT_FULL_WS=%0d CREDIT_FULL_OUT=%0d CREDIT_BARRIER_WS=%0d CREDIT_BARRIER_OUT=%0d TERMINAL_DRAIN_WAIT=%0d",mismatch_total,guard_errors,hazard_errors,e_group_drains,e_writer_drains,e_credit_max[0],e_credit_max[1],e_credit[0],e_credit[1],e_credit_full[0],e_credit_full[1],e_credit_barrier[0],e_credit_barrier[1],e_terminal_drain);',
         '      if(stage_done[0][0]-stage_start[0][0]<=3333333) $display("CNN_SYSTEM_STAGE_30FPS_PASS"); else $display("CNN_SYSTEM_STAGE_30FPS_FAIL");',
         '      $display("FULL_CNN_NUMERICAL_PASS");',
         '      $fclose(e_busfile);$fclose(e_funfile);$fclose(e_statsfile);$fclose(e_drainfile);$fclose(e_creditfile);$fclose(event_file);$fclose(progress_file);$finish;',
         '    end',
         '  endtask']
    for i, (_, p, width) in enumerate(buses):
        for k, sig in [('av','AWVALID'),('ar','AWREADY'),('wv','WVALID'),('wr','WREADY'),('wl','WLAST'),('bv','BVALID'),('br','BREADY'),('addr','AWADDR'),('len','AWLEN'),('size','AWSIZE'),('burst','AWBURST'),('resp','BRESP')]:
            value = f'(e_beat[{i}]==105)' if i >= 3 and k == 'wl' else p + sig
            o.append(f'  assign e_{k}[{i}]={value};')
        o.append(f'  assign e_strb[{i}]={p}WSTRB;')
    for i, (_, p) in enumerate(funcs):
        o.append(f'  assign e_start[{i}]={p}.ap_start; assign e_done[{i}]={p}.ap_done;')
    for i, (_, p) in enumerate(funcs[2:4]):
        o.append(f'  assign e_credit[{i}]={p}.credit_count;')
        o.append(f'  assign e_credit_wait[{i}]={p}.ap_CS_fsm_state2 && e_credit[{i}]==2;')
    o += ['  initial begin',
          '    if(!$value$plusargs("OUTPUT_DIR=%s",e_dir)) e_dir=".";',
          '    e_busfile=$fopen({e_dir,"/write_events.csv"},"w");$fdisplay(e_busfile,"cycle,bus,event,addr,len,size,block");',
          '    e_funfile=$fopen({e_dir,"/function_events.csv"},"w");$fdisplay(e_funfile,"cycle,function,event,block");',
          '    e_statsfile=$fopen({e_dir,"/write_stats.csv"},"w");$fdisplay(e_statsfile,"cycle,bus,aw,wlast,b,w,pending,max_pending,aw_stall,w_stall,b_after_wlast_wait");',
          '    e_drainfile=$fopen({e_dir,"/block_drains.csv"},"w");$fdisplay(e_drainfile,"cycle,block,event,credit_ws,credit_out,ws_aw,ws_wlast,ws_b,out_aw,out_wlast,out_b,ddr_wc");',
          '    e_creditfile=$fopen({e_dir,"/credit_events.csv"},"w");$fdisplay(e_creditfile,"cycle,helper,credit,block");',
          '    for(integer q=0;q<EB;q=q+1) begin e_aw[q]=0;e_wlast[q]=0;e_b[q]=0;e_w[q]=0;e_head[q]=0;e_tail[q]=0;e_beat[q]=0;e_pending[q]=0;e_max[q]=0;e_awstall[q]=0;e_wstall[q]=0;e_btail[q]=0;end',
          '    for(integer q=0;q<2;q=q+1) begin e_prev_credit[q]=0;e_credit_max[q]=0;e_credit_full[q]=0;e_credit_barrier[q]=0;end',
          '  end',
          '  always @(posedge ap_clk) if(ap_rst_n) begin',
          '    if(e_terminal_wait) e_terminal_drain=e_terminal_drain+1;',
          '    if(e_start[0] && !e_prev_start[0]) begin e_assert_drained(3);e_block=e_block+1;end',
          '    for(integer q=0;q<EF;q=q+1) begin',
          '      if(e_start[q] && !e_prev_start[q]) $fdisplay(e_funfile,"%0d,%0d,START,%0d",cycle,q,e_block);',
          '      if(e_done[q] && !e_prev_done[q]) $fdisplay(e_funfile,"%0d,%0d,DONE,%0d",cycle,q,e_block);',
          '    end',
          '    for(integer q=0;q<2;q=q+1) begin',
          '      if(e_credit[q]>2) $fatal(1,"PHASE4E logical row credit above two");',
          '      if(e_credit[q]>e_credit_max[q]) e_credit_max[q]=e_credit[q];',
          '      if(e_credit[q]==2) e_credit_full[q]=e_credit_full[q]+1;',
          '      if(e_credit_wait[q]) e_credit_barrier[q]=e_credit_barrier[q]+1;',
          '      if(e_credit[q]!=e_prev_credit[q]) begin $fdisplay(e_creditfile,"%0d,%0d,%0d,%0d",cycle,q,e_credit[q],e_block);e_prev_credit[q]=e_credit[q];end',
          '      if(e_pending[q+3]!=e_credit[q]) $fatal(1,"PHASE4E logical credit accounting mismatch");',
          '    end',
          '    for(integer q=0;q<EB;q=q+1) begin',
          '      if(e_av[q] && !e_ar[q]) e_awstall[q]=e_awstall[q]+1;',
          '      if(e_wv[q] && !e_wr[q]) e_wstall[q]=e_wstall[q]+1;',
          '      if(e_wlast[q]>e_b[q] && !e_bv[q]) e_btail[q]=e_btail[q]+1;',
          '      if(e_av[q] && e_ar[q]) begin',
          '        if(q<3 && ((e_addr[q]&~((64\'d1<<e_size[q])-1)&4095)+(e_len[q]+1)*(1<<e_size[q])>4096 || e_burst[q]!=1)) $fatal(1,"PHASE4E source burst cross 4KB/non-INCR");',
          '        if(q<2 && e_size[q]!=2) $fatal(1,"PHASE4E CNN source write size changed");',
          '        if(q>=3 && e_len[q]!=106) $fatal(1,"PHASE4E logical row layout changed");',
          '        if(e_aw[q]-e_wlast[q]>=8) $fatal(1,"PHASE4E monitor AW queue overflow");',
          '        e_beats[q][e_tail[q]]=q>=3?e_len[q]:e_len[q]+1;e_tail[q]=(e_tail[q]+1)%8;',
          '        e_aw[q]=e_aw[q]+1;e_pending[q]=e_pending[q]+1;',
          '        $fdisplay(e_busfile,"%0d,%0d,AW,%0h,%0d,%0d,%0d",cycle,q,e_addr[q],e_len[q],e_size[q],e_block);',
          '      end',
          '      if(e_wv[q] && e_wr[q]) begin',
          '        if(e_aw[q]<=e_wlast[q]) $fatal(1,"PHASE4E W without AW");',
          '        if(q<2 && e_strb[q]!=15 || q>=3 && e_strb[q]!=3) $fatal(1,"PHASE4E source WSTRB changed");',
          '        if(e_wl[q] !== (e_beat[q]==e_beats[q][e_head[q]]-1)) $fatal(1,"PHASE4E WLAST incorrect");',
          '        if(e_beat[q]==0) $fdisplay(e_busfile,"%0d,%0d,WFIRST,0,0,0,%0d",cycle,q,e_block);',
          '        e_w[q]=e_w[q]+1;e_beat[q]=e_beat[q]+1;',
          '        if(e_wl[q]) begin e_wlast[q]=e_wlast[q]+1;e_beat[q]=0;e_head[q]=(e_head[q]+1)%8;if(q>=3) $fdisplay(e_busfile,"%0d,%0d,ROW_DATA_END,0,0,0,%0d",cycle,q,e_block);else $fdisplay(e_busfile,"%0d,%0d,WLAST,0,0,0,%0d",cycle,q,e_block);end',
          '      end',
          '      if(e_bv[q] && e_br[q]) begin',
          '        if(e_b[q]>=e_wlast[q] || e_resp[q]!=0) $fatal(1,"PHASE4E bad/unmatched B");',
          '        e_b[q]=e_b[q]+1;e_pending[q]=e_pending[q]-1;$fdisplay(e_busfile,"%0d,%0d,B,0,0,0,%0d",cycle,q,e_block);',
          '      end',
          '      if(e_pending[q]>e_max[q]) e_max[q]=e_pending[q];',
          '      if(q==2 && e_pending[q]>2 || q>=3 && e_pending[q]>2 || e_pending[q]<0) $fatal(1,"PHASE4E write queue occupancy violation");',
          '    end',
          '    if(e_done[1] && !e_prev_done[1] && e_block>=0) begin e_assert_drained(0);e_writer_drains=e_writer_drains+1;end',
          '    if(e_done[0] && !e_prev_done[0] && e_block>=0) begin e_assert_drained(1);e_group_drains=e_group_drains+1;end',
          '    e_prev_start=e_start;e_prev_done=e_done;',
          '    if(cycle%50000==0) begin e_snapshot();$display("PHASE4E_PROGRESS CYCLE=%0d BLOCK=%0d",cycle,e_block);end',
          '  end\n']
    return '\n'.join(o), dict(enumerate(n for n, _, _ in buses)), dict(enumerate(n for n, _ in funcs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--name', default='phase4e_system_01')
    args = parser.parse_args()
    assert args.name.replace('_', '').isalnum()
    out = ROOT / args.name
    assert not out.exists(), out
    frozen = json.loads((BASE / 'source_manifest.json').read_text())
    for item in frozen['source_files']:
        assert SHA(Path(item['path'])) == item['sha256'], item['path']
    assert SHA(BASE / 'shared_axi_ddr.sv') == frozen['ddr_model_sha256']
    assert SHA(BASE / 'phase4_pl.v') == frozen['pl_wrapper_sha256']
    assert SHA(BASE / 'system_tb.sv') == frozen['generated_tb_sha256']
    assert SHA(BASE / 'shared_ddr.hex') == '5e675d404a1d5ceaea5088ba87e4197a134cbb851a8d2c45312dc13427579f0c'
    overlay = {}
    for name in OVERLAY_NAMES:
        matches = [p for p in args.overlay.glob('*.v') if p.name == name or p.name == name.replace('zero_dce_cnn_top_', '')]
        assert len(matches) == 1, (name, matches)
        overlay[name] = matches[0].resolve()
    out.mkdir()
    (out / 'results').mkdir()
    for p in BASE.iterdir():
        if p.is_file() and (p.suffix in ('.hex', '.dat') or p.name in ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt')):
            shutil.copy2(p, out / p.name)
    project = (BASE / 'system.prj').read_text().replace(BASE.as_posix(), out.as_posix())
    substitutions = []
    for name, new in overlay.items():
        matches = [item for item in frozen['source_files'] if Path(item['path']).name == name]
        assert len(matches) == 1
        old = matches[0]['path']
        assert project.count('"' + old + '"') == 1
        project = project.replace('"' + old + '"', '"' + new.as_posix() + '"')
        substitutions.append(dict(original=old, original_sha256=matches[0]['sha256'], candidate=new.as_posix(), candidate_sha256=SHA(new)))
    (out / 'system.prj').write_text(project)
    tb = (BASE / 'system_tb.sv').read_text()
    anchor = '            if(m==0) input_owner[slot]=-1;'
    assert tb.count(anchor) == 1 and tb.endswith('endmodule\n')
    tb = tb.replace(anchor, anchor + '\n            if(m==0) phase4e_finish();')
    append, busmap, funcmap = observer()
    (out / 'observer_append.sv').write_text(append)
    (out / 'system_tb.sv').write_text(tb[:-len('endmodule\n')] + append + 'endmodule\n')
    (out / 'run.tcl').write_text('run all\nquit\n')
    cmd = ('@echo off\nset "PROCESSOR_ARCHITECTURE=AMD64"\n'
           'call "E:\\Xilinx\\2025.2\\Vivado\\settings64.bat"\n'
           f'cd /d "{out}"\n'
           'call xelab --relax --mt 2 -prj system.prj -f xelab_options.txt xil_defaultlib.phase4_system_tb xil_defaultlib.glbl -s phase4e_system -log elaborate.log\n'
           'if errorlevel 1 exit /b %errorlevel%\n'
           'if not exist xsim.dir\\phase4e_system\\xsimk.exe exit /b 99\n'
           f'call xsim phase4e_system -tclbatch run.tcl -log system.log -testplusarg "FRAMES=1" -testplusarg "OUTPUT_DIR={out.as_posix()}/results" '
           '-testplusarg "READ_OUTSTANDING=2" -testplusarg "WRITE_OUTSTANDING=2" -testplusarg "DDR_DELAY=16" -testplusarg "SERVICE_PERIOD=1" -testplusarg "POLL_PERIOD=128"\nexit /b %errorlevel%\n')
    (out / 'run.cmd').write_text(cmd)
    before, after = cmd.split('call xsim phase4e_system', 1)
    (out / 'elaborate.cmd').write_text(before + 'exit /b %errorlevel%\n')
    (out / 'simulate.cmd').write_text(before.split('call xelab', 1)[0] + 'call xsim phase4e_system' + after)
    protected = {p.name: SHA(p) for p in out.iterdir() if p.is_file() and (p.suffix in ('.hex', '.dat') or p.name in ('phase4_pl.v', 'shared_axi_ddr.sv', 'xelab_options.txt'))}
    manifest = dict(status='PREPARED_NOT_RUN', config=dict(FRAMES=1, READ_OUTSTANDING=2, WRITE_OUTSTANDING=2, DDR_DELAY=16, SERVICE_PERIOD=1, POLL_PERIOD=128),
                    reference=BASE.as_posix(), substitutions=substitutions, original_source_manifest=frozen,
                    protected_copies=protected, bus_map=busmap, function_map=funcmap,
                    original_tb_sha256=SHA(BASE / 'system_tb.sv'), generated_tb_sha256=SHA(out / 'system_tb.sv'),
                    scope='CNN only; original BFM numerical/guard/hazard/IRQ check then finish. No Bilinear/Curve launch.',
                    logical_interface_note='HLS requests use scalar counts; AWSIZE/WLAST metadata unused. Logical ROW_DATA_END is synthesized by counting exactly 106 accepted INT16 W values. Physical bus WLAST is observed directly.',
                    source_scope='Only the three writer RTL files differ; no HLS, DDR, BD or adapter changes.')
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(dict(prepared=out.as_posix(), replaced_files=len(substitutions), frozen_sources_checked=len(frozen['source_files']), protected_copies=len(protected))))


if __name__ == '__main__':
    main()
