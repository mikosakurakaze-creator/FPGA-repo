`timescale 1ns/1ps
module ddr_v2_protocol_tb;
  reg clk=0;always #5 clk=~clk;reg rst_n=0;
  reg [48:0] araddr[0:3],awaddr[0:3];reg [7:0] arlen[0:3],awlen[0:3];
  reg [2:0] arsize[0:3],awsize[0:3];reg [1:0] arburst[0:3],awburst[0:3];
  reg [5:0] arid[0:3],awid[0:3];reg [3:0] arvalid=0,awvalid=0,wvalid=0,wlast=0,rready=0,bready=0;
  wire [3:0] arready,awready,wready,rvalid,rlast,bvalid;wire [127:0] rdata[0:3];wire [5:0] rid[0:3],bid[0:3];
  wire [1:0] rresp[0:3],bresp[0:3];reg [127:0] wdata[0:3];reg [15:0] wstrb[0:3];
  shared_axi_ddr #(.WORDS(2048)) dut(.*);
  reg [127:0] expected[0:2047];
  reg [48:0] read_addresses[0:3][0:255];integer read_lengths[0:3][0:255];
  reg [5:0] read_ids[0:3][0:255],write_ids[0:3][0:255];
  integer ar_count[0:3],aw_count[0:3],read_count[0:3],b_count[0:3],beat[0:3];
  integer same_hp_rw_overlap[0:3];
  reg [3:0] read_enable=0,write_response_enable=0,prev_rblocked=0,prev_bblocked=0;
  reg [127:0] prev_data[0:3];reg [5:0] prev_rid[0:3],prev_bid[0:3];reg [3:0] prev_last;
  integer read_limit=16,write_limit=16,cycle=0,test_case=0;
  always @(negedge clk) begin
    rready=read_enable & {4{cycle%7!=0}};
    bready=write_response_enable & {4{cycle%5!=0}};
  end
  always @(posedge clk) begin
    cycle<=cycle+1;
    if(rst_n) for(integer p=0;p<4;p=p+1) begin
      if(dut.eligible[2*p] && dut.eligible[2*p+1]) same_hp_rw_overlap[p]=same_hp_rw_overlap[p]+1;
      if(prev_rblocked[p] && (!rvalid[p] || rdata[p]!==prev_data[p] || rid[p]!==prev_rid[p] || rlast[p]!==prev_last[p]))
        $fatal(1,"R unstable under backpressure");
      if(prev_bblocked[p] && (!bvalid[p] || bid[p]!==prev_bid[p])) $fatal(1,"B unstable under backpressure");
      prev_rblocked[p]<=rvalid[p] && !rready[p];prev_bblocked[p]<=bvalid[p] && !bready[p];
      prev_data[p]<=rdata[p];prev_rid[p]<=rid[p];prev_last[p]<=rlast[p];prev_bid[p]<=bid[p];
      if(arvalid[p] && arready[p]) begin
        read_addresses[p][ar_count[p]]=araddr[p];read_lengths[p][ar_count[p]]=arlen[p]+1;
        read_ids[p][ar_count[p]]=arid[p];ar_count[p]=ar_count[p]+1;
      end
      if(awvalid[p] && awready[p]) begin write_ids[p][aw_count[p]]=awid[p];aw_count[p]=aw_count[p]+1;end
      if(rvalid[p] && rready[p]) begin
        if(rid[p]!==read_ids[p][read_count[p]] || rresp[p]!==0) $fatal(1,"RID/order/response error");
        if(rdata[p]!==expected[((read_addresses[p][read_count[p]]-49'h10000000)>>4)+beat[p]])
          $fatal(1,"read data mismatch HP=%0d transaction=%0d beat=%0d",p,read_count[p],beat[p]);
        if(rlast[p]!==(beat[p]==read_lengths[p][read_count[p]]-1)) $fatal(1,"RLAST error");
        if(rlast[p]) begin read_count[p]=read_count[p]+1;beat[p]=0;end else beat[p]=beat[p]+1;
      end
      if(bvalid[p] && bready[p]) begin
        if(bid[p]!==write_ids[p][b_count[p]] || bresp[p]!==0) $fatal(1,"BID/order/response error");
        b_count[p]=b_count[p]+1;
      end
    end
  end
  task automatic send_ar(input integer p,input [48:0] address,input integer count,input integer size,input integer id);
    begin
      @(negedge clk);araddr[p]=address;arlen[p]=count-1;arsize[p]=size;arid[p]=id;arvalid[p]=1;
      do @(posedge clk);while(!arready[p]);@(negedge clk);arvalid[p]=0;
    end
  endtask
  task automatic send_aw(input integer p,input [48:0] address,input integer count,input integer size,input integer id);
    begin
      @(negedge clk);awaddr[p]=address;awlen[p]=count-1;awsize[p]=size;awid[p]=id;awvalid[p]=1;
      do @(posedge clk);while(!awready[p]);@(negedge clk);awvalid[p]=0;
    end
  endtask
  task automatic send_w(input integer p,input [48:0] address,input integer n,input [127:0] value,input [15:0] mask,input bit last);
    integer index;
    begin
      @(negedge clk);wdata[p]=value;wstrb[p]=mask;wlast[p]=last;wvalid[p]=1;
      do @(posedge clk);while(!wready[p]);
      index=((address-49'h10000000)>>4)+n;
      for(integer l=0;l<16;l=l+1) if(mask[l]) expected[index][8*l+:8]=value[8*l+:8];
      @(negedge clk);wvalid[p]=0;
    end
  endtask
  task automatic writes(input integer p);
    reg [48:0] address;reg [15:0] value;integer target;
    begin
      for(integer round=0;round<2;round=round+1) begin
        write_response_enable[p]=0;
        for(integer q=0;q<write_limit;q=q+1)
          send_aw(p,49'h10000000+(p+1)*4096+256+64*q,1+q%3,4,q%3);
        repeat(5) @(posedge clk);
        if(dut.wc[p]!=write_limit || awready[p]) $fatal(1,"write queue capacity not enforced");
        for(integer q=0;q<write_limit;q=q+1) begin
          address=49'h10000000+(p+1)*4096+256+64*q;value=16'h5000+p*128+round*32+q;
          for(integer n=0;n<1+q%3;n=n+1) send_w(p,address,n,{8{value}},16'hffff,n==q%3);
        end
        target=aw_count[p];write_response_enable[p]=1;
        wait(b_count[p]==target);@(negedge clk);
      end
      // Two legal requests straddle a page boundary; an illegal crossing is a
      // separate expected-negative test. Neighboring bytes remain guards.
      address=49'h10000000+(p+1)*4096+4080;
      send_aw(p,address,1,4,5);send_w(p,address,0,{8{16'h7777}},16'hffff,1);
      send_aw(p,address+16,1,4,5);send_w(p,address+16,0,{8{16'h8888}},16'hffff,1);
      address=49'h10000000+(p+1)*4096+16'hd02;
      send_aw(p,address,1,1,2);send_w(p,address,0,128'hbeef0000,16'h000c,1);
      wait(b_count[p]==aw_count[p]);
    end
  endtask
  task automatic guard_reads(input integer p);
    begin
      for(integer q=0;q<read_limit;q=q+1) send_ar(p,49'h10000000+128+q*16,1,4,q%3);
      repeat(5) @(posedge clk);
      if(dut.rc[p]!=read_limit || arready[p]) $fatal(1,"read queue capacity not enforced");
      read_enable[p]=1;wait(read_count[p]==ar_count[p]);
    end
  endtask
  task automatic verify_writes(input integer p);
    integer target;
    begin
      read_enable[p]=1;
      for(integer q=0;q<write_limit;q=q+1) send_ar(p,49'h10000000+(p+1)*4096+256+64*q,1+q%3,4,q%3);
      send_ar(p,49'h10000000+(p+1)*4096+4080,1,4,5);
      send_ar(p,49'h10000000+(p+2)*4096,1,4,5);
      send_ar(p,49'h10000000+(p+1)*4096+16'hd02,1,1,2);
      target=ar_count[p];wait(read_count[p]==target);
    end
  endtask
  task automatic concurrent_probe(input integer p);
    reg [48:0] address;
    begin
      address=49'h10000000+(p+1)*4096+16'he00;
      fork
        begin send_ar(p,49'h10000080,8,4,1);wait(read_count[p]==ar_count[p]);end
        begin
          send_aw(p,address,1,4,1);repeat(16) @(posedge clk);
          send_w(p,address,0,{8{16'h9999}},16'hffff,1);wait(b_count[p]==aw_count[p]);
        end
      join
    end
  endtask
  initial begin
    if(!$value$plusargs("READ_OUTSTANDING=%d",read_limit)) read_limit=16;
    if(!$value$plusargs("WRITE_OUTSTANDING=%d",write_limit)) write_limit=16;
    if(!$value$plusargs("CASE=%d",test_case)) test_case=0;
    for(integer i=0;i<2048;i=i+1) expected[i]={8{16'h3039}};
    for(integer p=0;p<4;p=p+1) begin
      araddr[p]=0;awaddr[p]=0;arlen[p]=0;awlen[p]=0;arsize[p]=4;awsize[p]=4;arburst[p]=1;awburst[p]=1;
      arid[p]=0;awid[p]=0;wdata[p]=0;wstrb[p]=0;ar_count[p]=0;aw_count[p]=0;read_count[p]=0;b_count[p]=0;beat[p]=0;
      same_hp_rw_overlap[p]=0;
    end
    repeat(5) @(posedge clk);@(negedge clk);rst_n=1;
    if(test_case==1) begin send_ar(0,49'h10000ff0,2,4,0);repeat(5) @(posedge clk);$fatal(1,"negative test did not reject 4KB");end
    if(test_case==2) begin send_aw(0,49'h10000100,2,4,0);send_w(0,49'h10000100,0,0,16'hffff,1);$fatal(1,"negative test did not reject WLAST");end
    if(test_case==3) begin send_aw(0,49'h10000102,1,1,0);send_w(0,49'h10000102,0,0,16'h0001,1);$fatal(1,"negative test did not reject WSTRB");end
    fork writes(0);writes(1);writes(2);writes(3);guard_reads(0);guard_reads(1);guard_reads(2);guard_reads(3);join
    fork verify_writes(0);verify_writes(1);verify_writes(2);verify_writes(3);join
    fork concurrent_probe(0);concurrent_probe(1);concurrent_probe(2);concurrent_probe(3);join
    send_ar(0,49'h10000000,256,4,0);wait(read_count[0]==ar_count[0]);
    repeat(5) @(posedge clk);
    for(integer i=0;i<2048;i=i+1) if(dut.mem[i]!==expected[i]) $fatal(1,"guard/data mismatch word=%0d",i);
    for(integer p=0;p<4;p=p+1) begin
      if(ar_count[p]!=read_count[p] || aw_count[p]!=b_count[p]) $fatal(1,"transaction lost");
      if(dut.rq_max[p]!=read_limit || dut.wq_max[p]!=write_limit) $fatal(1,"occupancy not exercised");
      if(same_hp_rw_overlap[p]==0) $fatal(1,"same HP read/write overlap not exercised");
      $display("SAME_HP_RW_OVERLAP HP=%0d CYCLES=%0d",p,same_hp_rw_overlap[p]);
    end
    if(dut.contested_cycles==0) $fatal(1,"shared DDR arbitration not exercised");
    if(dut.rw_concurrent_cycles==0) $fatal(1,"read/write service overlap not exercised");
    if(dut.service_beats!=dut.rbeats[0]+dut.rbeats[1]+dut.rbeats[2]+dut.rbeats[3]+dut.wbeats[0]+dut.wbeats[1]+dut.wbeats[2]+dut.wbeats[3])
      $fatal(1,"physical service conservation failed");
    dut.print_stats();$display("DDR_V2_PROTOCOL_PASS RO=%0d WO=%0d",read_limit,write_limit);$finish;
  end
  initial begin repeat(200000) @(posedge clk);$fatal(1,"protocol watchdog");end
endmodule
