`timescale 1ns/1ps
module gdn_memory_selftest;
reg clk=0,resetn=0;
always #5 clk=~clk;
reg [63:0] ARADDR=0,AWADDR=0;
reg [7:0] ARLEN=0,AWLEN=0;
reg [2:0] ARSIZE=0,AWSIZE=0;
reg [5:0] ARID=0,AWID=0;
reg ARVALID=0,RREADY=0,AWVALID=0,WVALID=0,WLAST=1,BREADY=0;
wire ARREADY,RVALID,RLAST,AWREADY,WREADY,BVALID;
wire [127:0] RDATA;
reg [127:0] WDATA=0;
reg [15:0] WSTRB=0;
wire [5:0] RID,BID;
wire [1:0] RRESP,BRESP;
gdn_axi_bounded_memory #(.BASE(0),.BYTES(4096),.DATA_WIDTH(128),.ID_WIDTH(6),
 .R0(0),.N0(64),.R1(64),.N1(210),.WR1(1)) mem(
 .clk(clk),.resetn(resetn),.ARADDR(ARADDR),.ARLEN(ARLEN),.ARSIZE(ARSIZE),.ARBURST(2'b01),.ARID(ARID),
 .ARVALID(ARVALID),.ARREADY(ARREADY),.RDATA(RDATA),.RLAST(RLAST),.RID(RID),.RRESP(RRESP),.RVALID(RVALID),.RREADY(RREADY),
 .AWADDR(AWADDR),.AWLEN(AWLEN),.AWSIZE(AWSIZE),.AWBURST(2'b01),.AWID(AWID),.AWVALID(AWVALID),.AWREADY(AWREADY),
 .WDATA(WDATA),.WSTRB(WSTRB),.WLAST(WLAST),.WVALID(WVALID),.WREADY(WREADY),.BID(BID),.BRESP(BRESP),.BVALID(BVALID),.BREADY(BREADY));
task automatic read_one(input [63:0] addr,input [2:0] size,input [127:0] expected);
begin
 @(negedge clk);ARADDR=addr;ARSIZE=size;ARID=6'h29;ARVALID=1;
 do @(posedge clk);while(ARREADY!==1'b1);
 @(negedge clk);ARVALID=0;
 do @(posedge clk);while(RVALID!==1'b1);
 if(RDATA!==expected || RID!==6'h29 || RLAST!==1 || RRESP!==0)$fatal(1,"128-bit read/lane/ID mismatch");
 repeat(5)begin @(posedge clk);if(RDATA!==expected || !RVALID)$fatal(1,"R changed while stalled");end
 @(negedge clk);RREADY=1;@(posedge clk);@(negedge clk);RREADY=0;
end
endtask
task automatic write_one(input [63:0] addr,input [127:0] data,input [15:0] strobe);
begin
 @(negedge clk);AWADDR=addr;AWSIZE=1;AWID=6'h35;AWVALID=1;
 do @(posedge clk);while(AWREADY!==1'b1);
 @(negedge clk);AWVALID=0;WDATA=data;WSTRB=strobe;WVALID=1;
 do @(posedge clk);while(WREADY!==1'b1);
 @(negedge clk);WVALID=0;
 do @(posedge clk);while(BVALID!==1'b1);
 if(BID!==6'h35 || BRESP!==0)$fatal(1,"write ID/response");
 repeat(7)begin @(posedge clk);if(!BVALID || BID!==6'h35)$fatal(1,"B changed while stalled");end
 @(negedge clk);BREADY=1;@(posedge clk);@(negedge clk);BREADY=0;
end
endtask
initial begin
 for(integer i=0;i<1024;i=i+1)mem.mem[i]=32'h5a395a39;
 mem.mem[4]=32'h11223344;mem.mem[5]=32'h55667788;mem.mem[6]=32'h99aabbcc;mem.mem[7]=32'hddeeff00;
 repeat(10)@(negedge clk);resetn=1;
 read_one(16,4,128'hddeeff0099aabbcc5566778811223344);
 write_one(66,128'h000000000000000000000000beef0000,16'h000c);
 if(mem.mem[16]!==32'hbeef5a39)$fatal(1,"narrow write lane");
 read_one(66,1,128'h5a395a395a395a395a395a39beef5a39);
 write_one(272,128'h1234,16'h0003);
 if(mem.mem[68]!==32'h5a391234 || mem.mem[69]!==32'h5a395a39)$fatal(1,"payload tail guard");
 read_one(272,4,128'h5a395a395a395a395a395a395a391234);
 $display("GDN_MEMORY_SELFTEST_PASS data_width=128 id_width=6 narrow_strobes=2 tail_padding=PASS stalled_RB=PASS");$finish;
end
initial begin #100000;$fatal(1,"memory model timeout");end
endmodule
