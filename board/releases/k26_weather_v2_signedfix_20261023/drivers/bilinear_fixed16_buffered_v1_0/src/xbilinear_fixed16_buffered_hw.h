// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
// control
// 0x00 : Control signals
//        bit 0  - ap_start (Read/Write/COH)
//        bit 1  - ap_done (Read/COR)
//        bit 2  - ap_idle (Read)
//        bit 3  - ap_ready (Read/COR)
//        bit 7  - auto_restart (Read/Write)
//        bit 9  - interrupt (Read)
//        others - reserved
// 0x04 : Global Interrupt Enable Register
//        bit 0  - Global Interrupt Enable (Read/Write)
//        others - reserved
// 0x08 : IP Interrupt Enable Register (Read/Write)
//        bit 0 - enable ap_done interrupt (Read/Write)
//        bit 1 - enable ap_ready interrupt (Read/Write)
//        others - reserved
// 0x0c : IP Interrupt Status Register (Read/TOW)
//        bit 0 - ap_done (Read/TOW)
//        bit 1 - ap_ready (Read/TOW)
//        others - reserved
// 0x10 : Data signal of parameters_lowres
//        bit 31~0 - parameters_lowres[31:0] (Read/Write)
// 0x14 : Data signal of parameters_lowres
//        bit 31~0 - parameters_lowres[63:32] (Read/Write)
// 0x18 : reserved
// 0x1c : Data signal of parameters_fullres
//        bit 31~0 - parameters_fullres[31:0] (Read/Write)
// 0x20 : Data signal of parameters_fullres
//        bit 31~0 - parameters_fullres[63:32] (Read/Write)
// 0x24 : reserved
// 0x28 : Data signal of input_height
//        bit 31~0 - input_height[31:0] (Read/Write)
// 0x2c : reserved
// 0x30 : Data signal of input_width
//        bit 31~0 - input_width[31:0] (Read/Write)
// 0x34 : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL                 0x00
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_GIE                     0x04
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_IER                     0x08
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_ISR                     0x0c
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_LOWRES_DATA  0x10
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_BITS_PARAMETERS_LOWRES_DATA  64
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_FULLRES_DATA 0x1c
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_BITS_PARAMETERS_FULLRES_DATA 64
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_INPUT_HEIGHT_DATA       0x28
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_BITS_INPUT_HEIGHT_DATA       32
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_INPUT_WIDTH_DATA        0x30
#define XBILINEAR_FIXED16_BUFFERED_CONTROL_BITS_INPUT_WIDTH_DATA        32

