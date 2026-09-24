@echo off
setlocal
set "SETTINGS=E:\Xilinx\2025.2\data\settings64.bat"
set "CONFIG=E:\github\-\fpga\hls\bilinear_fp32\hls_config.cfg"
set "PROJECT=E:\HLS\fpga_bilinear_fp32"
set "VITIS_RUN=E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat"

if not exist "%SETTINGS%" exit /b 2
if not exist "%CONFIG%" exit /b 2
if not exist "%VITIS_RUN%" exit /b 2
if not exist "%PROJECT%" mkdir "%PROJECT%" || exit /b 2
cd /d "%PROJECT%" || exit /b 2
if not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"
call "%SETTINGS%" || exit /b 1
call "%VITIS_RUN%" --mode hls --csim --config "%CONFIG%" --work_dir fpga_bilinear_fp32

exit /b %errorlevel%
