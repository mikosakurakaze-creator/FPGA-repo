`timescale 1ns/1ps
// Four actual HP ports share one 128-bit beat service opportunity per cycle.
// One read and one write outstanding per HP; response IDs, stable R/B,
// arbitrary legal narrow sizes, byte strobes, WLAST and 4KB are honored.
module shared_axi_ddr #(
  parameter integer WORDS=1,
  parameter [48:0] BASE=49'h10000000
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
  reg [3:0] reading=0, writing=0, b_pending=0;
  reg [48:0] ra[0:3], wa[0:3];
  reg [2:0] rs[0:3], ws[0:3];
  integer rn[0:3], rb[0:3], wn[0:3], wb[0:3], rt[0:3], bt[0:3];
  wire [48:0] read_address[0:3], write_address[0:3];
  reg [7:0] eligible, grant;
  integer rr=0, chosen, k, p, lane, idx;
  integer delay_cycles=16, service_period=1;
  longint cycle=0, service_beats=0, contested_cycles=0;
  longint arcs[0:3], awcs[0:3], rbeats[0:3], wbeats[0:3], useful_write_bytes[0:3];
  longint ar_stalls[0:3], aw_stalls[0:3], r_stalls[0:3], r_backpressure[0:3], w_stalls[0:3], b_wait[0:3];
  longint ar_cycle[0:3], aw_cycle[0:3], first_r_sum[0:3], first_r_max[0:3], b_latency_sum[0:3], b_latency_max[0:3];
  longint first_r_samples[0:3], b_samples[0:3];
  integer outstanding_r[0:3], outstanding_w[0:3];
  function automatic integer popcount16(input [15:0] bits);
    begin
      popcount16=0;
      for(integer b=0;b<16;b=b+1) if(bits[b]) popcount16=popcount16+1;
    end
  endfunction
  initial begin
    if(!$value$plusargs("DDR_DELAY=%d",delay_cycles)) delay_cycles=16;
    if(!$value$plusargs("SERVICE_PERIOD=%d",service_period)) service_period=1;
    if(delay_cycles<0 || service_period<1) $fatal(1,"invalid DDR service parameters");
    $readmemh("shared_ddr.hex",mem);
    rvalid=0;rlast=0;bvalid=0;
    for(integer j=0;j<4;j=j+1) begin
      ra[j]=0;wa[j]=0;rs[j]=0;ws[j]=0;rn[j]=0;rb[j]=0;wn[j]=0;wb[j]=0;rt[j]=0;bt[j]=0;
      rdata[j]=0;rid[j]=0;bid[j]=0;
      arcs[j]=0;awcs[j]=0;rbeats[j]=0;wbeats[j]=0;useful_write_bytes[j]=0;
      ar_stalls[j]=0;aw_stalls[j]=0;r_stalls[j]=0;r_backpressure[j]=0;w_stalls[j]=0;b_wait[j]=0;
      first_r_sum[j]=0;first_r_max[j]=0;b_latency_sum[j]=0;b_latency_max[j]=0;
      first_r_samples[j]=0;b_samples[j]=0;ar_cycle[j]=0;aw_cycle[j]=0;
    end
  end
  generate for(genvar g=0;g<4;g=g+1) begin:port_logic
    assign arready[g]=rst_n && !reading[g] && !rvalid[g];
    assign awready[g]=rst_n && !writing[g] && !b_pending[g] && !bvalid[g];
    assign rresp[g]=0;
    assign bresp[g]=0;
    assign read_address[g]=(ra[g] & ~((49'd1<<rs[g])-1)) + (rb[g]<<rs[g]);
    assign write_address[g]=(wa[g] & ~((49'd1<<ws[g])-1)) + (wb[g]<<ws[g]);
    assign wready[g]=rst_n && grant[2*g+1];
  end endgenerate
  always @* begin
    eligible=0;grant=0;chosen=-1;
    for(integer j=0;j<4;j=j+1) begin
      eligible[2*j]=reading[j] && rt[j]==0 && (!rvalid[j] || rready[j]) &&
                       !(rvalid[j] && rready[j] && rlast[j]);
      eligible[2*j+1]=writing[j] && wvalid[j];
    end
    if(rst_n && cycle%service_period==0) begin
      for(integer q=0;q<8;q=q+1) begin
        if(chosen<0 && eligible[(rr+q)%8]) begin chosen=(rr+q)%8;grant[chosen]=1;end
      end
    end
  end
  always @(posedge clk) begin
    cycle<=cycle+1;
    if(!rst_n) begin
      reading<=0;writing<=0;b_pending<=0;rvalid<=0;rlast<=0;bvalid<=0;rr<=0;
    end else begin
      if(popcount16({8'b0,eligible})>1) contested_cycles<=contested_cycles+1;
      if(|grant) begin rr<=(chosen+1)%8;service_beats<=service_beats+1;end
      for(p=0;p<4;p=p+1) begin
        if(arvalid[p] && !arready[p]) ar_stalls[p]<=ar_stalls[p]+1;
        if(awvalid[p] && !awready[p]) aw_stalls[p]<=aw_stalls[p]+1;
        if(reading[p] && rready[p] && !rvalid[p]) r_stalls[p]<=r_stalls[p]+1;
        if(rvalid[p] && !rready[p]) r_backpressure[p]<=r_backpressure[p]+1;
        if(wvalid[p] && !wready[p]) w_stalls[p]<=w_stalls[p]+1;
        if(bready[p] && b_pending[p] && !bvalid[p]) b_wait[p]<=b_wait[p]+1;
        if(arvalid[p] && arready[p]) begin
          if(arsize[p]>4 || arburst[p]!==1 ||
             ((araddr[p] & ~((49'd1<<arsize[p])-1))%4096)+(arlen[p]+1)*(1<<arsize[p])>4096)
            $fatal(1,"HP%0d invalid read size/burst/4KB",p);
          if(araddr[p]<BASE || ((araddr[p]-BASE)>>4)>=WORDS) $fatal(1,"read outside DDR");
          reading[p]<=1;ra[p]<=araddr[p];rs[p]<=arsize[p];rn[p]<=arlen[p]+1;rb[p]<=0;
          rid[p]<=arid[p];rt[p]<=delay_cycles;arcs[p]<=arcs[p]+1;ar_cycle[p]<=cycle;
        end
        if(reading[p] && rt[p]>0) rt[p]<=rt[p]-1;
        if(rvalid[p] && rready[p]) begin
          rbeats[p]<=rbeats[p]+1;
          if(rb[p]==1) begin
            first_r_samples[p]<=first_r_samples[p]+1;first_r_sum[p]<=first_r_sum[p]+cycle-ar_cycle[p];
            if(cycle-ar_cycle[p]>first_r_max[p]) first_r_max[p]<=cycle-ar_cycle[p];
          end
          if(rlast[p]) begin reading[p]<=0;rvalid[p]<=0;rlast[p]<=0;end
          else rvalid[p]<=0;
        end
        if(grant[2*p]) begin
          idx=(read_address[p]-BASE)>>4;
          if(idx<0 || idx>=WORDS) $fatal(1,"read beat outside DDR");
          rdata[p]<=mem[idx];rvalid[p]<=1;rlast[p]<=rb[p]==rn[p]-1;rb[p]<=rb[p]+1;
        end
        if(awvalid[p] && awready[p]) begin
          if(awsize[p]>4 || awburst[p]!==1 ||
             ((awaddr[p] & ~((49'd1<<awsize[p])-1))%4096)+(awlen[p]+1)*(1<<awsize[p])>4096)
            $fatal(1,"HP%0d invalid write size/burst/4KB",p);
          if(awaddr[p]<BASE || ((awaddr[p]-BASE)>>4)>=WORDS) $fatal(1,"write outside DDR");
          writing[p]<=1;wa[p]<=awaddr[p];ws[p]<=awsize[p];wn[p]<=awlen[p]+1;wb[p]<=0;
          bid[p]<=awid[p];awcs[p]<=awcs[p]+1;aw_cycle[p]<=cycle;
        end
        if(wvalid[p] && wready[p]) begin
          if(wlast[p]!==(wb[p]==wn[p]-1)) $fatal(1,"HP%0d WLAST mismatch",p);
          idx=(write_address[p]-BASE)>>4;
          if(idx<0 || idx>=WORDS) $fatal(1,"write beat outside DDR");
          for(lane=0;lane<16;lane=lane+1) if(wstrb[p][lane]) mem[idx][8*lane+:8]<=wdata[p][8*lane+:8];
          wbeats[p]<=wbeats[p]+1;useful_write_bytes[p]<=useful_write_bytes[p]+popcount16(wstrb[p]);
          wb[p]<=wb[p]+1;
          if(wlast[p]) begin writing[p]<=0;b_pending[p]<=1;bt[p]<=delay_cycles;end
        end
        if(b_pending[p] && !bvalid[p]) begin
          if(bt[p]>0) bt[p]<=bt[p]-1;
          else begin b_pending[p]<=0;bvalid[p]<=1;end
        end
        if(bvalid[p] && bready[p]) begin
          bvalid[p]<=0;b_samples[p]<=b_samples[p]+1;b_latency_sum[p]<=b_latency_sum[p]+cycle-aw_cycle[p];
          if(cycle-aw_cycle[p]>b_latency_max[p]) b_latency_max[p]<=cycle-aw_cycle[p];
        end
      end
    end
  end
  task print_stats;
    begin
      $display("DDR_SHARED STATED_SERVICE_BEATS_PER_PERIOD=1 PERIOD=%0d DELAY=%0d SERVED=%0d CONTESTED_CYCLES=%0d",service_period,delay_cycles,service_beats,contested_cycles);
      for(integer j=0;j<4;j=j+1) begin
        $display("HP_STATS HP=%0d AR=%0d AW=%0d R=%0d W=%0d WRITE_BYTES=%0d AR_STALL=%0d AW_STALL=%0d R_STALL=%0d R_BACK=%0d W_STALL=%0d B_WAIT=%0d FIRST_R_SAMPLES=%0d FIRST_R_SUM=%0d FIRST_R_MAX=%0d B_SAMPLES=%0d B_LATENCY_SUM=%0d B_LATENCY_MAX=%0d",j,arcs[j],awcs[j],rbeats[j],wbeats[j],useful_write_bytes[j],ar_stalls[j],aw_stalls[j],r_stalls[j],r_backpressure[j],w_stalls[j],b_wait[j],first_r_samples[j],first_r_sum[j],first_r_max[j],b_samples[j],b_latency_sum[j],b_latency_max[j]);
        if(reading[j] || writing[j] || rvalid[j] || b_pending[j] || bvalid[j]) $fatal(1,"DDR not drained");
      end
    end
  endtask
endmodule
