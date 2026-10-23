// Independent, bounded AXI test, without the vendor UVM memory/VIP layer.
// Port declarations come from the actual HLS top, connected one-for-one.
`timescale 1ns/1ps
module weather_rtl_test;
@PORTS@
weather_frame_top dut(@CONNECTIONS@);
`ifdef WEATHER_FULL_FRAME
localparam integer DEPTH=2764832;
`else
localparam integer DEPTH=60000;
`endif
localparam [63:0] IN_BASE=64'h10000000, OUT_BASE=64'h20000000;
reg [15:0] input_mem[0:DEPTH-1], output_mem[0:DEPTH-1], golden[0:DEPTH-1];
integer cycle=0, active_n=0, read_beats=0, write_beats=0;
integer active_case=-1;
always #5 ap_clk=~ap_clk;
always @(posedge ap_clk) cycle<=cycle+1;
// One outstanding burst per channel is legal backpressure for a master that
// can issue four. Fixed stalls exercise holding VALID/data across READY=0.
reg rd_busy=0;
reg [63:0] rd_addr;
integer rd_left=0,rd_size=0,ri;
assign m_axi_gmem_in_ARREADY=ap_rst_n && !rd_busy && !m_axi_gmem_in_RVALID && (active_case>=7 || cycle%7!=0);
always @(posedge ap_clk) begin
    if(!ap_rst_n) begin
        rd_busy<=0;m_axi_gmem_in_RVALID<=0;
    end else begin
        if(m_axi_gmem_in_AWVALID || m_axi_gmem_in_WVALID)
            $fatal(1,"input channel attempted write");
        if(m_axi_gmem_in_ARVALID && m_axi_gmem_in_ARREADY) begin
            if(m_axi_gmem_in_ARBURST!==1 || m_axi_gmem_in_ARSIZE>2 ||
               m_axi_gmem_in_ARADDR<IN_BASE ||
               m_axi_gmem_in_ARADDR>=IN_BASE+((active_n*2+3)/4)*4)
                $fatal(1,"invalid input AR addr=%h size=%d",m_axi_gmem_in_ARADDR,m_axi_gmem_in_ARSIZE);
            if((m_axi_gmem_in_ARADDR>>12)!=
               (((m_axi_gmem_in_ARADDR>>m_axi_gmem_in_ARSIZE)+m_axi_gmem_in_ARLEN)<<m_axi_gmem_in_ARSIZE)>>12)
                $fatal(1,"read burst crosses 4K");
            rd_addr<=m_axi_gmem_in_ARADDR;rd_left<=m_axi_gmem_in_ARLEN+1;
            rd_size<=m_axi_gmem_in_ARSIZE;rd_busy<=1;
        end
        if(m_axi_gmem_in_RVALID && m_axi_gmem_in_RREADY) begin
            m_axi_gmem_in_RVALID<=0;read_beats<=read_beats+1;
            rd_left<=rd_left-1;
            rd_addr<=((rd_addr>>rd_size)+1)<<rd_size;
            if(rd_left==1)rd_busy<=0;
        end
        if(rd_busy && !m_axi_gmem_in_RVALID && (active_case>=7 || cycle%5!=0)) begin
            ri=((rd_addr-IN_BASE)>>2)*2;
            if(ri<0 || ri+1>=DEPTH || ri>=((active_n+1)/2)*2)
                $fatal(1,"input beat outside frame addr=%h",rd_addr);
            m_axi_gmem_in_RDATA<={input_mem[ri+1],input_mem[ri]};
            m_axi_gmem_in_RLAST<=rd_left==1;m_axi_gmem_in_RVALID<=1;
        end
    end
end
reg wr_busy=0;
reg b_pending=0;
reg [63:0] wr_addr;
integer wr_left=0,wr_size=0,wi,lane,byte_index,b_delay=0;
assign m_axi_gmem_out_AWREADY=ap_rst_n && !wr_busy && !b_pending && !m_axi_gmem_out_BVALID && (active_case>=7 || cycle%11!=0);
assign m_axi_gmem_out_WREADY=ap_rst_n && wr_busy && (active_case>=7 || cycle%3!=0);
always @(posedge ap_clk) begin
    if(!ap_rst_n) begin wr_busy<=0;b_pending<=0;m_axi_gmem_out_BVALID<=0; end
    else begin
        if(m_axi_gmem_out_ARVALID)$fatal(1,"output channel attempted read");
        if(m_axi_gmem_out_BVALID && m_axi_gmem_out_BREADY)m_axi_gmem_out_BVALID<=0;
        if(b_pending)begin
            if(b_delay==0)begin b_pending<=0;m_axi_gmem_out_BVALID<=1;end
            else b_delay<=b_delay-1;
        end
        if(m_axi_gmem_out_AWVALID && m_axi_gmem_out_AWREADY) begin
            if(m_axi_gmem_out_AWBURST!==1 || m_axi_gmem_out_AWSIZE>2 ||
               m_axi_gmem_out_AWADDR<OUT_BASE || m_axi_gmem_out_AWADDR>=OUT_BASE+active_n*2)
                $fatal(1,"invalid output AW addr=%h",m_axi_gmem_out_AWADDR);
            if((m_axi_gmem_out_AWADDR>>12)!=
               (((m_axi_gmem_out_AWADDR>>m_axi_gmem_out_AWSIZE)+m_axi_gmem_out_AWLEN)<<m_axi_gmem_out_AWSIZE)>>12)
                $fatal(1,"write burst crosses 4K");
            wr_addr<=m_axi_gmem_out_AWADDR;wr_left<=m_axi_gmem_out_AWLEN+1;
            wr_size<=m_axi_gmem_out_AWSIZE;wr_busy<=1;
        end
        if(m_axi_gmem_out_WVALID && m_axi_gmem_out_WREADY) begin
            if(m_axi_gmem_out_WLAST!==(wr_left==1))$fatal(1,"WLAST disagrees with AWLEN");
            for(lane=0;lane<4;lane=lane+1)if(m_axi_gmem_out_WSTRB[lane])begin
                byte_index=((wr_addr-OUT_BASE)>>2)*4+lane;
                if(byte_index<0 || byte_index>=active_n*2)$fatal(1,"write outside active output");
                wi=byte_index/2;
                if(byte_index%2)output_mem[wi][15:8]<=m_axi_gmem_out_WDATA[lane*8+:8];
                else output_mem[wi][7:0]<=m_axi_gmem_out_WDATA[lane*8+:8];
            end
            write_beats<=write_beats+1;wr_left<=wr_left-1;
            wr_addr<=((wr_addr>>wr_size)+1)<<wr_size;
            if(wr_left==1)begin wr_busy<=0;b_pending<=1;b_delay<=active_case>=7 ? 0 : 5+cycle%13;end
        end
    end
end
// Observe the core's actual done pulse, before the PS polling/readback delay
// could conceal a late write response. The B handshake on this edge may drain
// the final response, but data/burst work must never remain after done.
always @(posedge ap_clk)if(ap_rst_n && dut.ap_done && active_case>=0)begin
    if(wr_busy || b_pending || (m_axi_gmem_out_BVALID && !m_axi_gmem_out_BREADY))
        $fatal(1,"core done before delayed DDR write response drained");
end
// Unused AXI inputs are explicitly tied; expected directions asserted above.
assign m_axi_gmem_in_AWREADY=0,m_axi_gmem_in_WREADY=0;
assign m_axi_gmem_in_BVALID=0,m_axi_gmem_in_BRESP=0,m_axi_gmem_in_BID=0,m_axi_gmem_in_BUSER=0;
assign m_axi_gmem_in_RRESP=0,m_axi_gmem_in_RID=0,m_axi_gmem_in_RUSER=0;
assign m_axi_gmem_out_ARREADY=0,m_axi_gmem_out_RVALID=0,m_axi_gmem_out_RDATA=0;
assign m_axi_gmem_out_RLAST=0,m_axi_gmem_out_RID=0,m_axi_gmem_out_RUSER=0,m_axi_gmem_out_RRESP=0;
assign m_axi_gmem_out_BRESP=0,m_axi_gmem_out_BID=0,m_axi_gmem_out_BUSER=0;
reg ar_stalled=0,aw_stalled=0,w_stalled=0;
reg [76:0] saved_ar,saved_aw;
reg [36:0] saved_w;
always @(posedge ap_clk)if(ap_rst_n)begin
    if(ar_stalled && (!m_axi_gmem_in_ARVALID || saved_ar!==
       {m_axi_gmem_in_ARADDR,m_axi_gmem_in_ARLEN,m_axi_gmem_in_ARSIZE,m_axi_gmem_in_ARBURST}))
        $fatal(1,"AR changed while stalled");
    if(aw_stalled && (!m_axi_gmem_out_AWVALID || saved_aw!==
       {m_axi_gmem_out_AWADDR,m_axi_gmem_out_AWLEN,m_axi_gmem_out_AWSIZE,m_axi_gmem_out_AWBURST}))
        $fatal(1,"AW changed while stalled");
    if(w_stalled && (!m_axi_gmem_out_WVALID || saved_w!==
       {m_axi_gmem_out_WDATA,m_axi_gmem_out_WSTRB,m_axi_gmem_out_WLAST}))
        $fatal(1,"W changed while stalled");
    ar_stalled<=m_axi_gmem_in_ARVALID && !m_axi_gmem_in_ARREADY;
    aw_stalled<=m_axi_gmem_out_AWVALID && !m_axi_gmem_out_AWREADY;
    w_stalled<=m_axi_gmem_out_WVALID && !m_axi_gmem_out_WREADY;
    saved_ar<={m_axi_gmem_in_ARADDR,m_axi_gmem_in_ARLEN,m_axi_gmem_in_ARSIZE,m_axi_gmem_in_ARBURST};
    saved_aw<={m_axi_gmem_out_AWADDR,m_axi_gmem_out_AWLEN,m_axi_gmem_out_AWSIZE,m_axi_gmem_out_AWBURST};
    saved_w<={m_axi_gmem_out_WDATA,m_axi_gmem_out_WSTRB,m_axi_gmem_out_WLAST};
end

task automatic csr_write(input [6:0] addr,input [31:0] data);
    begin
        @(negedge ap_clk);s_axi_CTRL_AWADDR=addr;s_axi_CTRL_AWVALID=1;
        do @(posedge ap_clk);while(!s_axi_CTRL_AWREADY);
        @(negedge ap_clk);s_axi_CTRL_AWVALID=0;s_axi_CTRL_WDATA=data;s_axi_CTRL_WVALID=1;
        do @(posedge ap_clk);while(!s_axi_CTRL_WREADY);
        @(negedge ap_clk);s_axi_CTRL_WVALID=0;
        do @(posedge ap_clk);while(!s_axi_CTRL_BVALID);
        if(s_axi_CTRL_BRESP!==0)$fatal(1,"AXI Lite write response");
    end
endtask
task automatic csr_read(input [6:0] addr,output [31:0] data);
    begin
        @(negedge ap_clk);s_axi_CTRL_ARADDR=addr;s_axi_CTRL_ARVALID=1;
        do @(posedge ap_clk);while(!s_axi_CTRL_ARREADY);
        @(negedge ap_clk);s_axi_CTRL_ARVALID=0;
        do @(posedge ap_clk);while(!s_axi_CTRL_RVALID);
        if(s_axi_CTRL_RRESP!==0)$fatal(1,"AXI Lite read response");
        data=s_axi_CTRL_RDATA;
    end
endtask
task automatic frame(input integer index,input integer mode,input integer h,input integer w);
    integer i,start_cycle,rb,wb;
    reg [31:0] ctrl,ret;
    string file_name;
    begin
        active_case=index;active_n=3*h*w;
        if(active_n>=DEPTH)$fatal(1,"test allocation");
        for(i=0;i<DEPTH;i=i+1)begin input_mem[i]=16'h1357;output_mem[i]=16'h2468;end
        file_name=$sformatf("input_%0d.hex",index);$readmemh(file_name,input_mem,0,active_n-1);
        file_name=$sformatf("golden_%0d.hex",index);$readmemh(file_name,golden,0,active_n-1);
        csr_write('h18,IN_BASE[31:0]);csr_write('h1c,0);
        csr_write('h24,OUT_BASE[31:0]);csr_write('h28,0);
        csr_write('h30,h);csr_write('h38,w);csr_write('h40,mode);
        // Read back changed controls before start, as a PS integration check.
        csr_read('h30,ret);if(ret!==h)$fatal(1,"height readback");
        csr_read('h38,ret);if(ret!==w)$fatal(1,"width readback");
        rb=read_beats;wb=write_beats;start_cycle=cycle;
        csr_write(0,1);ctrl=0;
        while(!(ctrl&2))begin
            repeat(16)@(posedge ap_clk);csr_read(0,ctrl);
            if(cycle-start_cycle>(index<5 ? 200000 : 10000000))
                $fatal(1,"timeout case=%0d FSM=%h rb=%0d wb=%0d rd=%h wr=%h",index,dut.ap_CS_fsm,
                    read_beats-rb,write_beats-wb,rd_addr,wr_addr);
        end
        csr_read('h10,ret);if(ret!==0)$fatal(1,"core error %h",ret);
        if(rd_busy || wr_busy || b_pending || m_axi_gmem_out_BVALID)$fatal(1,"done before DDR drain");
        for(i=0;i<active_n;i=i+1)
            if(output_mem[i]!==golden[i])$fatal(1,"mismatch case=%0d i=%0d got=%h expected=%h",index,i,output_mem[i],golden[i]);
        for(i=active_n;i<DEPTH;i=i+1)
            if(output_mem[i]!==16'h2468 || input_mem[i]!==16'h1357)$fatal(1,"tail guard");
        $display("WEATHER_RTL_FRAME_PASS case=%0d task=%0d shape=%0dx%0d cycles=%0d read_beats=%0d write_beats=%0d",index,mode,h,w,cycle-start_cycle,read_beats-rb,write_beats-wb);
        if(index>=7 && cycle-start_cycle>3333333)$fatal(1,"720p30 cycle budget exceeded");
    end
endtask
initial begin
    ap_clk=0;ap_rst_n=0;s_axi_CTRL_AWVALID=0;s_axi_CTRL_WVALID=0;
    s_axi_CTRL_ARVALID=0;s_axi_CTRL_BREADY=1;s_axi_CTRL_RREADY=1;s_axi_CTRL_WSTRB=15;
    m_axi_gmem_in_RVALID=0;m_axi_gmem_out_BVALID=0;
    repeat(10)@(negedge ap_clk);ap_rst_n=1;
    repeat(10)@(negedge ap_clk);
    frame(0,0,8,8);frame(1,1,8,8);frame(2,0,8,8);
    frame(3,0,131,1);frame(4,1,1,133);
    frame(5,0,131,133);frame(6,1,131,133);
`ifdef WEATHER_FULL_FRAME
    frame(7,0,720,1280);frame(8,1,720,1280);
    $display("WEATHER_RTL_SEQUENCE_PASS frames=9");$finish;
`else
    $display("WEATHER_RTL_SEQUENCE_PASS frames=7");$finish;
`endif
end
initial begin
    // Includes a bound for MMIO handshakes as well as the frame poll loop.
    #600000000;$fatal(1,"global timeout case=%0d",active_case);
end
endmodule
