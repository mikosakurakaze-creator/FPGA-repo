# Routed DSP OPMODE audit

Date: 2026-10-24 (local K26 build)

The audit used the actual routed functional netlist, routed DRC report, and the installed Vivado 2025.2 `DSP48E2.v` simulation model:

- netlist: `D:/weather_builds/grid_system02/system_routed_funcsim.v`
- DRC: `D:/weather_builds/grid_system02/routed_drc.rpt`
- result: `work/dpreg_opmode_audit_grid_system02_v3.json`

All 19 DPREG-7 cells were resolved and checked. The audit enumerated every stable binary combination of the distinct OPMODE selector nets, applying the primitive's `IS_OPMODE_INVERTED` mask and DSP model selector table.

Result: `pass_no_stable_binary_p_feedback=true`; no stable combination selects the P feedback path at any of the 19 cells. The new GridDehazeNet cell is included. The remaining DRC messages are still ordinary warnings: this check does not prove absence of glitches during physical transitions, SDF timing behavior, or remove the other 1,083 warnings.

The routed design remains fully routed and timing-clean according to the existing signoff report. This audit is an additional signal-level consistency check, not board validation.
