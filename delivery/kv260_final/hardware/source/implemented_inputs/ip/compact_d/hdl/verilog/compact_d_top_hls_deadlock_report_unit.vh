   
    parameter PROC_NUM = 26;
    parameter ST_IDLE = 3'b000;
    parameter ST_FILTER_FAKE = 3'b001;
    parameter ST_DL_DETECTED = 3'b010;
    parameter ST_DL_REPORT = 3'b100;
   

    reg [2:0] CS_fsm;
    reg [2:0] NS_fsm;
    reg [PROC_NUM - 1:0] dl_detect_reg;
    reg [PROC_NUM - 1:0] dl_done_reg;
    reg [PROC_NUM - 1:0] origin_reg;
    reg [PROC_NUM - 1:0] dl_in_vec_reg;
    reg [31:0] dl_keep_cnt;
    reg stop_report_path;
    reg [PROC_NUM - 1:0] reported_proc;
    integer i;
    integer fp;

    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            reported_proc <= 'b0;
        end
        else if (CS_fsm == ST_DL_REPORT) begin
            reported_proc <= reported_proc | dl_in_vec;
        end
        else if (CS_fsm == ST_DL_DETECTED) begin
            reported_proc <= 'b0;
        end
    end

    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            stop_report_path <= 1'b0;
        end
        else if (CS_fsm == ST_DL_REPORT && (|(dl_in_vec & reported_proc))) begin
            stop_report_path <= 1'b1;
        end
        else if (CS_fsm == ST_IDLE) begin
            stop_report_path <= 1'b0;
        end
    end

    // FSM State machine
    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            CS_fsm <= ST_IDLE;
        end
        else begin
            CS_fsm <= NS_fsm;
        end
    end

    always @ (CS_fsm or dl_in_vec or dl_detect_reg or dl_done_reg or dl_in_vec or origin_reg or dl_keep_cnt) begin
        case (CS_fsm)
            ST_IDLE : begin
                if (|dl_in_vec) begin
                    NS_fsm = ST_FILTER_FAKE;
                end
                else begin
                    NS_fsm = ST_IDLE;
                end
            end
            ST_FILTER_FAKE: begin
                if (dl_keep_cnt >= 32'd1000) begin
                    NS_fsm = ST_DL_DETECTED;
                end
                else if (dl_detect_reg != (dl_detect_reg & dl_in_vec)) begin
                    NS_fsm = ST_IDLE;
                end
                else begin
                    NS_fsm = ST_FILTER_FAKE;
                end
            end
            ST_DL_DETECTED: begin
                // has unreported deadlock cycle
                if ((dl_detect_reg != dl_done_reg) && stop_report_path == 1'b0) begin
                    NS_fsm = ST_DL_REPORT;
                end
                else begin
                    NS_fsm = ST_DL_DETECTED;
                end
            end
            ST_DL_REPORT: begin
                if (|(dl_in_vec & origin_reg)) begin
                    NS_fsm = ST_DL_DETECTED;
                end
                // avoid report deadlock ring.
                else if (|(dl_in_vec & reported_proc)) begin
                    NS_fsm = ST_DL_DETECTED;
                end
                else begin
                    NS_fsm = ST_DL_REPORT;
                end
            end
            default: NS_fsm = ST_IDLE;
        endcase
    end

    // dl_detect_reg record the procs that first detect deadlock
    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            dl_detect_reg <= 'b0;
        end
        else begin
            if (CS_fsm == ST_IDLE) begin
                dl_detect_reg <= dl_in_vec;
            end
        end
    end

    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            dl_keep_cnt <= 32'h0;
        end
        else begin
            if (CS_fsm == ST_FILTER_FAKE && (dl_detect_reg == (dl_detect_reg & dl_in_vec))) begin
                dl_keep_cnt <= dl_keep_cnt + 32'h1;
            end
            else if (CS_fsm == ST_FILTER_FAKE && (dl_detect_reg != (dl_detect_reg & dl_in_vec))) begin
                dl_keep_cnt <= 32'h0;
            end
        end
    end

    // dl_detect_out keeps in high after deadlock detected
    assign dl_detect_out = (|dl_detect_reg) && (CS_fsm == ST_DL_DETECTED || CS_fsm == ST_DL_REPORT);

    // dl_done_reg record the cycles has been reported
    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            dl_done_reg <= 'b0;
        end
        else begin
            if ((CS_fsm == ST_DL_REPORT) && (|(dl_in_vec & dl_detect_reg) == 'b1)) begin
                dl_done_reg <= dl_done_reg | dl_in_vec;
            end
        end
    end

    // clear token once a cycle is done
    assign token_clear = (CS_fsm == ST_DL_REPORT) ? ((|(dl_in_vec & origin_reg)) ? 'b1 : 'b0) : 'b0;

    // origin_reg record the current cycle start id
    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            origin_reg <= 'b0;
        end
        else begin
            if (CS_fsm == ST_DL_DETECTED) begin
                origin_reg <= origin;
            end
        end
    end
   
    // origin will be valid for only one cycle
    wire [PROC_NUM*PROC_NUM - 1:0] origin_tmp;
    assign origin_tmp[PROC_NUM - 1:0] = (dl_detect_reg[0] & ~dl_done_reg[0]) ? 'b1 : 'b0;
    genvar j;
    generate
    for(j = 1;j < PROC_NUM;j = j + 1) begin: F1
        assign origin_tmp[j*PROC_NUM +: PROC_NUM] = (dl_detect_reg[j] & ~dl_done_reg[j]) ? ('b1 << j) : origin_tmp[(j - 1)*PROC_NUM +: PROC_NUM];
    end
    endgenerate
    always @ (CS_fsm or origin_tmp) begin
        if (CS_fsm == ST_DL_DETECTED) begin
            origin = origin_tmp[(PROC_NUM - 1)*PROC_NUM +: PROC_NUM];
        end
        else begin
            origin = 'b0;
        end
    end

    
    // dl_in_vec_reg record the current cycle dl_in_vec
    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            dl_in_vec_reg <= 'b0;
        end
        else begin
            if (CS_fsm == ST_DL_DETECTED) begin
                dl_in_vec_reg <= origin;
            end
            else if (CS_fsm == ST_DL_REPORT) begin
                dl_in_vec_reg <= dl_in_vec;
            end
        end
    end
    
    // find_df_deadlock to report the deadlock
    always @ (negedge dl_reset or posedge dl_clock) begin
        if (~dl_reset) begin
            find_df_deadlock <= 1'b0;
        end
        else begin
            if (CS_fsm == ST_DL_DETECTED && ((dl_detect_reg == dl_done_reg) || (stop_report_path == 1'b1))) begin
                find_df_deadlock <= 1'b1;
            end
            else if (CS_fsm == ST_IDLE) begin
                find_df_deadlock <= 1'b0;
            end
        end
    end
    
    // get the first valid proc index in dl vector
    function integer proc_index(input [PROC_NUM - 1:0] dl_vec);
        begin
            proc_index = 0;
            for (i = 0; i < PROC_NUM; i = i + 1) begin
                if (dl_vec[i]) begin
                    proc_index = i;
                end
            end
        end
    endfunction

    // get the proc path based on dl vector
    function [720:0] proc_path(input [PROC_NUM - 1:0] dl_vec);
        integer index;
        begin
            index = proc_index(dl_vec);
            case (index)
                0 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0";
                end
                1 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0";
                end
                2 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0";
                end
                3 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0";
                end
                4 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0";
                end
                5 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0";
                end
                6 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0";
                end
                7 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0";
                end
                8 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0";
                end
                9 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0";
                end
                10 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0";
                end
                11 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0";
                end
                12 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0";
                end
                13 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0";
                end
                14 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0";
                end
                15 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0";
                end
                16 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0";
                end
                17 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0";
                end
                18 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0";
                end
                19 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0";
                end
                20 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0";
                end
                21 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0";
                end
                22 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0";
                end
                23 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0";
                end
                24 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0";
                end
                25 : begin
                    proc_path = "compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0";
                end
                default : begin
                    proc_path = "unknown";
                end
            endcase
        end
    endfunction

    // print the headlines of deadlock detection
    task print_dl_head;
        begin
            $display("\n//////////////////////////////////////////////////////////////////////////////");
            $display("// ERROR!!! DEADLOCK DETECTED at %0t ns! SIMULATION WILL BE STOPPED! //", $time);
            $display("//////////////////////////////////////////////////////////////////////////////");
            fp = $fopen("deadlock_db.dat", "w");
        end
    endtask

    // print the start of a cycle
    task print_cycle_start(input reg [720:0] proc_path, input integer cycle_id);
        begin
            $display("/////////////////////////");
            $display("// Dependence cycle %0d:", cycle_id);
            $display("// (1): Process: %0s", proc_path);
            $fdisplay(fp, "Dependence_Cycle_ID %0d", cycle_id);
            $fdisplay(fp, "Dependence_Process_ID 1");
            $fdisplay(fp, "Dependence_Process_path %0s", proc_path);
        end
    endtask

    // print the end of deadlock detection
    task print_dl_end(input integer num, input integer record_time);
        begin
            $display("////////////////////////////////////////////////////////////////////////");
            $display("// Totally %0d cycles detected!", num);
            $display("////////////////////////////////////////////////////////////////////////");
            $display("// ERROR!!! DEADLOCK DETECTED at %0t ns! SIMULATION WILL BE STOPPED! //", record_time);
            $display("//////////////////////////////////////////////////////////////////////////////");
            $fdisplay(fp, "Dependence_Cycle_Number %0d", num);
            $fclose(fp);
        end
    endtask

    // print one proc component in the cycle
    task print_cycle_proc_comp(input reg [720:0] proc_path, input integer cycle_comp_id);
        begin
            $display("// (%0d): Process: %0s", cycle_comp_id, proc_path);
            $fdisplay(fp, "Dependence_Process_ID %0d", cycle_comp_id);
            $fdisplay(fp, "Dependence_Process_path %0s", proc_path);
        end
    endtask

    // print one channel component in the cycle
    task print_cycle_chan_comp(input [PROC_NUM - 1:0] dl_vec1, input [PROC_NUM - 1:0] dl_vec2);
        reg [816:0] chan_path;
        integer index1;
        integer index2;
        begin
            index1 = proc_index(dl_vec1);
            index2 = proc_index(dl_vec2);
            case (index1)
                0 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'
                    case(index2)
                    1: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ir_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.grp_read_plane_fu_100.grp_read_plane_Pipeline_READ_PLANE_fu_86.ir_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.read_nchw_U0.grp_read_plane_fu_100.grp_read_plane_Pipeline_READ_PLANE_fu_86.ir_blk_n)) begin
                            if (~grp_frame_fu_190.ir_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ir_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ir_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ir_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ir_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ir_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ig_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.grp_read_plane_fu_100.grp_read_plane_Pipeline_READ_PLANE_fu_86.ir_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.read_nchw_U0.grp_read_plane_fu_100.grp_read_plane_Pipeline_READ_PLANE_fu_86.ir_blk_n)) begin
                            if (~grp_frame_fu_190.ig_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ig_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ig_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ig_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ig_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ig_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ib_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.grp_read_plane_fu_100.grp_read_plane_Pipeline_READ_PLANE_fu_86.ir_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.read_nchw_U0.grp_read_plane_fu_100.grp_read_plane_Pipeline_READ_PLANE_fu_86.ir_blk_n)) begin
                            if (~grp_frame_fu_190.ib_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ib_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ib_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ib_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ib_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ib_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_pack_input_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_pack_input_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.real_start & (trans_in_cnt_0 == trans_out_cnt_0) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_pack_input_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_pack_input_U0_U.if_full_n & grp_frame_fu_190.read_nchw_U0.ap_start & ~grp_frame_fu_190.read_nchw_U0.real_start & (trans_in_cnt_0 == trans_out_cnt_0) & ~grp_frame_fu_190.start_for_pack_input_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_pack_input_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0',");
                        end
                    end
                    25: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.read_done_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.read_done_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.read_nchw_U0.read_done_blk_n)) begin
                            if (~grp_frame_fu_190.read_done_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.read_done_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.read_done_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.read_done_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.read_done_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.read_done_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_monitor_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_monitor_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.read_nchw_U0.real_start & (trans_in_cnt_0 == trans_out_cnt_0) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_monitor_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_monitor_U0_U.if_full_n & grp_frame_fu_190.read_nchw_U0.ap_start & ~grp_frame_fu_190.read_nchw_U0.real_start & (trans_in_cnt_0 == trans_out_cnt_0) & ~grp_frame_fu_190.start_for_monitor_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_monitor_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0',");
                        end
                    end
                    endcase
                end
                1 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'
                    case(index2)
                    0: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ir_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.ir_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.ir_blk_n)) begin
                            if (~grp_frame_fu_190.ir_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ir_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ir_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ir_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ir_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ir_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ig_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.ig_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.ig_blk_n)) begin
                            if (~grp_frame_fu_190.ig_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ig_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ig_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ig_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ig_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ig_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ib_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.ib_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.ib_blk_n)) begin
                            if (~grp_frame_fu_190.ib_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ib_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ib_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ib_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ib_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ib_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_pack_input_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_pack_input_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_pack_input_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_pack_input_U0_U.if_empty_n & grp_frame_fu_190.pack_input_U0.ap_idle & ~grp_frame_fu_190.start_for_pack_input_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_pack_input_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0',");
                        end
                    end
                    2: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.rgb_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.rgb_blk_n)) begin
                            if (~grp_frame_fu_190.rgb_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.rgb_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.real_start & (trans_in_cnt_1 == trans_out_cnt_1) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_full_n & grp_frame_fu_190.pack_input_U0.ap_start & ~grp_frame_fu_190.pack_input_U0.real_start & (trans_in_cnt_1 == trans_out_cnt_1) & ~grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0',");
                        end
                    end
                    23: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.base_r_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.pack_input_U0.grp_pack_input_Pipeline_VITIS_LOOP_83_1_fu_56.base_r_blk_n)) begin
                            if (~grp_frame_fu_190.base_r_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.base_r_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_finish_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_finish_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.pack_input_U0.real_start & (trans_in_cnt_1 == trans_out_cnt_1) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_finish_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_finish_U0_U.if_full_n & grp_frame_fu_190.pack_input_U0.ap_start & ~grp_frame_fu_190.pack_input_U0.real_start & (trans_in_cnt_1 == trans_out_cnt_1) & ~grp_frame_fu_190.start_for_finish_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_finish_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0',");
                        end
                    end
                    endcase
                end
                2 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'
                    case(index2)
                    1: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_0_3_8_U0.grp_convolution_0_3_8_Pipeline_CONV_PHASE_fu_66.rgb_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.convolution_0_3_8_U0.grp_convolution_0_3_8_Pipeline_CONV_PHASE_fu_66.rgb_blk_n)) begin
                            if (~grp_frame_fu_190.rgb_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.rgb_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.rgb_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_0_3_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_empty_n & grp_frame_fu_190.convolution_0_3_8_U0.ap_idle & ~grp_frame_fu_190.start_for_convolution_0_3_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_0_3_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0',");
                        end
                    end
                    3: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.stem_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_0_3_8_U0.grp_convolution_0_3_8_Pipeline_CONV_PHASE_fu_66.stem_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.convolution_0_3_8_U0.grp_convolution_0_3_8_Pipeline_CONV_PHASE_fu_66.stem_blk_n)) begin
                            if (~grp_frame_fu_190.stem_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.stem_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.stem_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.stem_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.stem_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.stem_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_relu_2_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_relu_2_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_0_3_8_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_0_3_8_U0.real_start & (trans_in_cnt_2 == trans_out_cnt_2) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_relu_2_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_relu_2_U0_U.if_full_n & grp_frame_fu_190.convolution_0_3_8_U0.ap_start & ~grp_frame_fu_190.convolution_0_3_8_U0.real_start & (trans_in_cnt_2 == trans_out_cnt_2) & ~grp_frame_fu_190.start_for_relu_2_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_relu_2_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0',");
                        end
                    end
                    endcase
                end
                3 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'
                    case(index2)
                    2: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.stem_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.relu_2_U0.grp_relu_2_Pipeline_VITIS_LOOP_172_1_fu_40.stem_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.relu_2_U0.grp_relu_2_Pipeline_VITIS_LOOP_172_1_fu_40.stem_blk_n)) begin
                            if (~grp_frame_fu_190.stem_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.stem_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.stem_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.stem_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.stem_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.stem_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_relu_2_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_relu_2_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.relu_2_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_relu_2_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_relu_2_U0_U.if_empty_n & grp_frame_fu_190.relu_2_U0.ap_idle & ~grp_frame_fu_190.start_for_relu_2_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_relu_2_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_0_3_8_U0',");
                        end
                    end
                    4: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.relu_2_U0.grp_relu_2_Pipeline_VITIS_LOOP_172_1_fu_40.s0_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.relu_2_U0.grp_relu_2_Pipeline_VITIS_LOOP_172_1_fu_40.s0_blk_n)) begin
                            if (~grp_frame_fu_190.s0_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s0_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_0_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_0_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.relu_2_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.relu_2_U0.real_start & (trans_in_cnt_3 == trans_out_cnt_3) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_0_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_residual_block_0_U0_U.if_full_n & grp_frame_fu_190.relu_2_U0.ap_start & ~grp_frame_fu_190.relu_2_U0.real_start & (trans_in_cnt_3 == trans_out_cnt_3) & ~grp_frame_fu_190.start_for_residual_block_0_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_0_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0',");
                        end
                    end
                    5: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.relu_2_U0.grp_relu_2_Pipeline_VITIS_LOOP_172_1_fu_40.s0_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.relu_2_U0.grp_relu_2_Pipeline_VITIS_LOOP_172_1_fu_40.s0_blk_n)) begin
                            if (~grp_frame_fu_190.s0_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s0_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                4 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'
                    case(index2)
                    3: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.s0_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.fork_0_U0.s0_blk_n)) begin
                            if (~grp_frame_fu_190.s0_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s0_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_0_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_0_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_0_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_residual_block_0_U0_U.if_empty_n & grp_frame_fu_190.residual_block_0_U0.ap_idle & ~grp_frame_fu_190.start_for_residual_block_0_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_0_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0',");
                        end
                    end
                    10: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_1_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_1_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.real_start & (trans_in_cnt_7 == trans_out_cnt_7) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_1_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_residual_block_1_U0_U.if_full_n & grp_frame_fu_190.residual_block_0_U0.ap_start & ~grp_frame_fu_190.residual_block_0_U0.real_start & (trans_in_cnt_7 == trans_out_cnt_7) & ~grp_frame_fu_190.start_for_residual_block_1_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_1_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0',");
                        end
                    end
                    11: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                5 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'
                    case(index2)
                    3: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.s0_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.fork_0_U0.s0_blk_n)) begin
                            if (~grp_frame_fu_190.s0_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s0_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s0_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    6: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.a_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.fork_0_U0.a_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.a_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.a_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.real_start & (trans_in_cnt_4 == trans_out_cnt_4) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_full_n & grp_frame_fu_190.residual_block_0_U0.fork_0_U0.ap_start & ~grp_frame_fu_190.residual_block_0_U0.fork_0_U0.real_start & (trans_in_cnt_4 == trans_out_cnt_4) & ~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0',");
                        end
                    end
                    9: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.skip_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.fork_0_U0.skip_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.skip_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.skip_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.fork_0_U0.real_start & (trans_in_cnt_4 == trans_out_cnt_4) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_full_n & grp_frame_fu_190.residual_block_0_U0.fork_0_U0.ap_start & ~grp_frame_fu_190.residual_block_0_U0.fork_0_U0.real_start & (trans_in_cnt_4 == trans_out_cnt_4) & ~grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0',");
                        end
                    end
                    endcase
                end
                6 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'
                    case(index2)
                    5: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.grp_convolution_1_8_8_Pipeline_CONV_PHASE_fu_68.a_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.grp_convolution_1_8_8_Pipeline_CONV_PHASE_fu_68.a_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.a_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.a_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_empty_n & grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.ap_idle & ~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_1_8_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0',");
                        end
                    end
                    7: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.grp_convolution_1_8_8_Pipeline_CONV_PHASE_fu_68.b_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.grp_convolution_1_8_8_Pipeline_CONV_PHASE_fu_68.b_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.b_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.b_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.real_start & (trans_in_cnt_5 == trans_out_cnt_5) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_full_n & grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.ap_start & ~grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0.real_start & (trans_in_cnt_5 == trans_out_cnt_5) & ~grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0',");
                        end
                    end
                    endcase
                end
                7 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'
                    case(index2)
                    6: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.relu_4_U0.grp_relu_4_Pipeline_VITIS_LOOP_172_1_fu_40.b_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.relu_4_U0.grp_relu_4_Pipeline_VITIS_LOOP_172_1_fu_40.b_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.b_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.b_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.relu_4_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_empty_n & grp_frame_fu_190.residual_block_0_U0.relu_4_U0.ap_idle & ~grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_relu_4_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_1_8_8_U0',");
                        end
                    end
                    8: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.relu_4_U0.grp_relu_4_Pipeline_VITIS_LOOP_172_1_fu_40.c_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.relu_4_U0.grp_relu_4_Pipeline_VITIS_LOOP_172_1_fu_40.c_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.c_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.c_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.relu_4_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.relu_4_U0.real_start & (trans_in_cnt_6 == trans_out_cnt_6) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_full_n & grp_frame_fu_190.residual_block_0_U0.relu_4_U0.ap_start & ~grp_frame_fu_190.residual_block_0_U0.relu_4_U0.real_start & (trans_in_cnt_6 == trans_out_cnt_6) & ~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0',");
                        end
                    end
                    endcase
                end
                8 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'
                    case(index2)
                    7: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0.grp_convolution_2_8_8_Pipeline_CONV_PHASE_fu_68.c_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0.grp_convolution_2_8_8_Pipeline_CONV_PHASE_fu_68.c_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.c_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.c_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_empty_n & grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0.ap_idle & ~grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_convolution_2_8_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.relu_4_U0',");
                        end
                    end
                    9: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0.grp_convolution_2_8_8_Pipeline_CONV_PHASE_fu_68.d_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0.grp_convolution_2_8_8_Pipeline_CONV_PHASE_fu_68.d_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.d_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.d_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                9 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'
                    case(index2)
                    8: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.d_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.d_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.d_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.d_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.convolution_2_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    5: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.skip_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.skip_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_0_U0.skip_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_0_U0.skip_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_empty_n & grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.ap_idle & ~grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.start_for_add_relu_0_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.fork_0_U0',");
                        end
                    end
                    10: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    11: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0.grp_add_relu_0_Pipeline_VITIS_LOOP_194_1_fu_52.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                10 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'
                    case(index2)
                    4: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_1_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_1_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_1_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_residual_block_1_U0_U.if_empty_n & grp_frame_fu_190.residual_block_1_U0.ap_idle & ~grp_frame_fu_190.start_for_residual_block_1_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_1_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0',");
                        end
                    end
                    9: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    16: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_2_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_2_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.real_start & (trans_in_cnt_11 == trans_out_cnt_11) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_2_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_residual_block_2_U0_U.if_full_n & grp_frame_fu_190.residual_block_1_U0.ap_start & ~grp_frame_fu_190.residual_block_1_U0.real_start & (trans_in_cnt_11 == trans_out_cnt_11) & ~grp_frame_fu_190.start_for_residual_block_2_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_2_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0',");
                        end
                    end
                    17: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                11 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'
                    case(index2)
                    4: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    9: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.s1_blk_n)) begin
                            if (~grp_frame_fu_190.s1_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s1_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s1_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_0_U0.add_relu_0_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s1_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    12: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.a_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.a_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.a_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.a_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.real_start & (trans_in_cnt_8 == trans_out_cnt_8) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_full_n & grp_frame_fu_190.residual_block_1_U0.fork_1_U0.ap_start & ~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.real_start & (trans_in_cnt_8 == trans_out_cnt_8) & ~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0',");
                        end
                    end
                    15: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.skip_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.skip_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.skip_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.skip_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.fork_1_U0.real_start & (trans_in_cnt_8 == trans_out_cnt_8) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_full_n & grp_frame_fu_190.residual_block_1_U0.fork_1_U0.ap_start & ~grp_frame_fu_190.residual_block_1_U0.fork_1_U0.real_start & (trans_in_cnt_8 == trans_out_cnt_8) & ~grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0',");
                        end
                    end
                    endcase
                end
                12 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'
                    case(index2)
                    11: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.grp_convolution_3_8_8_Pipeline_CONV_PHASE_fu_68.a_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.grp_convolution_3_8_8_Pipeline_CONV_PHASE_fu_68.a_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.a_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.a_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_empty_n & grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.ap_idle & ~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_3_8_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0',");
                        end
                    end
                    13: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.grp_convolution_3_8_8_Pipeline_CONV_PHASE_fu_68.b_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.grp_convolution_3_8_8_Pipeline_CONV_PHASE_fu_68.b_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.b_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.b_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.real_start & (trans_in_cnt_9 == trans_out_cnt_9) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_full_n & grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.ap_start & ~grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0.real_start & (trans_in_cnt_9 == trans_out_cnt_9) & ~grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0',");
                        end
                    end
                    endcase
                end
                13 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'
                    case(index2)
                    12: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.relu_9_U0.grp_relu_9_Pipeline_VITIS_LOOP_172_1_fu_40.b_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.relu_9_U0.grp_relu_9_Pipeline_VITIS_LOOP_172_1_fu_40.b_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.b_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.b_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.relu_9_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_empty_n & grp_frame_fu_190.residual_block_1_U0.relu_9_U0.ap_idle & ~grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_relu_9_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_3_8_8_U0',");
                        end
                    end
                    14: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.relu_9_U0.grp_relu_9_Pipeline_VITIS_LOOP_172_1_fu_40.c_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.relu_9_U0.grp_relu_9_Pipeline_VITIS_LOOP_172_1_fu_40.c_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.c_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.c_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.relu_9_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.relu_9_U0.real_start & (trans_in_cnt_10 == trans_out_cnt_10) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_full_n & grp_frame_fu_190.residual_block_1_U0.relu_9_U0.ap_start & ~grp_frame_fu_190.residual_block_1_U0.relu_9_U0.real_start & (trans_in_cnt_10 == trans_out_cnt_10) & ~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0',");
                        end
                    end
                    endcase
                end
                14 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'
                    case(index2)
                    13: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0.grp_convolution_4_8_8_Pipeline_CONV_PHASE_fu_68.c_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0.grp_convolution_4_8_8_Pipeline_CONV_PHASE_fu_68.c_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.c_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.c_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_empty_n & grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0.ap_idle & ~grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_convolution_4_8_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.relu_9_U0',");
                        end
                    end
                    15: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0.grp_convolution_4_8_8_Pipeline_CONV_PHASE_fu_68.d_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0.grp_convolution_4_8_8_Pipeline_CONV_PHASE_fu_68.d_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.d_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.d_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                15 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'
                    case(index2)
                    14: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.d_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.d_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.d_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.d_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.convolution_4_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    11: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.skip_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.skip_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_1_U0.skip_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_1_U0.skip_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_empty_n & grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.ap_idle & ~grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.start_for_add_relu_1_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.fork_1_U0',");
                        end
                    end
                    16: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    17: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0.grp_add_relu_1_Pipeline_VITIS_LOOP_194_1_fu_52.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                16 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'
                    case(index2)
                    10: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_2_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_2_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_residual_block_2_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_residual_block_2_U0_U.if_empty_n & grp_frame_fu_190.residual_block_2_U0.ap_idle & ~grp_frame_fu_190.start_for_residual_block_2_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_residual_block_2_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0',");
                        end
                    end
                    15: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    22: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.s3_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.s3_blk_n)) begin
                            if (~grp_frame_fu_190.s3_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s3_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.real_start & (trans_in_cnt_15 == trans_out_cnt_15) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_full_n & grp_frame_fu_190.residual_block_2_U0.ap_start & ~grp_frame_fu_190.residual_block_2_U0.real_start & (trans_in_cnt_15 == trans_out_cnt_15) & ~grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0',");
                        end
                    end
                    endcase
                end
                17 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'
                    case(index2)
                    10: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    15: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.s2_blk_n)) begin
                            if (~grp_frame_fu_190.s2_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s2_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s2_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_1_U0.add_relu_1_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s2_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    18: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.a_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.a_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.a_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.a_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.real_start & (trans_in_cnt_12 == trans_out_cnt_12) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_full_n & grp_frame_fu_190.residual_block_2_U0.fork_2_U0.ap_start & ~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.real_start & (trans_in_cnt_12 == trans_out_cnt_12) & ~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0',");
                        end
                    end
                    21: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.skip_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.skip_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.skip_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.skip_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.fork_2_U0.real_start & (trans_in_cnt_12 == trans_out_cnt_12) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_full_n & grp_frame_fu_190.residual_block_2_U0.fork_2_U0.ap_start & ~grp_frame_fu_190.residual_block_2_U0.fork_2_U0.real_start & (trans_in_cnt_12 == trans_out_cnt_12) & ~grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0',");
                        end
                    end
                    endcase
                end
                18 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'
                    case(index2)
                    17: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.grp_convolution_5_8_8_Pipeline_CONV_PHASE_fu_68.a_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.grp_convolution_5_8_8_Pipeline_CONV_PHASE_fu_68.a_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.a_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.a_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.a_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_empty_n & grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.ap_idle & ~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_5_8_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0',");
                        end
                    end
                    19: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.grp_convolution_5_8_8_Pipeline_CONV_PHASE_fu_68.b_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.grp_convolution_5_8_8_Pipeline_CONV_PHASE_fu_68.b_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.b_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.b_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.real_start & (trans_in_cnt_13 == trans_out_cnt_13) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_full_n & grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.ap_start & ~grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0.real_start & (trans_in_cnt_13 == trans_out_cnt_13) & ~grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0',");
                        end
                    end
                    endcase
                end
                19 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'
                    case(index2)
                    18: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.relu_14_U0.grp_relu_14_Pipeline_VITIS_LOOP_172_1_fu_40.b_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.relu_14_U0.grp_relu_14_Pipeline_VITIS_LOOP_172_1_fu_40.b_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.b_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.b_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.b_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.relu_14_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_empty_n & grp_frame_fu_190.residual_block_2_U0.relu_14_U0.ap_idle & ~grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_relu_14_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_5_8_8_U0',");
                        end
                    end
                    20: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.relu_14_U0.grp_relu_14_Pipeline_VITIS_LOOP_172_1_fu_40.c_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.relu_14_U0.grp_relu_14_Pipeline_VITIS_LOOP_172_1_fu_40.c_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.c_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.c_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.relu_14_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.relu_14_U0.real_start & (trans_in_cnt_14 == trans_out_cnt_14) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_full_n & grp_frame_fu_190.residual_block_2_U0.relu_14_U0.ap_start & ~grp_frame_fu_190.residual_block_2_U0.relu_14_U0.real_start & (trans_in_cnt_14 == trans_out_cnt_14) & ~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0',");
                        end
                    end
                    endcase
                end
                20 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'
                    case(index2)
                    19: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0.grp_convolution_6_8_8_Pipeline_CONV_PHASE_fu_68.c_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0.grp_convolution_6_8_8_Pipeline_CONV_PHASE_fu_68.c_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.c_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.c_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.c_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_empty_n & grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0.ap_idle & ~grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_convolution_6_8_8_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.relu_14_U0',");
                        end
                    end
                    21: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0.grp_convolution_6_8_8_Pipeline_CONV_PHASE_fu_68.d_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0.grp_convolution_6_8_8_Pipeline_CONV_PHASE_fu_68.d_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.d_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.d_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                21 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'
                    case(index2)
                    20: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.d_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.d_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.d_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.d_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.convolution_6_8_8_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.d_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    17: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.skip_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.skip_blk_n)) begin
                            if (~grp_frame_fu_190.residual_block_2_U0.skip_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.residual_block_2_U0.skip_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.skip_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_empty_n & grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.ap_idle & ~grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.start_for_add_relu_2_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.fork_2_U0',");
                        end
                    end
                    22: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.s3_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0.grp_add_relu_2_Pipeline_VITIS_LOOP_194_1_fu_52.s3_blk_n)) begin
                            if (~grp_frame_fu_190.s3_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s3_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                22 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'
                    case(index2)
                    16: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_7_8_3_U0.grp_convolution_7_8_3_Pipeline_CONV_PHASE_fu_68.s3_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.convolution_7_8_3_U0.grp_convolution_7_8_3_Pipeline_CONV_PHASE_fu_68.s3_blk_n)) begin
                            if (~grp_frame_fu_190.s3_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s3_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_7_8_3_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_empty_n & grp_frame_fu_190.convolution_7_8_3_U0.ap_idle & ~grp_frame_fu_190.start_for_convolution_7_8_3_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_convolution_7_8_3_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0',");
                        end
                    end
                    21: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_7_8_3_U0.grp_convolution_7_8_3_Pipeline_CONV_PHASE_fu_68.s3_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.convolution_7_8_3_U0.grp_convolution_7_8_3_Pipeline_CONV_PHASE_fu_68.s3_blk_n)) begin
                            if (~grp_frame_fu_190.s3_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.s3_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.s3_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.residual_block_2_U0.add_relu_2_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.s3_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    23: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.head_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.convolution_7_8_3_U0.grp_convolution_7_8_3_Pipeline_CONV_PHASE_fu_68.head_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.convolution_7_8_3_U0.grp_convolution_7_8_3_Pipeline_CONV_PHASE_fu_68.head_blk_n)) begin
                            if (~grp_frame_fu_190.head_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.head_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.head_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.head_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.head_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.head_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    endcase
                end
                23 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'
                    case(index2)
                    22: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.head_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.head_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.head_blk_n)) begin
                            if (~grp_frame_fu_190.head_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.head_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.head_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.head_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.head_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.convolution_7_8_3_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.head_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
                    end
                    1: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.base_r_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.base_r_blk_n)) begin
                            if (~grp_frame_fu_190.base_r_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.base_r_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.base_r_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_finish_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_finish_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_finish_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_finish_U0_U.if_empty_n & grp_frame_fu_190.finish_U0.ap_idle & ~grp_frame_fu_190.start_for_finish_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_finish_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.pack_input_U0',");
                        end
                    end
                    24: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.orr_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.orr_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.orr_blk_n)) begin
                            if (~grp_frame_fu_190.orr_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.orr_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.orr_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.orr_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.orr_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.orr_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.og_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.og_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.og_blk_n)) begin
                            if (~grp_frame_fu_190.og_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.og_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.og_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.og_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.og_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.og_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ob_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.ob_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.finish_U0.grp_finish_Pipeline_VITIS_LOOP_228_1_fu_56.ob_blk_n)) begin
                            if (~grp_frame_fu_190.ob_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ob_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ob_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ob_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ob_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ob_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_write_nchw_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_write_nchw_U0_U.if_full_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.ap_start & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.finish_U0.real_start & (trans_in_cnt_16 == trans_out_cnt_16) & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_write_nchw_U0_U.if_read} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_write_nchw_U0_U.if_full_n & grp_frame_fu_190.finish_U0.ap_start & ~grp_frame_fu_190.finish_U0.real_start & (trans_in_cnt_16 == trans_out_cnt_16) & ~grp_frame_fu_190.start_for_write_nchw_U0_U.if_read)) begin
                            $display("//      Blocked by full output start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_write_nchw_U0_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0',");
                        end
                    end
                    endcase
                end
                24 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'
                    case(index2)
                    23: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.orr_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.grp_write_plane_fu_100.grp_write_plane_Pipeline_WRITE_PLANE_fu_93.orr_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.write_nchw_U0.grp_write_plane_fu_100.grp_write_plane_Pipeline_WRITE_PLANE_fu_93.orr_blk_n)) begin
                            if (~grp_frame_fu_190.orr_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.orr_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.orr_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.orr_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.orr_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.orr_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.og_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.grp_write_plane_fu_100.grp_write_plane_Pipeline_WRITE_PLANE_fu_93.orr_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.write_nchw_U0.grp_write_plane_fu_100.grp_write_plane_Pipeline_WRITE_PLANE_fu_93.orr_blk_n)) begin
                            if (~grp_frame_fu_190.og_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.og_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.og_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.og_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.og_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.og_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.ob_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.grp_write_plane_fu_100.grp_write_plane_Pipeline_WRITE_PLANE_fu_93.orr_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.write_nchw_U0.grp_write_plane_fu_100.grp_write_plane_Pipeline_WRITE_PLANE_fu_93.orr_blk_n)) begin
                            if (~grp_frame_fu_190.ob_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ob_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ob_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.ob_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.ob_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.ob_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_write_nchw_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_write_nchw_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_write_nchw_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_write_nchw_U0_U.if_empty_n & grp_frame_fu_190.write_nchw_U0.ap_idle & ~grp_frame_fu_190.start_for_write_nchw_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_write_nchw_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.finish_U0',");
                        end
                    end
                    25: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.write_done_U' info is :
// blk sig is {~compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.write_done_blk_n data_FIFO}
                        if ((~grp_frame_fu_190.write_nchw_U0.write_done_blk_n)) begin
                            if (~grp_frame_fu_190.write_done_U.if_empty_n) begin
                                $display("//      Blocked by empty input FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.write_done_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.write_done_U");
                                $fdisplay(fp, "Dependence_Channel_status EMPTY");
                            end
                            else if (~grp_frame_fu_190.write_done_U.if_full_n) begin
                                $display("//      Blocked by full output FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.write_done_U' read by process 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'");
                                $fdisplay(fp, "Dependence_Channel_path compact_d_top_compact_d_top.grp_frame_fu_190.write_done_U");
                                $fdisplay(fp, "Dependence_Channel_status FULL");
                            end
                        end
// for dep channel '' info is :
// blk sig is {{ap_done_reg_3 & compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.ap_done & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.monitor_U0.ap_done} output_sync}
                        if ((ap_done_reg_3 & grp_frame_fu_190.write_nchw_U0.ap_done & ~grp_frame_fu_190.monitor_U0.ap_done)) begin
                            $display("//      Blocked by output sync logic with process : 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'");
                        end
                    end
                    endcase
                end
                25 : begin // for proc 'compact_d_top_compact_d_top.grp_frame_fu_190.monitor_U0'
                    case(index2)
                    24: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'
// for dep channel '' info is :
// blk sig is {{ap_done_reg_4 & compact_d_top_compact_d_top_inst.grp_frame_fu_190.monitor_U0.ap_done & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.write_nchw_U0.ap_done} output_sync}
                        if ((ap_done_reg_4 & grp_frame_fu_190.monitor_U0.ap_done & ~grp_frame_fu_190.write_nchw_U0.ap_done)) begin
                            $display("//      Blocked by output sync logic with process : 'compact_d_top_compact_d_top.grp_frame_fu_190.write_nchw_U0'");
                        end
                    end
                    0: begin //  for dep proc 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0'
// for dep channel 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_monitor_U0_U' info is :
// blk sig is {{~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_monitor_U0_U.if_empty_n & compact_d_top_compact_d_top_inst.grp_frame_fu_190.monitor_U0.ap_idle & ~compact_d_top_compact_d_top_inst.grp_frame_fu_190.start_for_monitor_U0_U.if_write} start_FIFO}
                        if ((~grp_frame_fu_190.start_for_monitor_U0_U.if_empty_n & grp_frame_fu_190.monitor_U0.ap_idle & ~grp_frame_fu_190.start_for_monitor_U0_U.if_write)) begin
                            $display("//      Blocked by missing 'ap_start' from start propagation FIFO 'compact_d_top_compact_d_top.grp_frame_fu_190.start_for_monitor_U0_U' written by process 'compact_d_top_compact_d_top.grp_frame_fu_190.read_nchw_U0',");
                        end
                    end
                    endcase
                end
            endcase
        end
    endtask

    // report
    initial begin : report_deadlock
        integer cycle_id;
        integer cycle_comp_id;
        integer record_time;
        wait (dl_reset == 1);
        cycle_id = 1;
        record_time = 0;
        while (1) begin
            @ (negedge dl_clock);
            case (CS_fsm)
                ST_DL_DETECTED: begin
                    cycle_comp_id = 2;
                    if (dl_detect_reg != dl_done_reg && stop_report_path == 1'b0) begin
                        if (dl_done_reg == 'b0) begin
                            print_dl_head;
                            record_time = $time;
                        end
                        print_cycle_start(proc_path(origin), cycle_id);
                        cycle_id = cycle_id + 1;
                    end
                    else begin
                        print_dl_end((cycle_id - 1),record_time);
                        @(negedge dl_clock);
                        @(negedge dl_clock);
                        $finish;
                    end
                end
                ST_DL_REPORT: begin
                    if ((|(dl_in_vec)) & ~(|(dl_in_vec & origin_reg)) & ~(|(reported_proc & dl_in_vec))) begin
                        print_cycle_chan_comp(dl_in_vec_reg, dl_in_vec);
                        print_cycle_proc_comp(proc_path(dl_in_vec), cycle_comp_id);
                        cycle_comp_id = cycle_comp_id + 1;
                    end
                    else begin
                        print_cycle_chan_comp(dl_in_vec_reg, dl_in_vec);
                    end
                end
            endcase
        end
    end
 
