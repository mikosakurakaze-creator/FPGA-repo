// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xzero_dce_cnn_top.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XZero_dce_cnn_top_CfgInitialize(XZero_dce_cnn_top *InstancePtr, XZero_dce_cnn_top_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XZero_dce_cnn_top_Start(XZero_dce_cnn_top *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL) & 0x80;
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XZero_dce_cnn_top_IsDone(XZero_dce_cnn_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XZero_dce_cnn_top_IsIdle(XZero_dce_cnn_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XZero_dce_cnn_top_IsReady(XZero_dce_cnn_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XZero_dce_cnn_top_EnableAutoRestart(XZero_dce_cnn_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XZero_dce_cnn_top_DisableAutoRestart(XZero_dce_cnn_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_AP_CTRL, 0);
}

void XZero_dce_cnn_top_Set_input_q14(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_INPUT_Q14_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_INPUT_Q14_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_input_q14(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_INPUT_Q14_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_INPUT_Q14_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_Set_weights_int8(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHTS_INT8_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHTS_INT8_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_weights_int8(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHTS_INT8_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHTS_INT8_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_Set_bias_int32(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_BIAS_INT32_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_BIAS_INT32_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_bias_int32(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_BIAS_INT32_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_BIAS_INT32_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_Set_weight_frac(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHT_FRAC_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHT_FRAC_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_weight_frac(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHT_FRAC_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WEIGHT_FRAC_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_Set_tanh_lut_q15(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_TANH_LUT_Q15_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_TANH_LUT_Q15_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_tanh_lut_q15(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_TANH_LUT_Q15_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_TANH_LUT_Q15_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_Set_a_low_q14(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_A_LOW_Q14_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_A_LOW_Q14_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_a_low_q14(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_A_LOW_Q14_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_A_LOW_Q14_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_Set_workspace_int16(XZero_dce_cnn_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WORKSPACE_INT16_DATA, (u32)(Data));
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WORKSPACE_INT16_DATA + 4, (u32)(Data >> 32));
}

u64 XZero_dce_cnn_top_Get_workspace_int16(XZero_dce_cnn_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WORKSPACE_INT16_DATA);
    Data += (u64)XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_WORKSPACE_INT16_DATA + 4) << 32;
    return Data;
}

void XZero_dce_cnn_top_InterruptGlobalEnable(XZero_dce_cnn_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_GIE, 1);
}

void XZero_dce_cnn_top_InterruptGlobalDisable(XZero_dce_cnn_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_GIE, 0);
}

void XZero_dce_cnn_top_InterruptEnable(XZero_dce_cnn_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_IER);
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_IER, Register | Mask);
}

void XZero_dce_cnn_top_InterruptDisable(XZero_dce_cnn_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_IER);
    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_IER, Register & (~Mask));
}

void XZero_dce_cnn_top_InterruptClear(XZero_dce_cnn_top *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XZero_dce_cnn_top_WriteReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_ISR, Mask);
}

u32 XZero_dce_cnn_top_InterruptGetEnabled(XZero_dce_cnn_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_IER);
}

u32 XZero_dce_cnn_top_InterruptGetStatus(XZero_dce_cnn_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XZero_dce_cnn_top_ReadReg(InstancePtr->Control_BaseAddress, XZERO_DCE_CNN_TOP_CONTROL_ADDR_ISR);
}

