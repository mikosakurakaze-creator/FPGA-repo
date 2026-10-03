`timescale 1ns/1ps
// One physical shared memory and at most one R-fetch/W-write service beat per
// cycle. Address queues cover independent burst startup latency. Responses are
// strictly FIFO per HP across all IDs, a legal stronger ordering than required.
module shared_axi_ddr #(
  parameter integer WORDS=1,
  parameter [48:0] BASE=49'h10000000,
  parameter integer READ_OUTSTANDING=16, WRITE_OUTSTANDING=16
)(
  input wire clk, input wire rst_n,
  input wire [48:0] araddr[0:3], input wire [7:0] arlen[0:3],
  input wire [2:0] arsize[0:3], input wire [1:0] arburst[0:3],
  input wire [5:0] arid[0:3], input wire [3:0] arvalid, output wire [3:0] arready,
  output reg [127:0] rdata[0:3], output reg [5:0] rid[0:3],
  output reg [3:0] rlast, output reg [3:0] rvalid,
  input wire [3:0] rready, output wire [1:0] rresp[0:3],
  input wire [48:0] awaddr[0:3], input wire [7:0] awlen[0:3],
  input wire [2:0] awsize[0:3], input wire [1:0] awburst[0:3],
  input wire [5:0] awid[0:3], input wire [3:0] awvalid, output wire [3:0] awready,
  input wire [127:0] wdata[0:3], input wire [15:0] wstrb[0:3],
  input wire [3:0] wlast, input wire [3:0] wvalid, output wire [3:0] wready,
  output reg [5:0] bid[0:3], output reg [3:0] bvalid,
  input wire [3:0] bready, output wire [1:0] bresp[0:3]
);
  reg [127:0] mem[0:WORDS-1];
  reg [48:0] rq_addr[0:3][0:READ_OUTSTANDING-1], wq_addr[0:3][0:WRITE_OUTSTANDING-1];
  reg [2:0] rq_size[0:3][0:READ_OUTSTANDING-1], wq_size[0:3][0:WRITE_OUTSTANDING-1];
  reg [5:0] rq_id[0:3][0:READ_OUTSTANDING-1], wq_id[0:3][0:WRITE_OUTSTANDING-1];
  integer rq_len[0:3][0:READ_OUTSTANDING-1], rq_beat[0:3][0:READ_OUTSTANDING-1];
  integer wq_len[0:3][0:WRITE_OUTSTANDING-1], wq_beat[0:3][0:WRITE_OUTSTANDING-1];
  longint rq_start[0:3][0:READ_OUTSTANDING-1], rq_due[0:3][0:READ_OUTSTANDING-1];
  longint wq_start[0:3][0:WRITE_OUTSTANDING-1], wq_due[0:3][0:WRITE_OUTSTANDING-1];
  reg wq_done[0:3][0:WRITE_OUTSTANDING-1];
  integer rh[0:3],rt[0:3],wh[0:3],wt[0:3],bh[0:3],rc[0:3],wc[0:3],wp[0:3];
  integer read_limit=READ_OUTSTANDING,write_limit=WRITE_OUTSTANDING;
  integer delay_cycles=16,service_period=1,rr=0,chosen,p,idx,lane;
  reg [7:0] eligible,grant;
  longint cycle=0,service_beats=0,contested_cycles=0,rw_concurrent_cycles=0;
  longint arcs[0:3],awcs[0:3],rbeats[0:3],wbeats[0:3],useful_write_bytes[0:3];
  longint ar_stalls[0:3],aw_stalls[0:3],r_stalls[0:3],r_backpressure[0:3],w_stalls[0:3],b_wait[0:3];
  longint first_r_sum[0:3],first_r_max[0:3],first_r_samples[0:3];
  longint b_latency_sum[0:3],b_latency_max[0:3],b_samples[0:3],rq_sum[0:3],wq_sum[0:3];
  integer rq_max[0:3],wq_max[0:3];
  reg [48:0] beat_address;
  // Expose the current AXI4 write-data address for the existing slot/guard BFM.
  wire [48:0] write_address[0:3];
  integer next_rc,next_wc;
  function automatic integer popcount16(input [15:0] bits);
    begin popcount16=0;for(integer b=0;b<16;b=b+1) if(bits[b]) popcount16=popcount16+1;end
  endfunction
  task automatic check_request(input [48:0] address,input [7:0] length,input [2:0] size,input [1:0] burst);
    reg [48:0] aligned_address,last_address;
    begin
      aligned_address=address & ~((49'd1<<size)-1);
      last_address=aligned_address+(length+1)*(49'd1<<size)-1;
      if(size>4 || burst!==1 || aligned_address[48:12]!=last_address[48:12])
        $fatal(1,"DDR v2 illegal size/INCR/4KB addr=%h len=%d size=%d",address,length,size);
      if(address<BASE || last_address>=BASE+WORDS*16) $fatal(1,"DDR v2 request outside memory");
    end
  endtask
  initial begin
    if(!$value$plusargs("READ_OUTSTANDING=%d",read_limit)) read_limit=READ_OUTSTANDING;
    if(!$value$plusargs("WRITE_OUTSTANDING=%d",write_limit)) write_limit=WRITE_OUTSTANDING;
    if(!$value$plusargs("DDR_DELAY=%d",delay_cycles)) delay_cycles=16;
    if(!$value$plusargs("SERVICE_PERIOD=%d",service_period)) service_period=1;
    if(read_limit<1 || read_limit>READ_OUTSTANDING || write_limit<1 || write_limit>WRITE_OUTSTANDING ||
       delay_cycles<0 || service_period<1) $fatal(1,"DDR v2 parameter out of range");
    $readmemh("shared_ddr.hex",mem);rvalid=0;rlast=0;bvalid=0;
    for(integer j=0;j<4;j=j+1) begin
      rh[j]=0;rt[j]=0;wh[j]=0;wt[j]=0;bh[j]=0;rc[j]=0;wc[j]=0;wp[j]=0;
      rdata[j]=0;rid[j]=0;bid[j]=0;arcs[j]=0;awcs[j]=0;rbeats[j]=0;wbeats[j]=0;useful_write_bytes[j]=0;
      ar_stalls[j]=0;aw_stalls[j]=0;r_stalls[j]=0;r_backpressure[j]=0;w_stalls[j]=0;b_wait[j]=0;
      first_r_sum[j]=0;first_r_max[j]=0;first_r_samples[j]=0;b_latency_sum[j]=0;b_latency_max[j]=0;b_samples[j]=0;
      rq_max[j]=0;wq_max[j]=0;rq_sum[j]=0;wq_sum[j]=0;
      for(integer q=0;q<WRITE_OUTSTANDING;q=q+1) wq_done[j][q]=0;
    end
  end
  generate for(genvar g=0;g<4;g=g+1) begin:port_logic
    assign arready[g]=rst_n && rc[g]<read_limit;
    assign awready[g]=rst_n && wc[g]<write_limit;
    assign wready[g]=rst_n && grant[2*g+1];
    assign write_address[g]=(wq_addr[g][wh[g]] & ~((49'd1<<wq_size[g][wh[g]])-1))+
                            (wq_beat[g][wh[g]]<<wq_size[g][wh[g]]);
    assign rresp[g]=0;assign bresp[g]=0;
  end endgenerate
  always @* begin
    eligible=0;grant=0;chosen=-1;
    for(integer j=0;j<4;j=j+1) begin
      if(rc[j]>0) eligible[2*j]=cycle>=rq_due[j][rh[j]] &&
        (!rvalid[j] || rready[j]) && !(rvalid[j] && rready[j] && rlast[j]);
      eligible[2*j+1]=wp[j]>0 && wvalid[j];
    end
    if(rst_n && cycle%service_period==0)
      for(integer q=0;q<8;q=q+1)
        if(chosen<0 && eligible[(rr+q)%8]) begin chosen=(rr+q)%8;grant[chosen]=1;end
  end
  always @(posedge clk) begin
    cycle<=cycle+1;
    if(!rst_n) begin
      rvalid<=0;rlast<=0;bvalid<=0;rr<=0;
      for(p=0;p<4;p=p+1) begin
        rh[p]<=0;rt[p]<=0;wh[p]<=0;wt[p]<=0;bh[p]<=0;rc[p]<=0;wc[p]<=0;wp[p]<=0;
        for(integer q=0;q<WRITE_OUTSTANDING;q=q+1) wq_done[p][q]<=0;
      end
    end else begin
      if(popcount16({8'b0,eligible})>1) contested_cycles<=contested_cycles+1;
      if((eligible & 8'h55)!=0 && (eligible & 8'haa)!=0) rw_concurrent_cycles<=rw_concurrent_cycles+1;
      if(|grant) begin rr<=(chosen+1)%8;service_beats<=service_beats+1;end
      for(p=0;p<4;p=p+1) begin
        next_rc=rc[p]+(arvalid[p] && arready[p])-(rvalid[p] && rready[p] && rlast[p]);
        next_wc=wc[p]+(awvalid[p] && awready[p])-(bvalid[p] && bready[p]);
        if(next_rc<0 || next_rc>read_limit || next_wc<0 || next_wc>write_limit)
          $fatal(1,"DDR v2 queue accounting error");
        rc[p]<=next_rc;wc[p]<=next_wc;
        wp[p]<=wp[p]+(awvalid[p] && awready[p])-(wvalid[p] && wready[p] && wlast[p]);
        if(next_rc>rq_max[p]) rq_max[p]<=next_rc;
        if(next_wc>wq_max[p]) wq_max[p]<=next_wc;
        rq_sum[p]<=rq_sum[p]+rc[p];wq_sum[p]<=wq_sum[p]+wc[p];
        if(arvalid[p] && !arready[p]) ar_stalls[p]<=ar_stalls[p]+1;
        if(awvalid[p] && !awready[p]) aw_stalls[p]<=aw_stalls[p]+1;
        if(rc[p]>0 && rready[p] && !rvalid[p]) r_stalls[p]<=r_stalls[p]+1;
        if(rvalid[p] && !rready[p]) r_backpressure[p]<=r_backpressure[p]+1;
        if(wvalid[p] && !wready[p]) w_stalls[p]<=w_stalls[p]+1;
        if(wc[p]>0 && bready[p] && !bvalid[p]) b_wait[p]<=b_wait[p]+1;
        if(arvalid[p] && arready[p]) begin
          check_request(araddr[p],arlen[p],arsize[p],arburst[p]);
          rq_addr[p][rt[p]]<=araddr[p];rq_size[p][rt[p]]<=arsize[p];rq_id[p][rt[p]]<=arid[p];
          rq_len[p][rt[p]]<=arlen[p]+1;rq_beat[p][rt[p]]<=0;
          rq_start[p][rt[p]]<=cycle;rq_due[p][rt[p]]<=cycle+delay_cycles+1;
          rt[p]<=(rt[p]+1)%READ_OUTSTANDING;arcs[p]<=arcs[p]+1;
        end
        if(rvalid[p] && rready[p]) begin
          rbeats[p]<=rbeats[p]+1;
          if(rq_beat[p][rh[p]]==1) begin
            first_r_samples[p]<=first_r_samples[p]+1;
            first_r_sum[p]<=first_r_sum[p]+cycle-rq_start[p][rh[p]];
            if(cycle-rq_start[p][rh[p]]>first_r_max[p]) first_r_max[p]<=cycle-rq_start[p][rh[p]];
          end
          rvalid[p]<=0;
          if(rlast[p]) begin rh[p]<=(rh[p]+1)%READ_OUTSTANDING;rlast[p]<=0;end
        end
        if(grant[2*p]) begin
          beat_address=(rq_addr[p][rh[p]] & ~((49'd1<<rq_size[p][rh[p]])-1))+
                       (rq_beat[p][rh[p]]<<rq_size[p][rh[p]]);
          idx=(beat_address-BASE)>>4;
          if(idx<0 || idx>=WORDS) $fatal(1,"DDR v2 read beat outside memory");
          rdata[p]<=mem[idx];rid[p]<=rq_id[p][rh[p]];rvalid[p]<=1;
          rlast[p]<=rq_beat[p][rh[p]]==rq_len[p][rh[p]]-1;
          rq_beat[p][rh[p]]<=rq_beat[p][rh[p]]+1;
        end
        if(awvalid[p] && awready[p]) begin
          check_request(awaddr[p],awlen[p],awsize[p],awburst[p]);
          wq_addr[p][wt[p]]<=awaddr[p];wq_size[p][wt[p]]<=awsize[p];wq_id[p][wt[p]]<=awid[p];
          wq_len[p][wt[p]]<=awlen[p]+1;wq_beat[p][wt[p]]<=0;wq_done[p][wt[p]]<=0;wq_start[p][wt[p]]<=cycle;
          wt[p]<=(wt[p]+1)%WRITE_OUTSTANDING;awcs[p]<=awcs[p]+1;
        end
        if(wvalid[p] && wready[p]) begin
          if(wlast[p]!==(wq_beat[p][wh[p]]==wq_len[p][wh[p]]-1)) $fatal(1,"DDR v2 WLAST mismatch");
          beat_address=(wq_addr[p][wh[p]] & ~((49'd1<<wq_size[p][wh[p]])-1))+
                       (wq_beat[p][wh[p]]<<wq_size[p][wh[p]]);
          idx=(beat_address-BASE)>>4;
          if(idx<0 || idx>=WORDS) $fatal(1,"DDR v2 write beat outside memory");
          for(lane=0;lane<16;lane=lane+1) if(wstrb[p][lane]) begin
            if((BASE+idx*16+lane)<beat_address || (BASE+idx*16+lane)>=beat_address+(49'd1<<wq_size[p][wh[p]]) ||
               (wq_beat[p][wh[p]]==0 && BASE+idx*16+lane<wq_addr[p][wh[p]]))
              $fatal(1,"DDR v2 WSTRB outside valid byte lanes");
            mem[idx][8*lane+:8]<=wdata[p][8*lane+:8];
          end
          wbeats[p]<=wbeats[p]+1;useful_write_bytes[p]<=useful_write_bytes[p]+popcount16(wstrb[p]);
          wq_beat[p][wh[p]]<=wq_beat[p][wh[p]]+1;
          if(wlast[p]) begin
            wq_done[p][wh[p]]<=1;wq_due[p][wh[p]]<=cycle+delay_cycles+1;wh[p]<=(wh[p]+1)%WRITE_OUTSTANDING;
          end
        end
        if(wc[p]>0 && !bvalid[p] && wq_done[p][bh[p]] && cycle>=wq_due[p][bh[p]]) begin
          bid[p]<=wq_id[p][bh[p]];bvalid[p]<=1;
        end
        if(bvalid[p] && bready[p]) begin
          bvalid[p]<=0;wq_done[p][bh[p]]<=0;bh[p]<=(bh[p]+1)%WRITE_OUTSTANDING;
          b_samples[p]<=b_samples[p]+1;b_latency_sum[p]<=b_latency_sum[p]+cycle-wq_start[p][bh[p]];
          if(cycle-wq_start[p][bh[p]]>b_latency_max[p]) b_latency_max[p]<=cycle-wq_start[p][bh[p]];
        end
      end
    end
  end
  task print_stats;
    begin
      $display("DDR_SHARED STATED_SERVICE_BEATS_PER_PERIOD=1 PERIOD=%0d DELAY=%0d SERVED=%0d CONTESTED_CYCLES=%0d",service_period,delay_cycles,service_beats,contested_cycles);
      $display("DDR_V2 READ_OUTSTANDING=%0d WRITE_OUTSTANDING=%0d",read_limit,write_limit);
      $display("DDR_V2_RW_CONCURRENT_CYCLES=%0d",rw_concurrent_cycles);
      for(integer j=0;j<4;j=j+1) begin
        $display("HP_STATS HP=%0d AR=%0d AW=%0d R=%0d W=%0d WRITE_BYTES=%0d AR_STALL=%0d AW_STALL=%0d R_STALL=%0d R_BACK=%0d W_STALL=%0d B_WAIT=%0d FIRST_R_SAMPLES=%0d FIRST_R_SUM=%0d FIRST_R_MAX=%0d B_SAMPLES=%0d B_LATENCY_SUM=%0d B_LATENCY_MAX=%0d",j,arcs[j],awcs[j],rbeats[j],wbeats[j],useful_write_bytes[j],ar_stalls[j],aw_stalls[j],r_stalls[j],r_backpressure[j],w_stalls[j],b_wait[j],first_r_samples[j],first_r_sum[j],first_r_max[j],b_samples[j],b_latency_sum[j],b_latency_max[j]);
        $display("HP_QUEUE HP=%0d READ_MAX=%0d WRITE_MAX=%0d READ_OCCUPANCY_SUM=%0d WRITE_OCCUPANCY_SUM=%0d",j,rq_max[j],wq_max[j],rq_sum[j],wq_sum[j]);
        if(rc[j] || wc[j] || wp[j] || rvalid[j] || bvalid[j]) $fatal(1,"DDR v2 not drained");
      end
    end
  endtask
endmodule
