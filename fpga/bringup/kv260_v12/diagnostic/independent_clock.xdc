# Diagnostic source only; never change PL0's 10 ns functional constraints.
create_clock -name independent_cfgmclk -period 17.391 [get_pins system_i/u_emio_observer/inst/u_startup/CFGMCLK]
set_clock_uncertainty 0.200 [get_clocks independent_cfgmclk]
# STARTUP is a configuration-site source, not a dedicated CCIO source.
# Allow the general-routing segment to this diagnostic BUFG input only.
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets -of_objects [get_pins system_i/u_emio_observer/inst/u_startup/CFGMCLK]]
# EOS is asynchronous status: exclude only the first synchronizer D endpoint.
set_false_path -to [get_pins system_i/u_emio_observer/inst/eos_meta_ff/D]
