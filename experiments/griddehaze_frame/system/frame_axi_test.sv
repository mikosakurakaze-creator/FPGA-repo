`timescale 1ns/1ps
module gdn_frame_axi_test;
@PORTS@
griddehaze_frame_top dut(@CONNECTIONS@);
@MEMORIES@
localparam integer IMAGE_BYTES=@IMAGE_BYTES@,SCRATCH_BYTES=@SCRATCH_BYTES@;
integer cycle=0,observed=0,active=0,pass=0,negative_mode=0;
reg [15:0] golden[0:@GOLDEN_LAST@];
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
    for(i=0;i<(IMAGE_BYTES+3)/4;i=i+1)feature.mem[(@OUT_OFFSET@/4)+i]=32'h39a539a5;
    csr_write('h8c,bad?0:32'h47444e31);
    start_cycle=cycle;csr_write(0,1);ctrl=0;
    while(!(ctrl&2))begin
        repeat(64)@(posedge ap_clk);csr_read(0,ctrl);
        if(cycle-start_cycle>@FRAME_CYCLES@)$fatal(1,"frame timeout nodes=%0d",observed);
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
        for(i=0;i<IMAGE_BYTES/2;i=i+1)$fwrite(fd,"%c%c",feature.mem[(@OUT_OFFSET@+2*i)/4]>>(((2*i)%4)*8),feature.mem[(@OUT_OFFSET@+2*i)/4]>>((((2*i)%4)+1)*8));
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
    for(i=0;i<@FEATURE_WORDS@;i=i+1)feature.mem[i]=32'h5a395a39;
    for(i=0;i<@PARAMETER_WORDS@;i=i+1)model_memory.mem[i]=32'h5a395a39;
    $readmemh("feature.hex",feature.mem);$readmemh("parameter.hex",model_memory.mem);
    $readmemh("golden.hex",golden);$readmemh("node_start.hex",node_start);
    $readmemh("node_bytes.hex",node_bytes);$readmemh("node_at.hex",node_at);
    repeat(10)@(negedge ap_clk);ap_rst_n=1;repeat(10)@(negedge ap_clk);
    csr_write('h18,32'h@INPUT_BASE@);csr_write('h1c,0);
    csr_write('h24,32'h@OUT_BASE@);csr_write('h28,0);
    csr_write('h30,32'h@SCRATCH_BASE@);csr_write('h34,0);
    csr_write('h3c,32'h@PARAMETER_BASE@);csr_write('h40,0);
    csr_write('h48,32'h@LAYOUT_BASE@);csr_write('h4c,0);
    csr_write('h54,IMAGE_BYTES);csr_write('h5c,IMAGE_BYTES);csr_write('h64,SCRATCH_BYTES);
    csr_write('h6c,@PARAMETER_BYTES@);csr_write('h74,1344);csr_write('h7c,@HEIGHT@);csr_write('h84,@WIDTH@);
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
initial begin wait(cycle>=@TOTAL_CYCLES@);$fatal(1,"global timeout");end
endmodule
