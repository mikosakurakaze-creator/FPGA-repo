// Independent AXI4 RAM for simulation. Addresses are test fixtures, not board allocations.
`timescale 1ns/1ps
module gdn_axi_bounded_memory #(
    parameter [63:0] BASE=0, parameter integer BYTES=4096,
    parameter integer DATA_WIDTH=32,ID_WIDTH=1,
    parameter integer R0=0,N0=0,R1=0,N1=0,R2=0,N2=0,
    parameter integer WR1=0,WR2=0
)(input clk,input resetn,
  input [63:0] ARADDR,input [7:0] ARLEN,input [2:0] ARSIZE,input [1:0] ARBURST,input [ID_WIDTH-1:0] ARID,
  input ARVALID,output ARREADY,output reg [DATA_WIDTH-1:0] RDATA=0,output reg RLAST=0,
  output reg [ID_WIDTH-1:0] RID=0,output [1:0] RRESP,output reg RVALID=0,input RREADY,
  input [63:0] AWADDR,input [7:0] AWLEN,input [2:0] AWSIZE,input [1:0] AWBURST,input [ID_WIDTH-1:0] AWID,
  input AWVALID,output AWREADY,input [DATA_WIDTH-1:0] WDATA,input [DATA_WIDTH/8-1:0] WSTRB,input WLAST,
  input WVALID,output WREADY,output reg [ID_WIDTH-1:0] BID=0,output [1:0] BRESP,output reg BVALID=0,input BREADY);
reg [31:0] mem[0:BYTES/4-1];
integer cycle=0,read_beats=0,write_beats=0;
reg rd_busy=0,wr_busy=0,b_pending=0;
reg [ID_WIDTH-1:0] rd_id=0;
reg [63:0] rd_addr=0,wr_addr=0;
integer rd_left=0,wr_left=0,rd_size=0,wr_size=0,delay_b=0,lane,idx;
function automatic allowed(input [63:0] at,input writing);
reg [63:0] x;
begin
    x=at-BASE;
    allowed=at>=BASE && x<BYTES &&
      ((!writing && x>=R0 && x<R0+((N0+63)/64)*64) ||
       ((!writing || WR1) && x>=R1 && x<R1+(writing ? N1 : ((N1+63)/64)*64)) ||
       ((!writing || WR2) && x>=R2 && x<R2+(writing ? N2 : ((N2+63)/64)*64)));
end
endfunction
assign RRESP=0,BRESP=0;
assign ARREADY=resetn && !rd_busy && !RVALID && cycle%7!=0;
assign AWREADY=resetn && !wr_busy && !b_pending && !BVALID && cycle%11!=0;
assign WREADY=resetn && wr_busy && cycle%3!=0;
always @(posedge clk) begin
    cycle<=cycle+1;
    if(!resetn)begin rd_busy<=0;wr_busy<=0;b_pending<=0;RVALID<=0;BVALID<=0;end
    else begin
        if(ARVALID && ARREADY)begin
            if(ARBURST!==1 || ARSIZE>$clog2(DATA_WIDTH/8) || (ARADDR & ((64'd1<<ARSIZE)-1))!=0 ||
              !allowed(ARADDR,0) || !allowed(ARADDR+((ARLEN+1)<<ARSIZE)-1,0))
                $fatal(1,"invalid AR addr=%h len=%0d size=%0d base=%h",ARADDR,ARLEN,ARSIZE,BASE);
            if((ARADDR>>12)!=((ARADDR+((ARLEN+1)<<ARSIZE)-1)>>12))$fatal(1,"AR crosses 4K");
            rd_addr<=ARADDR;rd_left<=ARLEN+1;rd_size<=ARSIZE;rd_busy<=1;rd_id<=ARID;
        end
        if(RVALID && RREADY)begin
            RVALID<=0;read_beats<=read_beats+1;rd_left<=rd_left-1;
            rd_addr<=rd_addr+(64'd1<<rd_size);
            if(rd_left==1)rd_busy<=0;
        end
        if(rd_busy && !RVALID && cycle%5!=0)begin
            for(integer word_lane=0;word_lane<DATA_WIDTH/32;word_lane=word_lane+1)
                RDATA[word_lane*32+:32]<=mem[((rd_addr-BASE)/(DATA_WIDTH/8))*(DATA_WIDTH/32)+word_lane];
            RLAST<=rd_left==1;RID<=rd_id;RVALID<=1;
        end
        if(BVALID && BREADY)BVALID<=0;
        if(b_pending)begin
            if(delay_b==0)begin b_pending<=0;BVALID<=1;end
            else delay_b<=delay_b-1;
        end
        if(AWVALID && AWREADY)begin
            if(AWBURST!==1 || AWSIZE>$clog2(DATA_WIDTH/8) || (AWADDR & ((64'd1<<AWSIZE)-1))!=0 ||
              !allowed(AWADDR,0) || !allowed(AWADDR+((AWLEN+1)<<AWSIZE)-1,0))
                $fatal(1,"invalid AW addr=%h len=%0d size=%0d base=%h",AWADDR,AWLEN,AWSIZE,BASE);
            if((AWADDR>>12)!=((AWADDR+((AWLEN+1)<<AWSIZE)-1)>>12))$fatal(1,"AW crosses 4K");
            wr_addr<=AWADDR;wr_left<=AWLEN+1;wr_size<=AWSIZE;wr_busy<=1;BID<=AWID;
        end
        if(WVALID && WREADY)begin
            if(WLAST!==(wr_left==1))$fatal(1,"WLAST disagrees with AWLEN");
            for(lane=0;lane<DATA_WIDTH/8;lane=lane+1)if(WSTRB[lane])begin
                if(lane<(wr_addr%(DATA_WIDTH/8)) || lane>=(wr_addr%(DATA_WIDTH/8))+(64'd1<<wr_size))
                    $fatal(1,"WSTRB outside the current AXI transfer lanes");
                if(!allowed((wr_addr/(DATA_WIDTH/8))*(DATA_WIDTH/8)+lane,1))$fatal(1,"write outside allowed bytes");
                idx=((wr_addr-BASE)/(DATA_WIDTH/8))*(DATA_WIDTH/8)+lane;
                mem[idx/4][(idx%4)*8+:8]<=WDATA[lane*8+:8];
            end
            write_beats<=write_beats+1;wr_left<=wr_left-1;wr_addr<=wr_addr+(64'd1<<wr_size);
            if(wr_left==1)begin wr_busy<=0;b_pending<=1;delay_b<=5+cycle%13;end
        end
    end
end
reg ar_stalled=0,aw_stalled=0,w_stalled=0;
reg [76+ID_WIDTH:0] saved_ar,saved_aw;
reg [DATA_WIDTH+DATA_WIDTH/8:0] saved_w;
always @(posedge clk)if(resetn)begin
    if(ar_stalled && (!ARVALID || saved_ar!=={ARADDR,ARLEN,ARSIZE,ARBURST,ARID}))$fatal(1,"AR changed during stall");
    if(aw_stalled && (!AWVALID || saved_aw!=={AWADDR,AWLEN,AWSIZE,AWBURST,AWID}))$fatal(1,"AW changed during stall");
    if(w_stalled && (!WVALID || saved_w!=={WDATA,WSTRB,WLAST}))$fatal(1,"W changed during stall");
    ar_stalled<=ARVALID && !ARREADY;aw_stalled<=AWVALID && !AWREADY;w_stalled<=WVALID && !WREADY;
    saved_ar<={ARADDR,ARLEN,ARSIZE,ARBURST,ARID};saved_aw<={AWADDR,AWLEN,AWSIZE,AWBURST,AWID};saved_w<={WDATA,WSTRB,WLAST};
end
endmodule
