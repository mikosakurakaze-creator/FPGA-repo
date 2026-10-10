@echo off
setlocal
set "SETTINGS=E:\Xilinx\2025.2\data\settings64.bat"
set "CONFIG=E:\github\-\fpga\hls\curve_image_fixed16\hls_config.cfg"
set "PROJECT=E:\HLS\fpga_curve_fixed16"
set "VITIS_COMPILE=E:\Xilinx\2025.2\Vitis\bin\v++.bat"

if not exist "%SETTINGS%" exit /b 2
if not exist "%CONFIG%" exit /b 2
if not exist "%VITIS_COMPILE%" exit /b 2
if not exist "%PROJECT%" mkdir "%PROJECT%" || exit /b 2
cd /d "%PROJECT%" || exit /b 2
if not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"
call "%SETTINGS%" || exit /b 1
call "%VITIS_COMPILE%" -c --mode hls --config "%CONFIG%" --work_dir fpga_curve_fixed16
exit /b %errorlevel%
