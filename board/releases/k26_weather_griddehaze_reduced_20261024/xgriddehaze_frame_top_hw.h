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
// 0x30 : Data signal of scratch
//        bit 31~0 - scratch[31:0] (Read/Write)
// 0x34 : Data signal of scratch
//        bit 31~0 - scratch[63:32] (Read/Write)
// 0x38 : reserved
// 0x3c : Data signal of parameters
//        bit 31~0 - parameters[31:0] (Read/Write)
// 0x40 : Data signal of parameters
//        bit 31~0 - parameters[63:32] (Read/Write)
// 0x44 : reserved
// 0x48 : Data signal of layout
//        bit 31~0 - layout[31:0] (Read/Write)
// 0x4c : Data signal of layout
//        bit 31~0 - layout[63:32] (Read/Write)
// 0x50 : reserved
// 0x54 : Data signal of input_bytes
//        bit 31~0 - input_bytes[31:0] (Read/Write)
// 0x58 : reserved
// 0x5c : Data signal of output_bytes
//        bit 31~0 - output_bytes[31:0] (Read/Write)
// 0x60 : reserved
// 0x64 : Data signal of scratch_bytes
//        bit 31~0 - scratch_bytes[31:0] (Read/Write)
// 0x68 : reserved
// 0x6c : Data signal of parameter_bytes
//        bit 31~0 - parameter_bytes[31:0] (Read/Write)
// 0x70 : reserved
// 0x74 : Data signal of layout_bytes
//        bit 31~0 - layout_bytes[31:0] (Read/Write)
// 0x78 : reserved
// 0x7c : Data signal of height
//        bit 31~0 - height[31:0] (Read/Write)
// 0x80 : reserved
// 0x84 : Data signal of width
//        bit 31~0 - width[31:0] (Read/Write)
// 0x88 : reserved
// 0x8c : Data signal of model_id
//        bit 31~0 - model_id[31:0] (Read/Write)
// 0x90 : reserved
// 0x94 : Data signal of abi
//        bit 31~0 - abi[31:0] (Read/Write)
// 0x98 : reserved
// 0x9c : Data signal of completed_nodes
//        bit 31~0 - completed_nodes[31:0] (Read)
// 0xa0 : Control signal of completed_nodes
//        bit 0  - completed_nodes_ap_vld (Read/COR)
//        others - reserved
// 0xac : Data signal of hardware_model
//        bit 31~0 - hardware_model[31:0] (Read)
// 0xb0 : Control signal of hardware_model
//        bit 0  - hardware_model_ap_vld (Read/COR)
//        others - reserved
// 0xbc : Data signal of hardware_abi
//        bit 31~0 - hardware_abi[31:0] (Read)
// 0xc0 : Control signal of hardware_abi
//        bit 0  - hardware_abi_ap_vld (Read/COR)
//        others - reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_AP_CTRL              0x00
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_GIE                  0x04
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_IER                  0x08
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_ISR                  0x0c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_AP_RETURN            0x10
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_AP_RETURN            32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_INPUT_R_DATA         0x18
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_INPUT_R_DATA         64
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_OUTPUT_R_DATA        0x24
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_OUTPUT_R_DATA        64
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_SCRATCH_DATA         0x30
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_SCRATCH_DATA         64
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_PARAMETERS_DATA      0x3c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_PARAMETERS_DATA      64
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_LAYOUT_DATA          0x48
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_LAYOUT_DATA          64
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_INPUT_BYTES_DATA     0x54
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_INPUT_BYTES_DATA     32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_OUTPUT_BYTES_DATA    0x5c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_OUTPUT_BYTES_DATA    32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_SCRATCH_BYTES_DATA   0x64
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_SCRATCH_BYTES_DATA   32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_PARAMETER_BYTES_DATA 0x6c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_PARAMETER_BYTES_DATA 32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_LAYOUT_BYTES_DATA    0x74
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_LAYOUT_BYTES_DATA    32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_HEIGHT_DATA          0x7c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_HEIGHT_DATA          32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_WIDTH_DATA           0x84
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_WIDTH_DATA           32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_MODEL_ID_DATA        0x8c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_MODEL_ID_DATA        32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_ABI_DATA             0x94
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_ABI_DATA             32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_COMPLETED_NODES_DATA 0x9c
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_COMPLETED_NODES_DATA 32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_COMPLETED_NODES_CTRL 0xa0
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_HARDWARE_MODEL_DATA  0xac
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_HARDWARE_MODEL_DATA  32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_HARDWARE_MODEL_CTRL  0xb0
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_HARDWARE_ABI_DATA    0xbc
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_BITS_HARDWARE_ABI_DATA    32
#define XGRIDDEHAZE_FRAME_TOP_CONTROL_ADDR_HARDWARE_ABI_CTRL    0xc0

