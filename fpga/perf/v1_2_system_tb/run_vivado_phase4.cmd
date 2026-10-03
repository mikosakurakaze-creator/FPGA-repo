@echo off
setlocal
set "PHASE=%~1"
if "%PHASE%"=="" exit /b 2
set "RUN=E:\HLS\kv260_three_module_v1_2_phase4"
set "SCRIPT=E:\github\-\fpga\scripts\vivado_three_module_v1_2_%PHASE%.tcl"
if not exist "%SCRIPT%" exit /b 3
if not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"
call "E:\Xilinx\2025.2\data\settings64.bat" || exit /b 1
cd /d "%RUN%" || exit /b 2
call "E:\Xilinx\2025.2\Vivado\bin\vivado.bat" -mode batch -source "%SCRIPT%" -log "%RUN%\%PHASE%_driver.log" -journal "%RUN%\%PHASE%_driver.jou" -notrace
exit /b %ERRORLEVEL%
