// Independent diagnostic observation only; no functional reset/control feedback.
(* KEEP_HIERARCHY = "TRUE" *)
module emio_clock_observer (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pl_clk0 CLK", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME pl_clk0, FREQ_HZ 99999001" *)
    input wire pl_clk0,
    input wire interconnect_aresetn,
    input wire peripheral_aresetn,
    output wire [7:0] observations
);
    wire [24:0] counter;
    wire [24:0] next_counter = counter + 25'd1;
    wire clock_seen;
    genvar bit_index;
    generate
        for (bit_index = 0; bit_index < 25; bit_index = bit_index + 1) begin : g_counter
            (* DONT_TOUCH = "TRUE" *)
            FDRE #(.INIT(1'b0)) counter_ff (
                .C(pl_clk0), .CE(1'b1), .R(1'b0),
                .D(next_counter[bit_index]), .Q(counter[bit_index])
            );
        end
    endgenerate
    // Retain this initialized one-edge marker through synthesis and implementation.
    (* DONT_TOUCH = "TRUE" *)
    FDRE #(.INIT(1'b0)) clock_seen_ff (
        .C(pl_clk0), .CE(1'b1), .R(1'b0), .D(1'b1), .Q(clock_seen)
    );

    // CFGMCLK is the independent configuration oscillator, not CFGCLK.
    wire cfgmclk, cfgmclk_global, eos;
    (* DONT_TOUCH = "TRUE" *) STARTUPE3 #(.PROG_USR("FALSE"), .SIM_CCLK_FREQ(0.0)) u_startup (
        .CFGMCLK(cfgmclk), .CFGCLK(), .EOS(eos), .PREQ(), .DI(),
        .DO(4'b0), .DTS(4'b1111), .FCSBO(1'b1), .FCSBTS(1'b1),
        .GSR(1'b0), .GTS(1'b0), .KEYCLEARB(1'b1), .PACK(1'b0),
        .USRCCLKO(1'b0), .USRCCLKTS(1'b1), .USRDONEO(1'b1), .USRDONETS(1'b1)
    );
    (* DONT_TOUCH = "TRUE" *) BUFG u_cfgmclk_bufg (.I(cfgmclk), .O(cfgmclk_global));
    wire [24:0] independent_counter;
    wire [24:0] independent_next = independent_counter + 25'd1;
    wire independent_seen, eos_meta, eos_sync;
    generate
        for (bit_index = 0; bit_index < 25; bit_index = bit_index + 1) begin : g_independent
            (* DONT_TOUCH = "TRUE" *) FDRE #(.INIT(1'b0)) independent_ff (
                .C(cfgmclk_global), .CE(1'b1), .R(1'b0),
                .D(independent_next[bit_index]), .Q(independent_counter[bit_index])
            );
        end
    endgenerate
    (* DONT_TOUCH = "TRUE" *) FDRE #(.INIT(1'b0)) independent_seen_ff (
        .C(cfgmclk_global), .CE(1'b1), .R(1'b0), .D(1'b1), .Q(independent_seen)
    );
    // EOS is status only. It never resets, enables, or gates either observer.
    (* DONT_TOUCH = "TRUE", ASYNC_REG = "TRUE" *) FDRE #(.INIT(1'b0)) eos_meta_ff (
        .C(cfgmclk_global), .CE(1'b1), .R(1'b0), .D(eos), .Q(eos_meta)
    );
    (* DONT_TOUCH = "TRUE", ASYNC_REG = "TRUE" *) FDRE #(.INIT(1'b0)) eos_sync_ff (
        .C(cfgmclk_global), .CE(1'b1), .R(1'b0), .D(eos_meta), .Q(eos_sync)
    );
    assign observations = {eos_sync, 1'b1, independent_seen, independent_counter[24], peripheral_aresetn, interconnect_aresetn, clock_seen, counter[24]};
endmodule
