@echo off
setlocal
set "SETTINGS=E:\Xilinx\2025.2\data\settings64.bat"
set "CONFIG=E:\github\-\fpga\hls\fixed16_rtl_cosim\bilinear_hls_config.cfg"
set "PROJECT=E:\HLS\fpga_bilinear_fixed16_cosim"
set "VITIS_RUN=E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat"
set "VITIS_COMPILE=E:\Xilinx\2025.2\Vitis\bin\v++.bat"

if not exist "%SETTINGS%" exit /b 2
if not exist "%CONFIG%" exit /b 2
if not exist "%VITIS_RUN%" exit /b 2
if not exist "%VITIS_COMPILE%" exit /b 2
if not exist "%PROJECT%" mkdir "%PROJECT%" || exit /b 2
cd /d "%PROJECT%" || exit /b 2
if not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"
call "%SETTINGS%" || exit /b 1
call "%VITIS_RUN%" --mode hls --csim --config "%CONFIG%" --work_dir fpga_bilinear_fixed16_cosim || exit /b 1
call "%VITIS_COMPILE%" -c --mode hls --config "%CONFIG%" --work_dir fpga_bilinear_fixed16_cosim || exit /b 1
call "%VITIS_RUN%" --mode hls --cosim --config "%CONFIG%" --work_dir fpga_bilinear_fixed16_cosim || exit /b 1
findstr /C:"C/RTL co-simulation finished: PASS" "%PROJECT%\fpga_bilinear_fixed16_cosim\logs\hls_run_cosim.log" >nul || exit /b 1
exit /b 0
