// Three planar signed-Q14 inputs; one shared, single-outstanding AXI4 master.
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
    input wire [31:0] m_axi_gmem_rdata, input wire [1:0] m_axi_gmem_rresp,
    input wire m_axi_gmem_rlast, input wire m_axi_gmem_rvalid,
    output wire m_axi_gmem_rready,
    output wire [63:0] m_axi_gmem_awaddr,
    output wire [7:0] m_axi_gmem_awlen, output wire [2:0] m_axi_gmem_awsize,
    output wire [1:0] m_axi_gmem_awburst, output wire m_axi_gmem_awlock,
    output wire [3:0] m_axi_gmem_awcache, output wire [2:0] m_axi_gmem_awprot,
    output wire [3:0] m_axi_gmem_awqos,
    output wire m_axi_gmem_awvalid, input wire m_axi_gmem_awready,
    output wire [31:0] m_axi_gmem_wdata, output wire [3:0] m_axi_gmem_wstrb,
    output wire m_axi_gmem_wlast, output wire m_axi_gmem_wvalid,
    input wire m_axi_gmem_wready, input wire [1:0] m_axi_gmem_bresp,
    input wire m_axi_gmem_bvalid, output wire m_axi_gmem_bready
);
    localparam [63:0] FRAME_BYTES = SCALAR_COUNT * 64'd2;
    localparam [3:0] IDLE=0, AI=1, RI=2, AL=3, RL=4, AD=5, RD=6, W=7, B=8;
    reg [3:0] state;
    reg busy, done;
    reg gie;
    reg [1:0] ier, isr;
    reg [31:0] result;
    reg [63:0] cfg_i, cfg_l, cfg_d, cfg_o;
    reg [31:0] cfg_wi, cfg_wl, cfg_wd, cfg_cookie, cfg_frame;
    reg [31:0] active_frame, completed_frame;
    reg [63:0] ptr_i, ptr_l, ptr_d, ptr_o;
    reg [15:0] wi, wl, wd;
    reg [63:0] byte_index;
    reg [31:0] value_i, value_l, write_word;
    reg aw_sent, w_sent;
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

    function [15:0] blend;
        input signed [15:0] vi, vl, vd;
        reg signed [63:0] pi, pl, pd, rounded;
        begin
            pi=vi*$signed({1'b0,wi});
            pl=vl*$signed({1'b0,wl});
            pd=vd*$signed({1'b0,wd});
            rounded=round_even15(pi+pl+pd);
            if(rounded<0) blend=0;
            else if(rounded>16384) blend=16'd16384;
            else blend=rounded[15:0];
        end
    endfunction

    assign s_axi_control_awready=!aw_hold && !s_axi_control_bvalid;
    assign s_axi_control_wready=!w_hold && !s_axi_control_bvalid;
    assign s_axi_control_arready=!s_axi_control_rvalid;
    assign s_axi_control_rresp=2'b00;
    assign interrupt=gie && |(isr & ier);
    assign m_axi_gmem_araddr=(state==AI?ptr_i:state==AL?ptr_l:ptr_d)+byte_index;
    assign m_axi_gmem_arlen=0;
    assign m_axi_gmem_arsize=3'd2;
    assign m_axi_gmem_arburst=2'b01;
    assign m_axi_gmem_arlock=0;
    assign m_axi_gmem_arcache=4'b0011;
    assign m_axi_gmem_arprot=0;
    assign m_axi_gmem_arqos=0;
    assign m_axi_gmem_arvalid=state==AI || state==AL || state==AD;
    assign m_axi_gmem_rready=state==RI || state==RL || state==RD;
    assign m_axi_gmem_awaddr=ptr_o+byte_index;
    assign m_axi_gmem_awlen=0;
    assign m_axi_gmem_awsize=3'd2;
    assign m_axi_gmem_awburst=2'b01;
    assign m_axi_gmem_awlock=0;
    assign m_axi_gmem_awcache=4'b0011;
    assign m_axi_gmem_awprot=0;
    assign m_axi_gmem_awqos=0;
    assign m_axi_gmem_awvalid=state==W && !aw_sent;
    assign m_axi_gmem_wdata=write_word;
    assign m_axi_gmem_wstrb=4'b1111;
    assign m_axi_gmem_wlast=1;
    assign m_axi_gmem_wvalid=state==W && !w_sent;
    assign m_axi_gmem_bready=state==B;

    always @(posedge ap_clk) begin
        if(!ap_rst_n) begin
            state<=IDLE; busy<=0; done<=0; result<=0;
            gie<=0; ier<=0; isr<=0;
            cfg_i<=0; cfg_l<=0; cfg_d<=0; cfg_o<=0;
            cfg_wi<=0; cfg_wl<=0; cfg_wd<=0; cfg_cookie<=0; cfg_frame<=0;
            active_frame<=0; completed_frame<=0;
            ptr_i<=0; ptr_l<=0; ptr_d<=0; ptr_o<=0;
            wi<=0; wl<=0; wd<=0; byte_index<=0;
            value_i<=0; value_l<=0; write_word<=0; aw_sent<=0; w_sent<=0;
            aw_hold<=0; w_hold<=0; aw_address<=0; w_value<=0; w_strobes<=0;
            s_axi_control_bvalid<=0; s_axi_control_bresp<=0;
            s_axi_control_rvalid<=0; s_axi_control_rdata<=0;
        end else begin
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
                            byte_index<=0; busy<=1; state<=AI;
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
            case(state)
                AI: if(m_axi_gmem_arready) state<=RI;
                AL: if(m_axi_gmem_arready) state<=RL;
                AD: if(m_axi_gmem_arready) state<=RD;
                RI,RL,RD: if(m_axi_gmem_rvalid) begin
                    if(m_axi_gmem_rresp!=0 || !m_axi_gmem_rlast) begin
                        result<=-3; busy<=0; done<=1; state<=IDLE; isr<=isr|2'b11;
                    end else if(state==RI) begin value_i<=m_axi_gmem_rdata; state<=AL; end
                    else if(state==RL) begin value_l<=m_axi_gmem_rdata; state<=AD; end
                    else begin
                        write_word<={blend(value_i[31:16],value_l[31:16],m_axi_gmem_rdata[31:16]),
                                     blend(value_i[15:0],value_l[15:0],m_axi_gmem_rdata[15:0])};
                        aw_sent<=0; w_sent<=0; state<=W;
                    end
                end
                W: begin
                    if(m_axi_gmem_awready) aw_sent<=1;
                    if(m_axi_gmem_wready) w_sent<=1;
                    if((aw_sent || m_axi_gmem_awready) && (w_sent || m_axi_gmem_wready)) state<=B;
                end
                B: if(m_axi_gmem_bvalid) begin
                    if(m_axi_gmem_bresp!=0) begin
                        result<=-3; busy<=0; done<=1; state<=IDLE; isr<=isr|2'b11;
                    end else if(byte_index+4==FRAME_BYTES) begin
                        result<=0; busy<=0; done<=1; completed_frame<=active_frame;
                        state<=IDLE; isr<=isr|2'b11;
                    end else begin byte_index<=byte_index+4; state<=AI; end
                end
                default: begin end
            endcase
        end
    end
endmodule
