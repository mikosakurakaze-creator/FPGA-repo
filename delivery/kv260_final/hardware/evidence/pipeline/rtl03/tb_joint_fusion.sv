`timescale 1ns/1ps
module tb_joint_fusion;
    parameter integer N=65536;
    parameter integer EXTERNAL_GOLDEN=0;
    parameter integer READ_DIV=1;
    reg clk=0; always #5 clk=~clk;
    reg rst=0;
    reg [6:0] ca=0,ra=0;
    reg cav=0,cwv=0,crv=0;
    wire car,cwr,crr,cbv,rrv;
    reg [31:0] cw=0; reg [3:0] cs=15;
    wire [1:0] cbresp,rrresp; wire [31:0] rr;
    wire [63:0] mar,maw; wire [7:0] arlen,awlen;
    wire [2:0] arsize,awsize; wire [1:0] arburst,awburst;
    wire arv,rrdy,awv,wv,brdy; reg rv=0,bv=0,rlast=0;
    reg [127:0] rd=0; wire [127:0] wd; wire [15:0] ws; wire wlast;
    reg [1:0] resp=0,bresp=0;
    integer cycle=0,reads=0,writes=0,read_bursts=0,write_bursts=0,frames=0,invalids=0;
    integer simultaneous_rw=0,pipe_pairs=0,full_cycles=0,stall_until=0;
    reg previous_pop=0;
    wire ardy=(cycle%3)!=0;
    reg force_aw_stall=0;
    wire awrdy=!force_aw_stall && ((cycle%5)==1 || (cycle%5)==2);
    wire wrdy=(cycle%5)!=0 && cycle>=stall_until;
    integer rwait=0,rbeat=0,rbeats=0,rbranch=0,rscalar=0;
    reg ractive=0,have_aw=0,wend=0;
    reg [63:0] saved_aw;
    integer wcount=0,wbeats=0,bwait=0;
    reg [127:0] saved_w[0:63];
    integer ei=0,el=0,ed=0,mode=0,inject_read_at=-1,inject_write_error=0,protocol_mode=0;
    reg read_error_seen=0,protocol_seen=0;
    reg [63:0] bi=64'h10000040,bl=64'h11000fc0,bd=64'h12000080,bo=64'h13000fc0;
    reg [15:0] frame_i[0:N-1],frame_l[0:N-1],frame_d[0:N-1],frame_o[0:N-1];
    joint_fusion #(.SCALAR_COUNT(N)) dut(
      .ap_clk(clk),.ap_rst_n(rst),
      .s_axi_control_awaddr(ca),.s_axi_control_awvalid(cav),.s_axi_control_awready(car),
      .s_axi_control_wdata(cw),.s_axi_control_wstrb(cs),.s_axi_control_wvalid(cwv),.s_axi_control_wready(cwr),
      .s_axi_control_bresp(cbresp),.s_axi_control_bvalid(cbv),.s_axi_control_bready(1'b1),
      .s_axi_control_araddr(ra),.s_axi_control_arvalid(crv),.s_axi_control_arready(crr),
      .s_axi_control_rdata(rr),.s_axi_control_rresp(rrresp),.s_axi_control_rvalid(rrv),.s_axi_control_rready(1'b1),
      .interrupt(),.m_axi_gmem_araddr(mar),.m_axi_gmem_arlen(arlen),.m_axi_gmem_arsize(arsize),
      .m_axi_gmem_arburst(arburst),.m_axi_gmem_arvalid(arv),.m_axi_gmem_arready(ardy),
      .m_axi_gmem_rdata(rd),.m_axi_gmem_rresp(resp),.m_axi_gmem_rlast(rlast),.m_axi_gmem_rvalid(rv),.m_axi_gmem_rready(rrdy),
      .m_axi_gmem_awaddr(maw),.m_axi_gmem_awlen(awlen),.m_axi_gmem_awsize(awsize),.m_axi_gmem_awburst(awburst),
      .m_axi_gmem_awvalid(awv),.m_axi_gmem_awready(awrdy),
      .m_axi_gmem_wdata(wd),.m_axi_gmem_wstrb(ws),.m_axi_gmem_wlast(wlast),.m_axi_gmem_wvalid(wv),.m_axi_gmem_wready(wrdy),
      .m_axi_gmem_bresp(bresp),.m_axi_gmem_bvalid(bv),.m_axi_gmem_bready(brdy)
    );
    function automatic signed [15:0] sample(input integer branch,input integer index);
        reg [15:0] v;
        begin
            v=(index*40503+branch*10007+12345)&65535;
            if(mode==1) v=0;
            if(mode==2 && branch==0) v=0;
            if(mode==3) v=(index%2)?16'h7fff:16'h8000;
            if(EXTERNAL_GOLDEN) v=branch==0?frame_i[index]:branch==1?frame_l[index]:frame_d[index];
            sample=$signed(v);
        end
    endfunction
    // Independent signed-floor oracle; also cross-check external Golden if used.
    function automatic [15:0] expected(input integer index);
        reg signed [63:0] acc,q,r;
        begin
            acc=$signed(sample(0,index))*64'sd1*ei+
                $signed(sample(1,index))*64'sd1*el+$signed(sample(2,index))*64'sd1*ed;
            q=acc/32768; r=acc%32768;
            if(r<0)begin q=q-1;r=r+32768;end
            if(r>16384 || (r==16384 && (q%2)!=0))q=q+1;
            expected=q<0?0:q>16384?16384:q[15:0];
        end
    endfunction
    function automatic [127:0] input_beat(input integer branch,input integer index);
        integer k;
        begin for(k=0;k<8;k=k+1) input_beat[k*16+:16]=sample(branch,index+k);end
    endfunction
    reg hold_ar=0,hold_aw=0,hold_w=0;
    reg [63:0] held_ar,held_aw;
    reg [7:0] held_arlen,held_awlen;
    reg [127:0] held_w;
    reg held_last;
    always @(posedge clk) begin
        cycle<=cycle+1;
        if(rst)begin
            if(hold_ar && (!arv || mar!==held_ar || arlen!==held_arlen))$fatal(1,"AR changed while stalled");
            if(hold_aw && (!awv || maw!==held_aw || awlen!==held_awlen))$fatal(1,"AW changed while stalled");
            if(hold_w && (!wv || wd!==held_w || wlast!==held_last || ws!=16'hffff))$fatal(1,"W changed while stalled");
            hold_ar<=arv&&!ardy;held_ar<=mar;held_arlen<=arlen;
            hold_aw<=awv&&!awrdy;held_aw<=maw;held_awlen<=awlen;
            hold_w<=wv&&!wrdy;held_w<=wd;held_last<=wlast;
            if(rv&&rrdy && wv&&wrdy)simultaneous_rw<=simultaneous_rw+1;
            if(dut.fifo_pop && previous_pop)pipe_pairs<=pipe_pairs+1;
            previous_pop<=dut.fifo_pop;
            if(dut.full_o)full_cycles<=full_cycles+1;
            if(dut.count_i>256 || dut.count_l>256 || dut.count_d>256 || dut.count_o>256)$fatal(1,"FIFO overflow");
            if(rv && rrdy)begin
                reads<=reads+1;rv<=0;
                if(rlast)ractive<=0;
            end
            if(rwait>0)rwait<=rwait-1;
            if(ractive && (!rv || rrdy) && rwait==0 && rbeat<rbeats && cycle%7!=0 && cycle%READ_DIV==0)begin
                rd<=input_beat(rbranch,rscalar+8*rbeat);
                resp<=0;rlast<=rbeat==rbeats-1;rv<=1;rbeat<=rbeat+1;
                if(inject_read_at>=0 && reads>=inject_read_at && !read_error_seen)begin
                    resp<=2'b10;read_error_seen<=1;
                end
                if(protocol_mode==1 && !protocol_seen && rbeat==17)begin
                    rlast<=1;rbeats<=18;protocol_seen<=1;
                end
                if(protocol_mode==2 && !protocol_seen && rbeat==rbeats-1)begin
                    rlast<=0;rbeats<=rbeats+1;protocol_seen<=1;
                end
            end
            if(arv && ardy)begin
                if(ractive || rv)$fatal(1,"more than one read burst outstanding");
                if(arsize!=4 || arburst!=1 || arlen>63 || mar[3:0]!=0 ||
                   {1'b0,mar[11:0]}+16*(arlen+1)>4096)$fatal(1,"bad read burst");
                if(mar>=bi && mar<bi+2*N)begin rbranch<=0;rscalar<=(mar-bi)/2;end
                else if(mar>=bl && mar<bl+2*N)begin rbranch<=1;rscalar<=(mar-bl)/2;end
                else if(mar>=bd && mar<bd+2*N)begin rbranch<=2;rscalar<=(mar-bd)/2;end
                else $fatal(1,"read outside buffers %h",mar);
                ractive<=1;rbeat<=0;rbeats<=arlen+1;rwait<=6+(cycle%5);read_bursts<=read_bursts+1;
            end
            if(awv && awrdy)begin
                if(have_aw)$fatal(1,"more than one write burst outstanding");
                if(awsize!=4 || awburst!=1 || awlen>63 || maw[3:0]!=0 ||
                   {1'b0,maw[11:0]}+16*(awlen+1)>4096)$fatal(1,"bad write burst");
                if(maw<bo || maw+16*(awlen+1)>bo+2*N)$fatal(1,"write outside buffer");
                have_aw<=1;saved_aw<=maw;wbeats<=awlen+1;write_bursts<=write_bursts+1;
            end
            if(wv && wrdy)begin
                if(wend || wcount>=64 || ws!=16'hffff)$fatal(1,"invalid W beat");
                saved_w[wcount]<=wd;wcount<=wcount+1;writes<=writes+1;
                if(wlast)begin wend<=1;bwait<=5;end
            end
            if(have_aw && wend && !bv)begin : check_output
                integer j,k,index;reg [15:0] gold;
                if(wcount!=wbeats)$fatal(1,"WLAST/length mismatch");
                if(bwait>0)bwait<=bwait-1;
                else begin
                    for(j=0;j<wcount;j=j+1)for(k=0;k<8;k=k+1)begin
                        index=(saved_aw-bo)/2+j*8+k;gold=expected(index);
                        if(EXTERNAL_GOLDEN && gold!==frame_o[index])$fatal(1,"oracle/software mismatch %0d",index);
                        if(saved_w[j][k*16+:16]!==gold)$fatal(1,"Golden mismatch index=%0d got=%h gold=%h",index,saved_w[j][k*16+:16],gold);
                    end
                    bv<=1;bresp<=inject_write_error?2'b10:0;
                end
            end
            if(bv && brdy)begin bv<=0;have_aw<=0;wend<=0;wcount<=0;end
        end
    end
    task automatic write_reg(input [6:0] addr,input [31:0] data);
        begin
            @(negedge clk);cw=data;cwv=1;
            do @(posedge clk);while(!cwr);
            @(negedge clk);cwv=0;repeat(2)@(negedge clk);ca=addr;cav=1;
            do @(posedge clk);while(!car);
            @(negedge clk);cav=0;wait(cbv);if(cbresp!=0)$fatal(1,"AXIL response");@(negedge clk);
        end
    endtask
    task automatic read_reg(input [6:0] addr,output [31:0] data);
        begin
            @(negedge clk);ra=addr;crv=1;do @(posedge clk);while(!crr);
            @(negedge clk);crv=0;wait(rrv);data=rr;@(negedge clk);
        end
    endtask
    task automatic wait_done(input integer expected_return);
        reg [31:0] ctrl,ret;integer polls;
        begin
            ctrl=0;polls=0;
            while(!ctrl[1])begin
                repeat(19)@(negedge clk);read_reg(0,ctrl);polls=polls+1;
                if(polls>N+1000)$fatal(1,"timeout state R=%0d W=%0d counts=%0d/%0d/%0d/%0d",dut.rstate,dut.wstate,dut.count_i,dut.count_l,dut.count_d,dut.count_o);
            end
            if(!ctrl[2])$fatal(1,"done without idle");
            if(ractive || rv || have_aw || wend || bv || wcount)$fatal(1,"done before AXI drained");
            read_reg('h10,ret);if($signed(ret)!=expected_return)$fatal(1,"return=%0d expected=%0d",$signed(ret),expected_return);
            read_reg(0,ctrl);if(ctrl[1])$fatal(1,"done not read-clear");
        end
    endtask
    task automatic weights(input [31:0] a,b,c);
        begin write_reg('h48,a);write_reg('h50,b);write_reg('h58,c);end
    endtask
    task automatic run_frame(input integer a,b,c,input integer modify_running);
        integer r0,w0,c0,rb0,wb0;reg [31:0] completed;
        begin
            ei=a;el=b;ed=c;weights(a,b,c);write_reg('h68,frames+1);
            r0=reads;w0=writes;c0=cycle;rb0=read_bursts;wb0=write_bursts;write_reg(0,1);
            if(modify_running)begin
                weights(0,0,32768);write_reg('h18,32'h14000000);write_reg('h68,32'hdeadbeef);write_reg(0,1);
            end
            wait_done(0);
            if(reads-r0!=3*N/8 || writes-w0!=N/8)$fatal(1,"incomplete frame");
            read_reg('h70,completed);if(completed!=frames+1)$fatal(1,"snapshot changed");
            $display("FUSION_FRAME_METRICS frame=%0d scalars=%0d cycles=%0d read_beats=%0d write_beats=%0d read_bursts=%0d write_bursts=%0d overlap=%0d read_div=%0d",frames+1,N,cycle-c0,reads-r0,writes-w0,read_bursts-rb0,write_bursts-wb0,simultaneous_rw,READ_DIV);
            if(N==2747520 && cycle-c0>3333300)$fatal(1,"fusion exceeds 30-FPS cycle budget in this memory model");
            frames=frames+1;write_reg('h18,bi[31:0]);
        end
    endtask
    task automatic invalid_frame(input [31:0] a,b,c,input integer rc);
        integer r0,w0;
        begin
            weights(a,b,c);r0=reads;w0=writes;write_reg(0,1);wait_done(rc);repeat(10)@(negedge clk);
            if(reads!=r0 || writes!=w0)$fatal(1,"invalid launch accessed DDR");invalids=invalids+1;
        end
    endtask
    initial begin
        if(N%32!=0)$fatal(1,"frame must preserve 64-byte alignment");
        if(EXTERNAL_GOLDEN)begin
            $readmemh("original.hex",frame_i);$readmemh("lowlight.hex",frame_l);
            $readmemh("d_output.hex",frame_d);$readmemh("fused.hex",frame_o);
        end
        repeat(6)@(negedge clk);rst=1;
        if(dut.round_even15(64'sd16384)!=0 || dut.round_even15(64'sd49152)!=2 ||
           dut.round_even15(64'sd81920)!=2 || dut.round_even15(-64'sd16384)!=0 ||
           dut.round_even15(-64'sd49152)!=-2 || dut.round_even15(-64'sd81920)!=-2)$fatal(1,"signed midpoint RNE");
        write_reg('h18,bi[31:0]);write_reg('h1c,0);write_reg('h24,bl[31:0]);write_reg('h28,0);
        write_reg('h30,bd[31:0]);write_reg('h34,0);write_reg('h3c,bo[31:0]);write_reg('h40,0);write_reg('h60,'h4a463031);
        run_frame(10923,10923,10922,1);
        if(N==2747520)begin
            if(simultaneous_rw==0 || pipe_pairs==0)$fatal(1,"no transport/compute overlap");
            if(EXTERNAL_GOLDEN)$display("FUSION_SAME_IMAGE_PASS scalars=%0d reads=%0d writes=%0d",N,reads,writes);
            else $display("FUSION_FULL_FRAME_PASS scalars=%0d reads=%0d writes=%0d",N,reads,writes);
            $finish;
        end
        run_frame(32768,0,0,0);run_frame(0,32768,0,0);run_frame(0,0,32768,0);
        run_frame(16384,16384,0,0);run_frame(32767,0,1,0);
        mode=1;run_frame(10923,10923,10922,0);mode=2;run_frame(1,16383,16384,0);
        mode=3;run_frame(16384,16384,0,0);mode=0;
        invalid_frame(0,0,0,-2);invalid_frame(32768,32768,0,-2);
        invalid_frame('h18000,0,0,-2);invalid_frame('hffffffff,1,32768,-2);invalid_frame('hffffffff,'hffffffff,'h8002,-2);
        write_reg('h60,0);invalid_frame(32768,0,0,-1);write_reg('h60,'h4a463031);
        write_reg('h1c,1);invalid_frame(32768,0,0,-4);write_reg('h1c,0);
        write_reg('h18,'h10000002);invalid_frame(32768,0,0,-4);write_reg('h18,bi[31:0]);
        write_reg('h3c,bi[31:0]);invalid_frame(32768,0,0,-4);write_reg('h3c,bo[31:0]);
        weights(32768,0,0);ei=32768;el=0;ed=0;
        inject_read_at=reads+700;read_error_seen=0;write_reg(0,1);wait_done(-3);inject_read_at=-1;
        // Force a read fault while AWVALID is held: the committed write must
        // retain its address/data and complete before reporting the error.
        force_aw_stall=1;read_error_seen=0;write_reg(0,1);wait(awv);
        inject_read_at=reads;wait(dut.aborted);repeat(20)@(negedge clk);
        if(!dut.busy || !awv)$fatal(1,"aborted/withdrew an unaccepted AW");
        force_aw_stall=0;wait_done(-3);inject_read_at=-1;
        inject_write_error=1;write_reg(0,1);wait_done(-3);inject_write_error=0;
        protocol_mode=1;protocol_seen=0;write_reg(0,1);wait_done(-3);protocol_mode=0;
        protocol_mode=2;protocol_seen=0;write_reg(0,1);wait_done(-3);protocol_mode=0;
        // Hold the writer long enough to fill output FIFO and stall all stages.
        stall_until=cycle+5000;run_frame(10923,10923,10922,0);
        if(simultaneous_rw==0 || pipe_pairs==0 || full_cycles==0)$fatal(1,"missing overlap/FIFO-pressure coverage");
        $display("FUSION_RTL_PASS frames=%0d invalid=%0d scalars=%0d reads=%0d writes=%0d overlap=%0d full_cycles=%0d",frames,invalids,frames*N,reads,writes,simultaneous_rw,full_cycles);$finish;
    end
endmodule
