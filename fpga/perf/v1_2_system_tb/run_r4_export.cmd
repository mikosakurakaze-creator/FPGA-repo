@echo off
setlocal
set "RUN=E:\HLS\kv260_three_module_v1_2_phase4"
if exist "%RUN%\cnn_r4_export" exit /b 4
if not defined PROCESSOR_ARCHITECTURE set "PROCESSOR_ARCHITECTURE=AMD64"
call "E:\Xilinx\2025.2\data\settings64.bat" || exit /b 1
cd /d "%RUN%" || exit /b 2
call "E:\Xilinx\2025.2\Vitis\bin\vitis-run.bat" --mode hls --csim --config r4_hls_config.cfg --work_dir cnn_r4_export || exit /b 1
findstr /c:"CSim done with 0 errors." cnn_r4_export\hls\csim\report\zero_dce_cnn_top_csim.log >nul || exit /b 5
findstr /c:"mismatches=0" cnn_r4_export\hls\csim\report\zero_dce_cnn_top_csim.log >nul || exit /b 6
call "E:\Xilinx\2025.2\Vitis\bin\v++.bat" -c --mode hls --config r4_hls_config.cfg --work_dir cnn_r4_export || exit /b 1
if not exist cnn_r4_export\hls\syn\report\zero_dce_cnn_top_csynth.xml exit /b 7
if not exist cnn_r4_export\hls\impl\ip\component.xml exit /b 8
if not exist cnn_r4_export\zero_dce_cnn_top.zip exit /b 9
