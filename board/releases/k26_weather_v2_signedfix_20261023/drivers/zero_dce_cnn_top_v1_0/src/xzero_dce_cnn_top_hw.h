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
// 0x10 : Data signal of input_q14
//        bit 31~0 - input_q14[31:0] (Read/Write)
// 0x14 : Data signal of input_q14
//        bit 31~0 - input_q14[63:32] (Read/Write)
// 0x18 : reserved
// 0x1c : Data signal of weights_int8
//        bit 31~0 - weights_int8[31:0] (Read/Write)
// 0x20 : Data signal of weights_int8
//        bit 31~0 - weights_int8[63:32] (Read/Write)
// 0x24 : reserved
// 0x28 : Data signal of bias_int32
//        bit 31~0 - bias_int32[31:0] (Read/Write)
// 0x2c : Data signal of bias_int32
//        bit 31~0 - bias_int32[63:32] (Read/Write)
// 0x30 : reserved
// 0x34 : Data signal of weight_frac
//        bit 31~0 - weight_frac[31:0] (Read/Write)
// 0x38 : Data signal of weight_frac
//        bit 31~0 - weight_frac[63:32] (Read/Write)
// 0x3c : reserved
// 0x40 : Data signal of tanh_lut_q15
//        bit 31~0 - tanh_lut_q15[31:0] (Read/Write)
// 0x44 : Data signal of tanh_lut_q15
//        bit 31~0 - tanh_lut_q15[63:32] (Read/Write)
// 0x48 : reserved
// 0x4c : Data signal of a_low_q14
//        bit 31~0 - a_low_q14[31:0] (Read/Write)
// 0x50 : Data signal of a_low_q14
//        bit 31~0 - a_low_q14[63:32] (Read/Write)
// 0x54 : reserved
// 0x58 : Data signal of workspace_int16
//        bit 31~0 - workspace_int16[31:0] (Read/Write)
// 0x5c : Data signal of workspace_int16
//        bit 31~0 - workspace_int16[63:32] (Read/Write)
// 0x60 : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL              0x00
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_GIE                  0x04
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_IER                  0x08
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_ISR                  0x0c
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_INPUT_Q14_DATA       0x10
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_INPUT_Q14_DATA       64
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHTS_INT8_DATA    0x1c
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_WEIGHTS_INT8_DATA    64
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_BIAS_INT32_DATA      0x28
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_BIAS_INT32_DATA      64
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHT_FRAC_DATA     0x34
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_WEIGHT_FRAC_DATA     64
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_TANH_LUT_Q15_DATA    0x40
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_TANH_LUT_Q15_DATA    64
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_A_LOW_Q14_DATA       0x4c
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_A_LOW_Q14_DATA       64
#define XZERO_DCE_CNN_TOP_CONTROL_ADDR_WORKSPACE_INT16_DATA 0x58
#define XZERO_DCE_CNN_TOP_CONTROL_BITS_WORKSPACE_INT16_DATA 64

