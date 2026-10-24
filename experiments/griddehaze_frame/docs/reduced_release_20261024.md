# Reduced Local Release

This local candidate uses the reduced release gate requested on 2026-10-24:

- compiled-source audit, synthesis, implementation, routed timing, and route status are required;
- the 33x47 cold/warm cross-tile RTL regression is deferred;
- the post-route new-core and legacy-core numerical regressions are deferred;
- board, DMA, CMA, HDMI, and physical-device validation remain external.

The bitstream and XSA are therefore implementation artifacts for software-side integration and review, not a claim of full numerical or board acceptance. The full gate can be resumed later with `tools/continue_grid_system.py`.
