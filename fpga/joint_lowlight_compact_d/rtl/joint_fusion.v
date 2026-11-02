`timescale 1ns/1ps
// Three Q14 streams, 128-bit INCR bursts, independent read/write engines.
// Eight arithmetic lanes; input/output FIFOs decouple DDR from the pipeline.
// SCALAR_COUNT is fixed to 3*720*1272 in the packaged production core.
module joint_fusion #(
    parameter integer SCALAR_COUNT = 2747520
)(
    input wire ap_clk, input wire ap_rst_n,
    input wire [6:0] s_axi_control_awaddr,
    input wire s_axi_control_awvalid, output wire s_axi_control_awready,
    input wire [31:0] s_axi_control_wdata, input wire [3:0] s_axi_control_wstrb,
    input wire s_axi_control_wvalid, output wire s_axi_control_wready,
    output reg [1:0] s_axi_control_bresp, output reg s_axi_control_bvalid,
    input wire s_axi_control_bready,
    input wire [6:0] s_axi_control_araddr,
    input wire s_axi_control_arvalid, output wire s_axi_control_arready,
    output reg [31:0] s_axi_control_rdata, output wire [1:0] s_axi_control_rresp,
    output reg s_axi_control_rvalid, input wire s_axi_control_rready,
    output wire interrupt,
    output wire [63:0] m_axi_gmem_araddr,
    output wire [7:0] m_axi_gmem_arlen, output wire [2:0] m_axi_gmem_arsize,
    output wire [1:0] m_axi_gmem_arburst, output wire m_axi_gmem_arlock,
    output wire [3:0] m_axi_gmem_arcache, output wire [2:0] m_axi_gmem_arprot,
    output wire [3:0] m_axi_gmem_arqos,
    output wire m_axi_gmem_arvalid, input wire m_axi_gmem_arready,
    input wire [127:0] m_axi_gmem_rdata, input wire [1:0] m_axi_gmem_rresp,
    input wire m_axi_gmem_rlast, input wire m_axi_gmem_rvalid,
    output wire m_axi_gmem_rready,
    output wire [63:0] m_axi_gmem_awaddr,
    output wire [7:0] m_axi_gmem_awlen, output wire [2:0] m_axi_gmem_awsize,
    output wire [1:0] m_axi_gmem_awburst, output wire m_axi_gmem_awlock,
    output wire [3:0] m_axi_gmem_awcache, output wire [2:0] m_axi_gmem_awprot,
    output wire [3:0] m_axi_gmem_awqos,
    output wire m_axi_gmem_awvalid, input wire m_axi_gmem_awready,
    output wire [127:0] m_axi_gmem_wdata, output wire [15:0] m_axi_gmem_wstrb,
    output wire m_axi_gmem_wlast, output wire m_axi_gmem_wvalid,
    input wire m_axi_gmem_wready, input wire [1:0] m_axi_gmem_bresp,
    input wire m_axi_gmem_bvalid, output wire m_axi_gmem_bready
);
    localparam [63:0] FRAME_BYTES = SCALAR_COUNT * 64'd2;
    localparam integer BEAT_COUNT = (SCALAR_COUNT+7)/8;
    localparam integer FIFO_DEPTH = 256;
    localparam [1:0] R_IDLE=0, R_ADDR=1, R_DATA=2;
    localparam [1:0] W_IDLE=0, W_SEND=1, W_RESP=2;
    reg [1:0] rstate, wstate;
    reg dp_start, dp_active, dp_finish, aborted;
    reg [1:0] rbranch;
    reg [31:0] rpos_i, rpos_l, rpos_d, written;
    reg [63:0] raddress, waddress;
    reg [8:0] rlength, wlength, rindex, windex;
    reg aw_sent, w_sent;
    wire [127:0] fifo_i_data, fifo_l_data, fifo_d_data, fifo_o_data;
    wire [8:0] count_i, count_l, count_d, count_o;
    wire empty_i, empty_l, empty_d, empty_o, full_i, full_l, full_d, full_o;
    wire read_fire=m_axi_gmem_rvalid && m_axi_gmem_rready;
    wire write_fire=m_axi_gmem_wvalid && m_axi_gmem_wready;
    wire read_fault=read_fire && (m_axi_gmem_rresp!=0 ||
        (m_axi_gmem_rlast != (rindex==rlength-1)));
    wire write_fault=m_axi_gmem_bvalid && m_axi_gmem_bready && m_axi_gmem_bresp!=0;
    wire fifo_pop=dp_active && !aborted && !empty_i && !empty_l && !empty_d && !full_o;
    wire pipe_ce=!full_o;
    reg [4:0] pipe_valid;
    reg signed [32:0] product_i[0:7], product_l[0:7], product_d[0:7];
    reg signed [63:0] pair_sum[0:7], delayed_d[0:7], total_sum[0:7], rounded[0:7];
    reg [127:0] packed_output;
    wire fifo_push_o=dp_active && !aborted && pipe_ce && pipe_valid[4];
    reg [63:0] ptr_i, ptr_l, ptr_d, ptr_o;
    wire [31:0] selected_pos=rbranch==0?rpos_i:rbranch==1?rpos_l:rpos_d;
    wire [63:0] selected_ptr=rbranch==0?ptr_i:rbranch==1?ptr_l:ptr_d;
    wire [8:0] selected_count=rbranch==0?count_i:rbranch==1?count_l:count_d;
    wire [63:0] next_read_address=selected_ptr+{28'd0,selected_pos,4'd0};
    wire [63:0] next_write_address=ptr_o+{28'd0,written,4'd0};
    wire [8:0] next_read_length=burst_beats(next_read_address,BEAT_COUNT-selected_pos);
    wire [8:0] next_write_length=burst_beats(next_write_address,BEAT_COUNT-written);
    reg busy, done;
    reg gie;
    reg [1:0] ier, isr;
    reg [31:0] result;
    reg [63:0] cfg_i, cfg_l, cfg_d, cfg_o;
    reg [31:0] cfg_wi, cfg_wl, cfg_wd, cfg_cookie, cfg_frame;
    reg [31:0] active_frame, completed_frame;
    reg [15:0] wi, wl, wd;
    reg aw_hold, w_hold;
    reg [6:0] aw_address;
    reg [31:0] w_value;
    reg [3:0] w_strobes;

    function [31:0] merge_word;
        input [31:0] old_value, new_value;
        input [3:0] strobes;
        integer j;
        begin
            merge_word=old_value;
            for(j=0;j<4;j=j+1)
                if(strobes[j]) merge_word[j*8+:8]=new_value[j*8+:8];
        end
    endfunction

    function valid_range;
        input [63:0] p;
        begin valid_range=(p[5:0]==0 && p <= (64'h80000000-FRAME_BYTES)); end
    endfunction

    function overlap_output;
        input [63:0] src, dst;
        begin overlap_output=(src < dst+FRAME_BYTES && dst < src+FRAME_BYTES); end
    endfunction

    // Magnitude rounding makes negative midpoint behavior independent of the
    // language's signed division/shift rules. Valid sums fit comfortably in i64.
    function signed [63:0] round_even15;
        input signed [63:0] acc;
        reg [63:0] magnitude, quotient;
        reg [14:0] remainder;
        begin
            magnitude=acc<0 ? -acc : acc;
            quotient=magnitude>>15;
            remainder=magnitude[14:0];
            if(remainder>15'd16384 || (remainder==15'd16384 && quotient[0]))
                quotient=quotient+1;
            round_even15=acc<0 ? -$signed(quotient) : $signed(quotient);
        end
    endfunction

    // An INCR burst never crosses a 4-KiB page; the tail may be <64 beats.
    function [8:0] burst_beats;
        input [63:0] address;
        input [31:0] remaining;
        reg [8:0] boundary, n;
        begin
            boundary=9'd256-{1'b0,address[11:4]};
            n=boundary<64?boundary:9'd64;
            burst_beats=remaining<n?remaining[8:0]:n;
        end
    endfunction

    // Distributed RAM is deliberate: the K26 baseline already uses 58/64 URAM.
    // FIFO data is not reset; resetting pointers/count invalidates all entries.
    joint_fusion_fifo fi(ap_clk,ap_rst_n,dp_start,
        read_fire && !aborted && !read_fault && rbranch==0,m_axi_gmem_rdata,
        fifo_pop,fifo_i_data,count_i,empty_i,full_i);
    joint_fusion_fifo fl(ap_clk,ap_rst_n,dp_start,
        read_fire && !aborted && !read_fault && rbranch==1,m_axi_gmem_rdata,
        fifo_pop,fifo_l_data,count_l,empty_l,full_l);
    joint_fusion_fifo fd(ap_clk,ap_rst_n,dp_start,
        read_fire && !aborted && !read_fault && rbranch==2,m_axi_gmem_rdata,
        fifo_pop,fifo_d_data,count_d,empty_d,full_d);
    joint_fusion_fifo fo(ap_clk,ap_rst_n,dp_start,
        fifo_push_o,packed_output,write_fire,fifo_o_data,count_o,empty_o,full_o);

    integer lane;
    always @(posedge ap_clk) begin
        if(!ap_rst_n || dp_start) begin
            pipe_valid<=0;
        end else if(aborted || !dp_active) begin
            pipe_valid<=0;
        end else if(pipe_ce) begin
            pipe_valid<={pipe_valid[3:0],fifo_pop};
            for(lane=0;lane<8;lane=lane+1) begin
                // Stage 0: 24 parallel DSP products (8 samples x 3 branches).
                product_i[lane]<=$signed(fifo_i_data[lane*16+:16])*$signed({1'b0,wi});
                product_l[lane]<=$signed(fifo_l_data[lane*16+:16])*$signed({1'b0,wl});
                product_d[lane]<=$signed(fifo_d_data[lane*16+:16])*$signed({1'b0,wd});
                // Stages 1/2: signed 64-bit accumulation, no intermediate rounding.
                pair_sum[lane]<={{31{product_i[lane][32]}},product_i[lane]}+
                                {{31{product_l[lane][32]}},product_l[lane]};
                delayed_d[lane]<={{31{product_d[lane][32]}},product_d[lane]};
                total_sum[lane]<=pair_sum[lane]+delayed_d[lane];
                // Stages 3/4: a single RNE, then [0,16384] clamp and repack.
                rounded[lane]<=round_even15(total_sum[lane]);
                packed_output[lane*16+:16]<=rounded[lane]<0?16'd0:
                    rounded[lane]>16384?16'd16384:rounded[lane][15:0];
            end
        end
    end

    // Read and write engines run independently. A write burst is issued only
    // after its entire payload is buffered, so even an abort can drain it.
    always @(posedge ap_clk) begin
        if(!ap_rst_n) begin
            dp_active<=0; dp_finish<=0; aborted<=0;
            rstate<=R_IDLE; wstate<=W_IDLE; rbranch<=0;
            rpos_i<=0; rpos_l<=0; rpos_d<=0; written<=0;
            raddress<=0; waddress<=0; rlength<=0; wlength<=0;
            rindex<=0; windex<=0; aw_sent<=0; w_sent<=0;
        end else begin
            dp_finish<=0;
            if(dp_start) begin
                dp_active<=1; aborted<=0; rstate<=R_IDLE; wstate<=W_IDLE;
                rbranch<=0; rpos_i<=0; rpos_l<=0; rpos_d<=0; written<=0;
                rindex<=0; windex<=0; aw_sent<=0; w_sent<=0;
            end else if(dp_active) begin
                if(read_fault || write_fault) aborted<=1;
                case(rstate)
                    R_IDLE: if(!aborted) begin
                        if(selected_pos<BEAT_COUNT && selected_count+next_read_length<=FIFO_DEPTH) begin
                            raddress<=next_read_address; rlength<=next_read_length;
                            rindex<=0; rstate<=R_ADDR;
                        end else rbranch<=rbranch==2?0:rbranch+1'b1;
                    end
                    R_ADDR: if(m_axi_gmem_arready) rstate<=R_DATA;
                    R_DATA: if(read_fire) begin
                        if(m_axi_gmem_rlast) begin
                            rstate<=R_IDLE;
                            case(rbranch)
                                0:rpos_i<=rpos_i+rlength;
                                1:rpos_l<=rpos_l+rlength;
                                2:rpos_d<=rpos_d+rlength;
                            endcase
                            rbranch<=rbranch==2?0:rbranch+1'b1;
                        end else if(rindex<rlength) rindex<=rindex+1'b1;
                        // Missing RLAST: stay active and drain until RLAST/reset.
                    end
                endcase
                case(wstate)
                    W_IDLE: if(!aborted && written<BEAT_COUNT && count_o>=next_write_length) begin
                        waddress<=next_write_address; wlength<=next_write_length;
                        windex<=0; aw_sent<=0; w_sent<=0; wstate<=W_SEND;
                    end
                    W_SEND: begin
                        if(m_axi_gmem_awvalid && m_axi_gmem_awready) aw_sent<=1;
                        if(write_fire) begin
                            if(m_axi_gmem_wlast) w_sent<=1;
                            else windex<=windex+1'b1;
                        end
                        if((aw_sent || m_axi_gmem_awready) &&
                           (w_sent || (write_fire && m_axi_gmem_wlast))) wstate<=W_RESP;
                    end
                    W_RESP: if(m_axi_gmem_bvalid) begin
                        written<=written+wlength; wstate<=W_IDLE;
                    end
                endcase
                // Never announce done while an accepted AXI transaction remains.
                if((aborted || written==BEAT_COUNT) && rstate==R_IDLE && wstate==W_IDLE) begin
                    dp_finish<=1; dp_active<=0;
                end
            end
        end
    end

    assign s_axi_control_awready=!aw_hold && !s_axi_control_bvalid;
    assign s_axi_control_wready=!w_hold && !s_axi_control_bvalid;
    assign s_axi_control_arready=!s_axi_control_rvalid;
    assign s_axi_control_rresp=2'b00;
    assign interrupt=gie && |(isr & ier);
    assign m_axi_gmem_araddr=raddress;
    assign m_axi_gmem_arlen=rlength-1'b1;
    assign m_axi_gmem_arsize=3'd4;
    assign m_axi_gmem_arburst=2'b01;
    assign m_axi_gmem_arlock=0;
    assign m_axi_gmem_arcache=4'b0011;
    assign m_axi_gmem_arprot=0;
    assign m_axi_gmem_arqos=0;
    assign m_axi_gmem_arvalid=rstate==R_ADDR;
    assign m_axi_gmem_rready=rstate==R_DATA &&
        (aborted || (rbranch==0?!full_i:rbranch==1?!full_l:!full_d));
    assign m_axi_gmem_awaddr=waddress;
    assign m_axi_gmem_awlen=wlength-1'b1;
    assign m_axi_gmem_awsize=3'd4;
    assign m_axi_gmem_awburst=2'b01;
    assign m_axi_gmem_awlock=0;
    assign m_axi_gmem_awcache=4'b0011;
    assign m_axi_gmem_awprot=0;
    assign m_axi_gmem_awqos=0;
    assign m_axi_gmem_awvalid=wstate==W_SEND && !aw_sent;
    assign m_axi_gmem_wdata=fifo_o_data;
    assign m_axi_gmem_wstrb=16'hffff;
    assign m_axi_gmem_wlast=windex==wlength-1'b1;
    assign m_axi_gmem_wvalid=wstate==W_SEND && !w_sent && !empty_o;
    assign m_axi_gmem_bready=wstate==W_RESP;

    always @(posedge ap_clk) begin
        if(!ap_rst_n) begin
            dp_start<=0; busy<=0; done<=0; result<=0;
            gie<=0; ier<=0; isr<=0;
            cfg_i<=0; cfg_l<=0; cfg_d<=0; cfg_o<=0;
            cfg_wi<=0; cfg_wl<=0; cfg_wd<=0; cfg_cookie<=0; cfg_frame<=0;
            active_frame<=0; completed_frame<=0;
            ptr_i<=0; ptr_l<=0; ptr_d<=0; ptr_o<=0;
            wi<=0; wl<=0; wd<=0;
            aw_hold<=0; w_hold<=0; aw_address<=0; w_value<=0; w_strobes<=0;
            s_axi_control_bvalid<=0; s_axi_control_bresp<=0;
            s_axi_control_rvalid<=0; s_axi_control_rdata<=0;
        end else begin
            dp_start<=0;
            if(s_axi_control_bvalid && s_axi_control_bready) s_axi_control_bvalid<=0;
            if(s_axi_control_rvalid && s_axi_control_rready) s_axi_control_rvalid<=0;
            if(s_axi_control_awvalid && s_axi_control_awready) begin
                aw_hold<=1; aw_address<=s_axi_control_awaddr;
            end
            if(s_axi_control_wvalid && s_axi_control_wready) begin
                w_hold<=1; w_value<=s_axi_control_wdata; w_strobes<=s_axi_control_wstrb;
            end
            if(aw_hold && w_hold && !s_axi_control_bvalid) begin
                aw_hold<=0; w_hold<=0; s_axi_control_bvalid<=1; s_axi_control_bresp<=0;
                case(aw_address)
                    7'h00: if(w_strobes[0] && w_value[0] && !busy) begin
                        done<=0; result<=0; completed_frame<=0;
                        active_frame<=cfg_frame;
                        if(cfg_cookie!=32'h4a463031) begin result<=-1; done<=1; isr<=isr|2'b11; end
                        else if(cfg_wi>32768 || cfg_wl>32768 || cfg_wd>32768 ||
                          ({2'b0,cfg_wi}+{2'b0,cfg_wl}+{2'b0,cfg_wd})!=34'd32768) begin
                            result<=-2; done<=1; isr<=isr|2'b11;
                        end else if(!valid_range(cfg_i) || !valid_range(cfg_l) ||
                            !valid_range(cfg_d) || !valid_range(cfg_o) ||
                            overlap_output(cfg_i,cfg_o) || overlap_output(cfg_l,cfg_o) ||
                            overlap_output(cfg_d,cfg_o)) begin
                            result<=-4; done<=1; isr<=isr|2'b11;
                        end else begin
                            ptr_i<=cfg_i; ptr_l<=cfg_l; ptr_d<=cfg_d; ptr_o<=cfg_o;
                            wi<=cfg_wi[15:0]; wl<=cfg_wl[15:0]; wd<=cfg_wd[15:0];
                            busy<=1; dp_start<=1;
                        end
                    end
                    7'h04: if(w_strobes[0]) gie<=w_value[0];
                    7'h08: if(w_strobes[0]) ier<=w_value[1:0];
                    7'h0c: if(w_strobes[0]) isr<=isr^w_value[1:0];
                    7'h18: cfg_i[31:0]<=merge_word(cfg_i[31:0],w_value,w_strobes);
                    7'h1c: cfg_i[63:32]<=merge_word(cfg_i[63:32],w_value,w_strobes);
                    7'h24: cfg_l[31:0]<=merge_word(cfg_l[31:0],w_value,w_strobes);
                    7'h28: cfg_l[63:32]<=merge_word(cfg_l[63:32],w_value,w_strobes);
                    7'h30: cfg_d[31:0]<=merge_word(cfg_d[31:0],w_value,w_strobes);
                    7'h34: cfg_d[63:32]<=merge_word(cfg_d[63:32],w_value,w_strobes);
                    7'h3c: cfg_o[31:0]<=merge_word(cfg_o[31:0],w_value,w_strobes);
                    7'h40: cfg_o[63:32]<=merge_word(cfg_o[63:32],w_value,w_strobes);
                    7'h48: cfg_wi<=merge_word(cfg_wi,w_value,w_strobes);
                    7'h50: cfg_wl<=merge_word(cfg_wl,w_value,w_strobes);
                    7'h58: cfg_wd<=merge_word(cfg_wd,w_value,w_strobes);
                    7'h60: cfg_cookie<=merge_word(cfg_cookie,w_value,w_strobes);
                    7'h68: cfg_frame<=merge_word(cfg_frame,w_value,w_strobes);
                    default: s_axi_control_bresp<=2'b10;
                endcase
            end
            if(s_axi_control_arvalid && s_axi_control_arready) begin
                s_axi_control_rvalid<=1;
                case(s_axi_control_araddr)
                    7'h00: begin s_axi_control_rdata<={28'd0,!busy,!busy,done,1'b0}; done<=0; end
                    7'h04: s_axi_control_rdata<={31'd0,gie};
                    7'h08: s_axi_control_rdata<={30'd0,ier};
                    7'h0c: s_axi_control_rdata<={30'd0,isr};
                    7'h10: s_axi_control_rdata<=result;
                    7'h18: s_axi_control_rdata<=cfg_i[31:0];
                    7'h1c: s_axi_control_rdata<=cfg_i[63:32];
                    7'h24: s_axi_control_rdata<=cfg_l[31:0];
                    7'h28: s_axi_control_rdata<=cfg_l[63:32];
                    7'h30: s_axi_control_rdata<=cfg_d[31:0];
                    7'h34: s_axi_control_rdata<=cfg_d[63:32];
                    7'h3c: s_axi_control_rdata<=cfg_o[31:0];
                    7'h40: s_axi_control_rdata<=cfg_o[63:32];
                    7'h48: s_axi_control_rdata<=cfg_wi;
                    7'h50: s_axi_control_rdata<=cfg_wl;
                    7'h58: s_axi_control_rdata<=cfg_wd;
                    7'h60: s_axi_control_rdata<=cfg_cookie;
                    7'h68: s_axi_control_rdata<=cfg_frame;
                    7'h70: s_axi_control_rdata<=completed_frame;
                    7'h74: s_axi_control_rdata<=active_frame;
                    default: s_axi_control_rdata<=0;
                endcase
            end
            if(dp_finish) begin
                result<=aborted?-3:0; busy<=0; done<=1;
                if(!aborted) completed_frame<=active_frame;
                isr<=isr|2'b11;
            end
        end
    end
endmodule

// Four independent 256 x 128-bit FIFOs, each with one asynchronous read port.
// Resource choice is explicit; OOC/system reports quantify its LUT cost.
module joint_fusion_fifo(
    input wire clk, input wire rst_n, input wire clear,
    input wire push, input wire [127:0] din, input wire pop,
    output wire [127:0] dout, output reg [8:0] count,
    output wire empty, output wire full
);
    (* ram_style="distributed" *) reg [127:0] mem[0:255];
    reg [7:0] rp,wp;
    assign dout=mem[rp];
    assign empty=count==0;
    assign full=count==256;
    always @(posedge clk) begin
        if(!rst_n || clear) begin rp<=0;wp<=0;count<=0;end
        else begin
            if(push && !full) begin mem[wp]<=din;wp<=wp+1'b1;end
            if(pop && !empty) rp<=rp+1'b1;
            case({push && !full,pop && !empty})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:begin end
            endcase
        end
    end
endmodule
