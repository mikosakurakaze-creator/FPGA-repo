`timescale 1ns/1ps
module gdn_frame_axi_test;
logic  ap_clk;
logic  ap_rst_n;
logic  m_axi_feature_mem_AWVALID;
logic  m_axi_feature_mem_AWREADY;
logic [63:0] m_axi_feature_mem_AWADDR;
logic [0:0] m_axi_feature_mem_AWID;
logic [7:0] m_axi_feature_mem_AWLEN;
logic [2:0] m_axi_feature_mem_AWSIZE;
logic [1:0] m_axi_feature_mem_AWBURST;
logic [1:0] m_axi_feature_mem_AWLOCK;
logic [3:0] m_axi_feature_mem_AWCACHE;
logic [2:0] m_axi_feature_mem_AWPROT;
logic [3:0] m_axi_feature_mem_AWQOS;
logic [3:0] m_axi_feature_mem_AWREGION;
logic [0:0] m_axi_feature_mem_AWUSER;
logic  m_axi_feature_mem_WVALID;
logic  m_axi_feature_mem_WREADY;
logic [31:0] m_axi_feature_mem_WDATA;
logic [3:0] m_axi_feature_mem_WSTRB;
logic  m_axi_feature_mem_WLAST;
logic [0:0] m_axi_feature_mem_WID;
logic [0:0] m_axi_feature_mem_WUSER;
logic  m_axi_feature_mem_ARVALID;
logic  m_axi_feature_mem_ARREADY;
logic [63:0] m_axi_feature_mem_ARADDR;
logic [0:0] m_axi_feature_mem_ARID;
logic [7:0] m_axi_feature_mem_ARLEN;
logic [2:0] m_axi_feature_mem_ARSIZE;
logic [1:0] m_axi_feature_mem_ARBURST;
logic [1:0] m_axi_feature_mem_ARLOCK;
logic [3:0] m_axi_feature_mem_ARCACHE;
logic [2:0] m_axi_feature_mem_ARPROT;
logic [3:0] m_axi_feature_mem_ARQOS;
logic [3:0] m_axi_feature_mem_ARREGION;
logic [0:0] m_axi_feature_mem_ARUSER;
logic  m_axi_feature_mem_RVALID;
logic  m_axi_feature_mem_RREADY;
logic [31:0] m_axi_feature_mem_RDATA;
logic  m_axi_feature_mem_RLAST;
logic [0:0] m_axi_feature_mem_RID;
logic [0:0] m_axi_feature_mem_RUSER;
logic [1:0] m_axi_feature_mem_RRESP;
logic  m_axi_feature_mem_BVALID;
logic  m_axi_feature_mem_BREADY;
logic [1:0] m_axi_feature_mem_BRESP;
logic [0:0] m_axi_feature_mem_BID;
logic [0:0] m_axi_feature_mem_BUSER;
logic  m_axi_parameter_mem_AWVALID;
logic  m_axi_parameter_mem_AWREADY;
logic [63:0] m_axi_parameter_mem_AWADDR;
logic [0:0] m_axi_parameter_mem_AWID;
logic [7:0] m_axi_parameter_mem_AWLEN;
logic [2:0] m_axi_parameter_mem_AWSIZE;
logic [1:0] m_axi_parameter_mem_AWBURST;
logic [1:0] m_axi_parameter_mem_AWLOCK;
logic [3:0] m_axi_parameter_mem_AWCACHE;
logic [2:0] m_axi_parameter_mem_AWPROT;
logic [3:0] m_axi_parameter_mem_AWQOS;
logic [3:0] m_axi_parameter_mem_AWREGION;
logic [0:0] m_axi_parameter_mem_AWUSER;
logic  m_axi_parameter_mem_WVALID;
logic  m_axi_parameter_mem_WREADY;
logic [31:0] m_axi_parameter_mem_WDATA;
logic [3:0] m_axi_parameter_mem_WSTRB;
logic  m_axi_parameter_mem_WLAST;
logic [0:0] m_axi_parameter_mem_WID;
logic [0:0] m_axi_parameter_mem_WUSER;
logic  m_axi_parameter_mem_ARVALID;
logic  m_axi_parameter_mem_ARREADY;
logic [63:0] m_axi_parameter_mem_ARADDR;
logic [0:0] m_axi_parameter_mem_ARID;
logic [7:0] m_axi_parameter_mem_ARLEN;
logic [2:0] m_axi_parameter_mem_ARSIZE;
logic [1:0] m_axi_parameter_mem_ARBURST;
logic [1:0] m_axi_parameter_mem_ARLOCK;
logic [3:0] m_axi_parameter_mem_ARCACHE;
logic [2:0] m_axi_parameter_mem_ARPROT;
logic [3:0] m_axi_parameter_mem_ARQOS;
logic [3:0] m_axi_parameter_mem_ARREGION;
logic [0:0] m_axi_parameter_mem_ARUSER;
logic  m_axi_parameter_mem_RVALID;
logic  m_axi_parameter_mem_RREADY;
logic [31:0] m_axi_parameter_mem_RDATA;
logic  m_axi_parameter_mem_RLAST;
logic [0:0] m_axi_parameter_mem_RID;
logic [0:0] m_axi_parameter_mem_RUSER;
logic [1:0] m_axi_parameter_mem_RRESP;
logic  m_axi_parameter_mem_BVALID;
logic  m_axi_parameter_mem_BREADY;
logic [1:0] m_axi_parameter_mem_BRESP;
logic [0:0] m_axi_parameter_mem_BID;
logic [0:0] m_axi_parameter_mem_BUSER;
logic  s_axi_control_AWVALID;
logic  s_axi_control_AWREADY;
logic [7:0] s_axi_control_AWADDR;
logic  s_axi_control_WVALID;
logic  s_axi_control_WREADY;
logic [31:0] s_axi_control_WDATA;
logic [3:0] s_axi_control_WSTRB;
logic  s_axi_control_ARVALID;
logic  s_axi_control_ARREADY;
logic [7:0] s_axi_control_ARADDR;
logic  s_axi_control_RVALID;
logic  s_axi_control_RREADY;
logic [31:0] s_axi_control_RDATA;
logic [1:0] s_axi_control_RRESP;
logic  s_axi_control_BVALID;
logic  s_axi_control_BREADY;
logic [1:0] s_axi_control_BRESP;
logic  interrupt;
griddehaze_frame_top dut(.ap_clk(ap_clk),
.ap_rst_n(ap_rst_n),
.m_axi_feature_mem_AWVALID(m_axi_feature_mem_AWVALID),
.m_axi_feature_mem_AWREADY(m_axi_feature_mem_AWREADY),
.m_axi_feature_mem_AWADDR(m_axi_feature_mem_AWADDR),
.m_axi_feature_mem_AWID(m_axi_feature_mem_AWID),
.m_axi_feature_mem_AWLEN(m_axi_feature_mem_AWLEN),
.m_axi_feature_mem_AWSIZE(m_axi_feature_mem_AWSIZE),
.m_axi_feature_mem_AWBURST(m_axi_feature_mem_AWBURST),
.m_axi_feature_mem_AWLOCK(m_axi_feature_mem_AWLOCK),
.m_axi_feature_mem_AWCACHE(m_axi_feature_mem_AWCACHE),
.m_axi_feature_mem_AWPROT(m_axi_feature_mem_AWPROT),
.m_axi_feature_mem_AWQOS(m_axi_feature_mem_AWQOS),
.m_axi_feature_mem_AWREGION(m_axi_feature_mem_AWREGION),
.m_axi_feature_mem_AWUSER(m_axi_feature_mem_AWUSER),
.m_axi_feature_mem_WVALID(m_axi_feature_mem_WVALID),
.m_axi_feature_mem_WREADY(m_axi_feature_mem_WREADY),
.m_axi_feature_mem_WDATA(m_axi_feature_mem_WDATA),
.m_axi_feature_mem_WSTRB(m_axi_feature_mem_WSTRB),
.m_axi_feature_mem_WLAST(m_axi_feature_mem_WLAST),
.m_axi_feature_mem_WID(m_axi_feature_mem_WID),
.m_axi_feature_mem_WUSER(m_axi_feature_mem_WUSER),
.m_axi_feature_mem_ARVALID(m_axi_feature_mem_ARVALID),
.m_axi_feature_mem_ARREADY(m_axi_feature_mem_ARREADY),
.m_axi_feature_mem_ARADDR(m_axi_feature_mem_ARADDR),
.m_axi_feature_mem_ARID(m_axi_feature_mem_ARID),
.m_axi_feature_mem_ARLEN(m_axi_feature_mem_ARLEN),
.m_axi_feature_mem_ARSIZE(m_axi_feature_mem_ARSIZE),
.m_axi_feature_mem_ARBURST(m_axi_feature_mem_ARBURST),
.m_axi_feature_mem_ARLOCK(m_axi_feature_mem_ARLOCK),
.m_axi_feature_mem_ARCACHE(m_axi_feature_mem_ARCACHE),
.m_axi_feature_mem_ARPROT(m_axi_feature_mem_ARPROT),
.m_axi_feature_mem_ARQOS(m_axi_feature_mem_ARQOS),
.m_axi_feature_mem_ARREGION(m_axi_feature_mem_ARREGION),
.m_axi_feature_mem_ARUSER(m_axi_feature_mem_ARUSER),
.m_axi_feature_mem_RVALID(m_axi_feature_mem_RVALID),
.m_axi_feature_mem_RREADY(m_axi_feature_mem_RREADY),
.m_axi_feature_mem_RDATA(m_axi_feature_mem_RDATA),
.m_axi_feature_mem_RLAST(m_axi_feature_mem_RLAST),
.m_axi_feature_mem_RID(m_axi_feature_mem_RID),
.m_axi_feature_mem_RUSER(m_axi_feature_mem_RUSER),
.m_axi_feature_mem_RRESP(m_axi_feature_mem_RRESP),
.m_axi_feature_mem_BVALID(m_axi_feature_mem_BVALID),
.m_axi_feature_mem_BREADY(m_axi_feature_mem_BREADY),
.m_axi_feature_mem_BRESP(m_axi_feature_mem_BRESP),
.m_axi_feature_mem_BID(m_axi_feature_mem_BID),
.m_axi_feature_mem_BUSER(m_axi_feature_mem_BUSER),
.m_axi_parameter_mem_AWVALID(m_axi_parameter_mem_AWVALID),
.m_axi_parameter_mem_AWREADY(m_axi_parameter_mem_AWREADY),
.m_axi_parameter_mem_AWADDR(m_axi_parameter_mem_AWADDR),
.m_axi_parameter_mem_AWID(m_axi_parameter_mem_AWID),
.m_axi_parameter_mem_AWLEN(m_axi_parameter_mem_AWLEN),
.m_axi_parameter_mem_AWSIZE(m_axi_parameter_mem_AWSIZE),
.m_axi_parameter_mem_AWBURST(m_axi_parameter_mem_AWBURST),
.m_axi_parameter_mem_AWLOCK(m_axi_parameter_mem_AWLOCK),
.m_axi_parameter_mem_AWCACHE(m_axi_parameter_mem_AWCACHE),
.m_axi_parameter_mem_AWPROT(m_axi_parameter_mem_AWPROT),
.m_axi_parameter_mem_AWQOS(m_axi_parameter_mem_AWQOS),
.m_axi_parameter_mem_AWREGION(m_axi_parameter_mem_AWREGION),
.m_axi_parameter_mem_AWUSER(m_axi_parameter_mem_AWUSER),
.m_axi_parameter_mem_WVALID(m_axi_parameter_mem_WVALID),
.m_axi_parameter_mem_WREADY(m_axi_parameter_mem_WREADY),
.m_axi_parameter_mem_WDATA(m_axi_parameter_mem_WDATA),
.m_axi_parameter_mem_WSTRB(m_axi_parameter_mem_WSTRB),
.m_axi_parameter_mem_WLAST(m_axi_parameter_mem_WLAST),
.m_axi_parameter_mem_WID(m_axi_parameter_mem_WID),
.m_axi_parameter_mem_WUSER(m_axi_parameter_mem_WUSER),
.m_axi_parameter_mem_ARVALID(m_axi_parameter_mem_ARVALID),
.m_axi_parameter_mem_ARREADY(m_axi_parameter_mem_ARREADY),
.m_axi_parameter_mem_ARADDR(m_axi_parameter_mem_ARADDR),
.m_axi_parameter_mem_ARID(m_axi_parameter_mem_ARID),
.m_axi_parameter_mem_ARLEN(m_axi_parameter_mem_ARLEN),
.m_axi_parameter_mem_ARSIZE(m_axi_parameter_mem_ARSIZE),
.m_axi_parameter_mem_ARBURST(m_axi_parameter_mem_ARBURST),
.m_axi_parameter_mem_ARLOCK(m_axi_parameter_mem_ARLOCK),
.m_axi_parameter_mem_ARCACHE(m_axi_parameter_mem_ARCACHE),
.m_axi_parameter_mem_ARPROT(m_axi_parameter_mem_ARPROT),
.m_axi_parameter_mem_ARQOS(m_axi_parameter_mem_ARQOS),
.m_axi_parameter_mem_ARREGION(m_axi_parameter_mem_ARREGION),
.m_axi_parameter_mem_ARUSER(m_axi_parameter_mem_ARUSER),
.m_axi_parameter_mem_RVALID(m_axi_parameter_mem_RVALID),
.m_axi_parameter_mem_RREADY(m_axi_parameter_mem_RREADY),
.m_axi_parameter_mem_RDATA(m_axi_parameter_mem_RDATA),
.m_axi_parameter_mem_RLAST(m_axi_parameter_mem_RLAST),
.m_axi_parameter_mem_RID(m_axi_parameter_mem_RID),
.m_axi_parameter_mem_RUSER(m_axi_parameter_mem_RUSER),
.m_axi_parameter_mem_RRESP(m_axi_parameter_mem_RRESP),
.m_axi_parameter_mem_BVALID(m_axi_parameter_mem_BVALID),
.m_axi_parameter_mem_BREADY(m_axi_parameter_mem_BREADY),
.m_axi_parameter_mem_BRESP(m_axi_parameter_mem_BRESP),
.m_axi_parameter_mem_BID(m_axi_parameter_mem_BID),
.m_axi_parameter_mem_BUSER(m_axi_parameter_mem_BUSER),
.s_axi_control_AWVALID(s_axi_control_AWVALID),
.s_axi_control_AWREADY(s_axi_control_AWREADY),
.s_axi_control_AWADDR(s_axi_control_AWADDR),
.s_axi_control_WVALID(s_axi_control_WVALID),
.s_axi_control_WREADY(s_axi_control_WREADY),
.s_axi_control_WDATA(s_axi_control_WDATA),
.s_axi_control_WSTRB(s_axi_control_WSTRB),
.s_axi_control_ARVALID(s_axi_control_ARVALID),
.s_axi_control_ARREADY(s_axi_control_ARREADY),
.s_axi_control_ARADDR(s_axi_control_ARADDR),
.s_axi_control_RVALID(s_axi_control_RVALID),
.s_axi_control_RREADY(s_axi_control_RREADY),
.s_axi_control_RDATA(s_axi_control_RDATA),
.s_axi_control_RRESP(s_axi_control_RRESP),
.s_axi_control_BVALID(s_axi_control_BVALID),
.s_axi_control_BREADY(s_axi_control_BREADY),
.s_axi_control_BRESP(s_axi_control_BRESP),
.interrupt(interrupt));
gdn_axi_bounded_memory #(.BASE(64'h10000000),.BYTES(823296),.DATA_WIDTH(32),.ID_WIDTH(1),.R0(4096),.N0(9306),.R1(16384),.N1(9306),.R2(28672),.N2(794240),.WR1(1),.WR2(1)) feature(.clk(ap_clk),.resetn(ap_rst_n),.ARADDR(m_axi_feature_mem_ARADDR),.ARLEN(m_axi_feature_mem_ARLEN),.ARSIZE(m_axi_feature_mem_ARSIZE),.ARBURST(m_axi_feature_mem_ARBURST),.ARID(m_axi_feature_mem_ARID),.ARVALID(m_axi_feature_mem_ARVALID),.ARREADY(m_axi_feature_mem_ARREADY),.RDATA(m_axi_feature_mem_RDATA),.RLAST(m_axi_feature_mem_RLAST),.RID(m_axi_feature_mem_RID),.RRESP(m_axi_feature_mem_RRESP),.RVALID(m_axi_feature_mem_RVALID),.RREADY(m_axi_feature_mem_RREADY),.AWADDR(m_axi_feature_mem_AWADDR),.AWLEN(m_axi_feature_mem_AWLEN),.AWSIZE(m_axi_feature_mem_AWSIZE),.AWBURST(m_axi_feature_mem_AWBURST),.AWID(m_axi_feature_mem_AWID),.AWVALID(m_axi_feature_mem_AWVALID),.AWREADY(m_axi_feature_mem_AWREADY),.WDATA(m_axi_feature_mem_WDATA),.WSTRB(m_axi_feature_mem_WSTRB),.WLAST(m_axi_feature_mem_WLAST),.WVALID(m_axi_feature_mem_WVALID),.WREADY(m_axi_feature_mem_WREADY),.BID(m_axi_feature_mem_BID),.BRESP(m_axi_feature_mem_BRESP),.BVALID(m_axi_feature_mem_BVALID),.BREADY(m_axi_feature_mem_BREADY));
assign m_axi_feature_mem_RUSER=0,m_axi_feature_mem_BUSER=0;
gdn_axi_bounded_memory #(.BASE(64'h20000000),.BYTES(2097152),.DATA_WIDTH(32),.ID_WIDTH(1),.R0(0),.N0(1933120),.R1(1966080),.N1(1344),.R2(0),.N2(0),.WR1(0),.WR2(0)) model_memory(.clk(ap_clk),.resetn(ap_rst_n),.ARADDR(m_axi_parameter_mem_ARADDR),.ARLEN(m_axi_parameter_mem_ARLEN),.ARSIZE(m_axi_parameter_mem_ARSIZE),.ARBURST(m_axi_parameter_mem_ARBURST),.ARID(m_axi_parameter_mem_ARID),.ARVALID(m_axi_parameter_mem_ARVALID),.ARREADY(m_axi_parameter_mem_ARREADY),.RDATA(m_axi_parameter_mem_RDATA),.RLAST(m_axi_parameter_mem_RLAST),.RID(m_axi_parameter_mem_RID),.RRESP(m_axi_parameter_mem_RRESP),.RVALID(m_axi_parameter_mem_RVALID),.RREADY(m_axi_parameter_mem_RREADY),.AWADDR(m_axi_parameter_mem_AWADDR),.AWLEN(m_axi_parameter_mem_AWLEN),.AWSIZE(m_axi_parameter_mem_AWSIZE),.AWBURST(m_axi_parameter_mem_AWBURST),.AWID(m_axi_parameter_mem_AWID),.AWVALID(m_axi_parameter_mem_AWVALID),.AWREADY(m_axi_parameter_mem_AWREADY),.WDATA(m_axi_parameter_mem_WDATA),.WSTRB(m_axi_parameter_mem_WSTRB),.WLAST(m_axi_parameter_mem_WLAST),.WVALID(m_axi_parameter_mem_WVALID),.WREADY(m_axi_parameter_mem_WREADY),.BID(m_axi_parameter_mem_BID),.BRESP(m_axi_parameter_mem_BRESP),.BVALID(m_axi_parameter_mem_BVALID),.BREADY(m_axi_parameter_mem_BREADY));
assign m_axi_parameter_mem_RUSER=0,m_axi_parameter_mem_BUSER=0;
localparam integer IMAGE_BYTES=9306,SCRATCH_BYTES=794240;
integer cycle=0,observed=0,active=0,pass=0,negative_mode=0;
reg [15:0] golden[0:6872006];
reg [31:0] node_start[0:319],node_bytes[0:319],node_at[0:319];
always #5 ap_clk=~ap_clk;
always @(posedge ap_clk)cycle<=cycle+1;
always @(negedge ap_clk)if(ap_rst_n && active && cycle%1000000==0)
    $display("GDN_AXI_PROGRESS cycle=%0d feature_reads=%0d parameter_reads=%0d writes=%0d",cycle,feature.read_beats,model_memory.read_beats,feature.write_beats);
function automatic [15:0] feature_scalar(input integer index,input integer scalar_index);
integer byte_index;
begin
    byte_index=node_at[index]+scalar_index*2;
    feature_scalar=feature.mem[byte_index/4]>>((byte_index%4)*8);
end
endfunction
// HLS removes intermediate stores to a nonvolatile output reference. The CSR
// publishes 1 then the final value; it is not a per-node progress channel.
// Observe the exact exported graph-loop retirement state for this revision.
`ifndef GDN_NETLIST
always @(negedge ap_clk)if(ap_rst_n && active &&
  ((observed==0 && dut.completed_nodes_ap_vld && dut.completed_nodes==1) || dut.ap_CS_fsm_state141))begin : observe
    integer i,n,f;
    reg [15:0] actual;
    n=dut.ap_CS_fsm_state141 ? dut.i_2_fu_352 : 0;
    if(n!=observed)$fatal(1,"node completion order got=%0d expected=%0d",n,observed);
    for(i=0;i<node_bytes[n]/2;i=i+1)begin
        actual=feature_scalar(n,i);
        if(actual!==golden[node_start[n]+i])$fatal(1,"node mismatch pass=%0d node=%0d i=%0d got=%h expected=%h",pass,n,i,actual,golden[node_start[n]+i]);
    end
    if(pass==0)begin
        f=$fopen($sformatf("node_%0d.raw",n),"wb");
        if(!f)$fatal(1,"cannot open node output");
        for(i=0;i<node_bytes[n]/2;i=i+1)begin
            actual=feature_scalar(n,i);$fwrite(f,"%c%c",actual[7:0],actual[15:8]);
        end
        $fclose(f);
    end
    observed=observed+1;
    if(observed%32==0)$display("GDN_RTL_PROGRESS pass=%0d nodes=%0d cycles=%0d",pass,observed,cycle);
end
always @(posedge ap_clk)if(ap_rst_n && active && dut.ap_done)begin
    if(feature.wr_busy || feature.b_pending || (m_axi_feature_mem_BVALID && !m_axi_feature_mem_BREADY) ||
       feature.rd_busy || model_memory.rd_busy)$fatal(1,"done before AXI drained");
end
`endif
task automatic csr_write(input [7:0] addr,input [31:0] data);
integer started;
begin
    started=cycle;
    @(negedge ap_clk);s_axi_control_AWADDR=addr;s_axi_control_AWVALID=1;
    do begin @(posedge ap_clk);if(cycle-started>10000)$fatal(1,"CSR AW timeout addr=%h",addr);end while(s_axi_control_AWREADY!==1'b1);
    @(negedge ap_clk);s_axi_control_AWVALID=0;s_axi_control_WDATA=data;s_axi_control_WVALID=1;
    do begin @(posedge ap_clk);if(cycle-started>10000)$fatal(1,"CSR W timeout addr=%h",addr);end while(s_axi_control_WREADY!==1'b1);
    @(negedge ap_clk);s_axi_control_WVALID=0;
    do begin @(posedge ap_clk);if(cycle-started>10000)$fatal(1,"CSR B timeout addr=%h",addr);end while(s_axi_control_BVALID!==1'b1);
    if(s_axi_control_BRESP!==0)$fatal(1,"CSR write response");
end
endtask
task automatic csr_read(input [7:0] addr,output [31:0] data);
integer started;
begin
    started=cycle;
    @(negedge ap_clk);s_axi_control_ARADDR=addr;s_axi_control_ARVALID=1;
    do begin @(posedge ap_clk);if(cycle-started>10000)$fatal(1,"CSR AR timeout addr=%h",addr);end while(s_axi_control_ARREADY!==1'b1);
    @(negedge ap_clk);s_axi_control_ARVALID=0;
    do begin @(posedge ap_clk);if(cycle-started>10000)$fatal(1,"CSR R timeout addr=%h",addr);end while(s_axi_control_RVALID!==1'b1);
    if(s_axi_control_RRESP!==0)$fatal(1,"CSR read response");
    data=s_axi_control_RDATA;
end
endtask
task automatic execute(input integer bad);
integer start_cycle,i,fd,previous_reads,previous_parameters,previous_writes;reg [31:0] ctrl,ret;
begin
    observed=0;active=1;
    previous_reads=feature.read_beats;previous_parameters=model_memory.read_beats;previous_writes=feature.write_beats;
    for(i=0;i<(IMAGE_BYTES+3)/4;i=i+1)feature.mem[(16384/4)+i]=32'h39a539a5;
    csr_write('h8c,bad?0:32'h47444e31);
    start_cycle=cycle;csr_write(0,1);ctrl=0;
    while(!(ctrl&2))begin
        repeat(64)@(posedge ap_clk);csr_read(0,ctrl);
        if(cycle-start_cycle>500000000)$fatal(1,"frame timeout nodes=%0d",observed);
    end
    csr_read('h10,ret);
    if(bad)begin
        if(ret!==1 || observed!=0)$fatal(1,"invalid descriptor did not fail early");
        if(feature.read_beats!=previous_reads || model_memory.read_beats!=previous_parameters || feature.write_beats!=previous_writes)
            $fatal(1,"invalid model caused DDR traffic");
        $display("GDN_RTL_BAD_MODEL_PASS");
    end else begin
        if(ret!==0)$fatal(1,"completion status=%h",ret);
`ifndef GDN_NETLIST
        if(observed!=320)$fatal(1,"completion nodes=%0d",observed);
`endif
        if(feature.wr_busy || feature.b_pending || m_axi_feature_mem_BVALID || feature.rd_busy || model_memory.rd_busy)
            $fatal(1,"CSR done before AXI drained");
        csr_read('h9c,ret);if(ret!==320)$fatal(1,"CSR completed nodes");
        for(i=0;i<IMAGE_BYTES/2;i=i+1)
            if(feature_scalar(319,i)!==golden[node_start[319]+i])$fatal(1,"final output mismatch");
        fd=$fopen($sformatf("output_%0d.raw",pass),"wb");
        for(i=0;i<IMAGE_BYTES/2;i=i+1)$fwrite(fd,"%c%c",feature.mem[(16384+2*i)/4]>>(((2*i)%4)*8),feature.mem[(16384+2*i)/4]>>((((2*i)%4)+1)*8));
        $fclose(fd);
        $display("GDN_RTL_FRAME_PASS pass=%0d completed_csr=320 cycles=%0d read_beats=%0d parameter_beats=%0d writes=%0d",pass,cycle-start_cycle,feature.read_beats,model_memory.read_beats,feature.write_beats);
    end
    active=0;
end
endtask
initial begin : main
    integer i;
    ap_clk=0;ap_rst_n=0;s_axi_control_AWVALID=0;s_axi_control_WVALID=0;
    s_axi_control_ARVALID=0;s_axi_control_BREADY=1;s_axi_control_RREADY=1;s_axi_control_WSTRB=15;
    for(i=0;i<205824;i=i+1)feature.mem[i]=32'h5a395a39;
    for(i=0;i<524288;i=i+1)model_memory.mem[i]=32'h5a395a39;
    $readmemh("feature.hex",feature.mem);$readmemh("parameter.hex",model_memory.mem);
    $readmemh("golden.hex",golden);$readmemh("node_start.hex",node_start);
    $readmemh("node_bytes.hex",node_bytes);$readmemh("node_at.hex",node_at);
    repeat(10)@(negedge ap_clk);ap_rst_n=1;repeat(10)@(negedge ap_clk);
    csr_write('h18,32'h10001000);csr_write('h1c,0);
    csr_write('h24,32'h10004000);csr_write('h28,0);
    csr_write('h30,32'h10007000);csr_write('h34,0);
    csr_write('h3c,32'h20000000);csr_write('h40,0);
    csr_write('h48,32'h201e0000);csr_write('h4c,0);
    csr_write('h54,IMAGE_BYTES);csr_write('h5c,IMAGE_BYTES);csr_write('h64,SCRATCH_BYTES);
    csr_write('h6c,1933120);csr_write('h74,1344);csr_write('h7c,33);csr_write('h84,47);
    csr_write('h94,32'h00010000);
    execute(1);
    pass=0;execute(0);pass=1;execute(0);
`ifdef GDN_NETLIST
    $display("GDN_RTL_SEQUENCE_PASS frames=2 scope=netlist_final_output bad_model=1");
`else
    $display("GDN_RTL_SEQUENCE_PASS frames=2 scope=all_320_nodes bad_model=1");
`endif
    $finish;
end
// Cycle budget covers both cold and warm frames. A fixed small-vector time
// delay used to terminate larger cases before their per-frame watchdog.
initial begin wait(cycle>=1001000000);$fatal(1,"global timeout");end
endmodule
