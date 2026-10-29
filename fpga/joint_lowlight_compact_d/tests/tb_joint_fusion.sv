`timescale 1ns/1ps
module tb_joint_fusion;
    parameter integer N=65536;
    reg clk=0; always #5 clk=~clk;
    reg rst=0;
    reg [6:0] ca=0,ra=0;
    reg cav=0,cwv=0,crv=0;
    wire car,cwr,crr,cbv,rrv;
    reg [31:0] cw=0;
    reg [3:0] cs=15;
    wire [1:0] cbresp,rrresp;
    wire [31:0] rr;
    wire [63:0] mar,maw;
    wire arv,rrdy,awv,wv,brdy;
    reg rv=0,bv=0;
    reg [31:0] rd=0;
    wire [31:0] wd;
    wire [3:0] ws;
    wire wlast;
    reg [1:0] resp=0,bresp=0;
    integer cycle=0,reads=0,writes=0,frames=0,invalids=0;
    wire ardy=(cycle%3)!=0;
    wire awrdy=(cycle%5)==1 || (cycle%5)==2;
    wire wrdy=(cycle%7)>=3;
    integer pending_r=0;
    reg have_aw=0,have_w=0;
    reg [63:0] saved_aw;
    reg [31:0] saved_w;
    integer ei=0,el=0,ed=0,mode=0;
    integer inject_read_error=0,inject_write_error=0;
    joint_fusion #(.SCALAR_COUNT(N)) dut(
      .ap_clk(clk),.ap_rst_n(rst),
      .s_axi_control_awaddr(ca),.s_axi_control_awvalid(cav),.s_axi_control_awready(car),
      .s_axi_control_wdata(cw),.s_axi_control_wstrb(cs),.s_axi_control_wvalid(cwv),.s_axi_control_wready(cwr),
      .s_axi_control_bresp(cbresp),.s_axi_control_bvalid(cbv),.s_axi_control_bready(1'b1),
      .s_axi_control_araddr(ra),.s_axi_control_arvalid(crv),.s_axi_control_arready(crr),
      .s_axi_control_rdata(rr),.s_axi_control_rresp(rrresp),.s_axi_control_rvalid(rrv),.s_axi_control_rready(1'b1),
      .interrupt(),.m_axi_gmem_araddr(mar),.m_axi_gmem_arvalid(arv),.m_axi_gmem_arready(ardy),
      .m_axi_gmem_rdata(rd),.m_axi_gmem_rresp(resp),.m_axi_gmem_rlast(1'b1),.m_axi_gmem_rvalid(rv),.m_axi_gmem_rready(rrdy),
      .m_axi_gmem_awaddr(maw),.m_axi_gmem_awvalid(awv),.m_axi_gmem_awready(awrdy),
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
            sample=$signed(v);
        end
    endfunction
    // Independent oracle uses signed floor division, unlike DUT magnitude RNE.
    function automatic [15:0] expected(input integer index);
        reg signed [63:0] acc,q,r;
        begin
            acc=$signed(sample(0,index))*64'sd1*ei+
                $signed(sample(1,index))*64'sd1*el+
                $signed(sample(2,index))*64'sd1*ed;
            q=acc/32768; r=acc%32768;
            if(r<0)begin q=q-1; r=r+32768; end
            if(r>16384 || (r==16384 && (q%2)!=0)) q=q+1;
            expected=q<0?0:q>16384?16384:q[15:0];
        end
    endfunction
    always @(posedge clk) begin
        cycle<=cycle+1;
        if(rst)begin
            if(rv && rrdy)rv<=0;
            if(bv && brdy)bv<=0;
            if(pending_r>0)begin
                pending_r<=pending_r-1;
                if(pending_r==1)rv<=1;
            end
            if(arv && ardy)begin : read_request
                integer branch,index;
                if(rv || pending_r!=0)$fatal(1,"overlapping read");
                if(mar>=64'h10000000 && mar<64'h10000000+2*N)begin branch=0;index=(mar-64'h10000000)/2;end
                else if(mar>=64'h11000000 && mar<64'h11000000+2*N)begin branch=1;index=(mar-64'h11000000)/2;end
                else if(mar>=64'h12000000 && mar<64'h12000000+2*N)begin branch=2;index=(mar-64'h12000000)/2;end
                else $fatal(1,"read outside buffer: %h",mar);
                if(mar[1:0]!=0)$fatal(1,"unaligned read");
                rd<={sample(branch,index+1),sample(branch,index)};
                resp<=inject_read_error?2'b10:0;
                pending_r<=2+(cycle%3); reads<=reads+1;
            end
            if(awv && awrdy)begin
                if(have_aw)$fatal(1,"duplicate AW");
                have_aw<=1;saved_aw<=maw;
            end
            if(wv && wrdy)begin
                if(have_w || ws!=15 || !wlast)$fatal(1,"bad/duplicate W");
                have_w<=1;saved_w<=wd;
            end
            if(have_aw && have_w && !bv)begin : output_word
                integer index;
                if(saved_aw<64'h13000000 || saved_aw>=64'h13000000+2*N || saved_aw[1:0]!=0)
                    $fatal(1,"write outside buffer: %h",saved_aw);
                index=(saved_aw-64'h13000000)/2;
                if(saved_w!=={expected(index+1),expected(index)})
                    $fatal(1,"Golden mismatch index=%0d actual=%h expected=%h",index,saved_w,{expected(index+1),expected(index)});
                have_aw<=0;have_w<=0;bv<=1;writes<=writes+1;
                bresp<=inject_write_error?2'b10:0;
            end
        end
    end
    task automatic write_reg(input [6:0] addr,input [31:0] data);
        begin
            // W deliberately precedes AW: AXI-Lite channels are independent.
            @(negedge clk);cw=data;cwv=1;
            do @(posedge clk);while(!cwr);
            @(negedge clk);cwv=0;
            repeat(2)@(negedge clk);
            ca=addr;cav=1;
            do @(posedge clk);while(!car);
            @(negedge clk);cav=0;
            wait(cbv);if(cbresp!=0)$fatal(1,"AXI-Lite write response");
            @(negedge clk);
        end
    endtask
    task automatic read_reg(input [6:0] addr,output [31:0] data);
        begin
            @(negedge clk);ra=addr;crv=1;
            do @(posedge clk);while(!crr);
            @(negedge clk);crv=0;
            wait(rrv);data=rr;
            @(negedge clk);
        end
    endtask
    task automatic wait_done(input integer expected_return);
        reg [31:0] ctrl,ret;
        integer polls;
        begin
            ctrl=0;polls=0;
            while(!ctrl[1])begin
                repeat(19)@(negedge clk);
                read_reg(0,ctrl);polls=polls+1;
                if(polls>N*20+100)$fatal(1,"timeout");
            end
            if(!ctrl[2])$fatal(1,"done without idle");
            read_reg(7'h10,ret);
            if($signed(ret)!=expected_return)$fatal(1,"return=%0d expected=%0d",$signed(ret),expected_return);
            read_reg(0,ctrl);if(ctrl[1])$fatal(1,"done not read-clear");
        end
    endtask
    task automatic weights(input [31:0] a,b,c);
        begin write_reg('h48,a);write_reg('h50,b);write_reg('h58,c);end
    endtask
    task automatic run_frame(input integer a,b,c,input integer modify_running);
        integer r0,w0;
        reg [31:0] completed;
        begin
            ei=a;el=b;ed=c;weights(a,b,c);
            write_reg('h68,frames+1);r0=reads;w0=writes;
            write_reg(0,1);
            if(modify_running)begin
                weights(0,0,32768);
                write_reg('h18,32'h14000000);write_reg('h68,32'hdeadbeef);
                // Busy start must not reset, queue, or replace the active frame.
                write_reg(0,1);
            end
            wait_done(0);
            if(reads-r0!=3*N/2 || writes-w0!=N/2)$fatal(1,"incomplete frame");
            read_reg('h70,completed);if(completed!=frames+1)$fatal(1,"frame snapshot changed");
            frames=frames+1;write_reg('h18,32'h10000000);
        end
    endtask
    task automatic invalid_frame(input [31:0] a,b,c,input integer rc);
        integer r0,w0;
        begin
            weights(a,b,c);r0=reads;w0=writes;
            write_reg(0,1);wait_done(rc);repeat(10)@(negedge clk);
            if(reads!=r0 || writes!=w0)$fatal(1,"invalid launch accessed DDR");
            invalids=invalids+1;
        end
    endtask
    initial begin
        if(N%32!=0)$fatal(1,"test count must preserve 64-byte alignment");
        repeat(6)@(negedge clk);rst=1;
        if(dut.round_even15(64'sd16384)!=0 || dut.round_even15(64'sd49152)!=2 ||
           dut.round_even15(64'sd81920)!=2 || dut.round_even15(-64'sd16384)!=0 ||
           dut.round_even15(-64'sd49152)!=-2 || dut.round_even15(-64'sd81920)!=-2)
           $fatal(1,"signed midpoint RNE");
        write_reg('h18,'h10000000);write_reg('h1c,0);
        write_reg('h24,'h11000000);write_reg('h28,0);
        write_reg('h30,'h12000000);write_reg('h34,0);
        write_reg('h3c,'h13000000);write_reg('h40,0);
        write_reg('h60,'h4a463031);
        run_frame(10923,10923,10922,1);
        if(N==2747520)begin
            $display("FUSION_FULL_FRAME_PASS scalars=%0d reads=%0d writes=%0d",N,reads,writes);$finish;
        end
        run_frame(32768,0,0,0);run_frame(0,32768,0,0);run_frame(0,0,32768,0);
        run_frame(16384,16384,0,0);run_frame(32767,0,1,0);
        mode=1;run_frame(10923,10923,10922,0);
        mode=2;run_frame(1,16383,16384,0);
        mode=3;run_frame(16384,16384,0,0);mode=0;
        invalid_frame(0,0,0,-2);invalid_frame(32768,32768,0,-2);
        invalid_frame('h18000,0,0,-2);invalid_frame('hffffffff,1,32768,-2);
        invalid_frame('hffffffff,'hffffffff,'h8002,-2);
        write_reg('h60,0);invalid_frame(32768,0,0,-1);write_reg('h60,'h4a463031);
        write_reg('h1c,1);invalid_frame(32768,0,0,-4);write_reg('h1c,0);
        write_reg('h18,'h10000002);invalid_frame(32768,0,0,-4);write_reg('h18,'h10000000);
        write_reg('h3c,'h10000000);invalid_frame(32768,0,0,-4);write_reg('h3c,'h13000000);
        weights(32768,0,0);ei=32768;el=0;ed=0;
        inject_read_error=1;write_reg(0,1);wait_done(-3);inject_read_error=0;
        inject_write_error=1;write_reg(0,1);wait_done(-3);inject_write_error=0;
        run_frame(10923,10923,10922,0);
        $display("FUSION_RTL_PASS frames=%0d invalid=%0d scalars=%0d reads=%0d writes=%0d",frames,invalids,frames*N,reads,writes);
        $finish;
    end
endmodule
