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
// 0x10 : Data signal of ap_return
//        bit 31~0 - ap_return[31:0] (Read)
// 0x18 : Data signal of input_r
//        bit 31~0 - input_r[31:0] (Read/Write)
// 0x1c : Data signal of input_r
//        bit 31~0 - input_r[63:32] (Read/Write)
// 0x20 : reserved
// 0x24 : Data signal of output_r
//        bit 31~0 - output_r[31:0] (Read/Write)
// 0x28 : Data signal of output_r
//        bit 31~0 - output_r[63:32] (Read/Write)
// 0x2c : reserved
// 0x30 : Data signal of height
//        bit 31~0 - height[31:0] (Read/Write)
// 0x34 : reserved
// 0x38 : Data signal of width
//        bit 31~0 - width[31:0] (Read/Write)
// 0x3c : reserved
// 0x40 : Data signal of abi_cookie
//        bit 31~0 - abi_cookie[31:0] (Read/Write)
// 0x44 : reserved
// 0x48 : Data signal of work_cycles
//        bit 31~0 - work_cycles[31:0] (Read)
// 0x4c : Data signal of work_cycles
//        bit 31~0 - work_cycles[63:32] (Read)
// 0x50 : Control signal of work_cycles
//        bit 0  - work_cycles_ap_vld (Read/COR)
//        others - reserved
// 0x58 : Data signal of input_cycles
//        bit 31~0 - input_cycles[31:0] (Read)
// 0x5c : Data signal of input_cycles
//        bit 31~0 - input_cycles[63:32] (Read)
// 0x60 : Control signal of input_cycles
//        bit 0  - input_cycles_ap_vld (Read/COR)
//        others - reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL           0x00
#define XCOMPACT_D_TOP_CONTROL_ADDR_GIE               0x04
#define XCOMPACT_D_TOP_CONTROL_ADDR_IER               0x08
#define XCOMPACT_D_TOP_CONTROL_ADDR_ISR               0x0c
#define XCOMPACT_D_TOP_CONTROL_ADDR_AP_RETURN         0x10
#define XCOMPACT_D_TOP_CONTROL_BITS_AP_RETURN         32
#define XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_R_DATA      0x18
#define XCOMPACT_D_TOP_CONTROL_BITS_INPUT_R_DATA      64
#define XCOMPACT_D_TOP_CONTROL_ADDR_OUTPUT_R_DATA     0x24
#define XCOMPACT_D_TOP_CONTROL_BITS_OUTPUT_R_DATA     64
#define XCOMPACT_D_TOP_CONTROL_ADDR_HEIGHT_DATA       0x30
#define XCOMPACT_D_TOP_CONTROL_BITS_HEIGHT_DATA       32
#define XCOMPACT_D_TOP_CONTROL_ADDR_WIDTH_DATA        0x38
#define XCOMPACT_D_TOP_CONTROL_BITS_WIDTH_DATA        32
#define XCOMPACT_D_TOP_CONTROL_ADDR_ABI_COOKIE_DATA   0x40
#define XCOMPACT_D_TOP_CONTROL_BITS_ABI_COOKIE_DATA   32
#define XCOMPACT_D_TOP_CONTROL_ADDR_WORK_CYCLES_DATA  0x48
#define XCOMPACT_D_TOP_CONTROL_BITS_WORK_CYCLES_DATA  64
#define XCOMPACT_D_TOP_CONTROL_ADDR_WORK_CYCLES_CTRL  0x50
#define XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_CYCLES_DATA 0x58
#define XCOMPACT_D_TOP_CONTROL_BITS_INPUT_CYCLES_DATA 64
#define XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_CYCLES_CTRL 0x60

