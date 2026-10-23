// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xbilinear_fixed16_buffered.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XBilinear_fixed16_buffered_CfgInitialize(XBilinear_fixed16_buffered *InstancePtr, XBilinear_fixed16_buffered_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XBilinear_fixed16_buffered_Start(XBilinear_fixed16_buffered *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL) & 0x80;
    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XBilinear_fixed16_buffered_IsDone(XBilinear_fixed16_buffered *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XBilinear_fixed16_buffered_IsIdle(XBilinear_fixed16_buffered *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XBilinear_fixed16_buffered_IsReady(XBilinear_fixed16_buffered *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XBilinear_fixed16_buffered_EnableAutoRestart(XBilinear_fixed16_buffered *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XBilinear_fixed16_buffered_DisableAutoRestart(XBilinear_fixed16_buffered *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_AP_CTRL, 0);
}

void XBilinear_fixed16_buffered_Set_parameters_lowres(XBilinear_fixed16_buffered *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_LOWRES_DATA, (u32)(Data));
    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_LOWRES_DATA + 4, (u32)(Data >> 32));
}

u64 XBilinear_fixed16_buffered_Get_parameters_lowres(XBilinear_fixed16_buffered *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_LOWRES_DATA);
    Data += (u64)XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_LOWRES_DATA + 4) << 32;
    return Data;
}

void XBilinear_fixed16_buffered_Set_parameters_fullres(XBilinear_fixed16_buffered *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_FULLRES_DATA, (u32)(Data));
    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_FULLRES_DATA + 4, (u32)(Data >> 32));
}

u64 XBilinear_fixed16_buffered_Get_parameters_fullres(XBilinear_fixed16_buffered *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_FULLRES_DATA);
    Data += (u64)XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_PARAMETERS_FULLRES_DATA + 4) << 32;
    return Data;
}

void XBilinear_fixed16_buffered_Set_input_height(XBilinear_fixed16_buffered *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_INPUT_HEIGHT_DATA, Data);
}

u32 XBilinear_fixed16_buffered_Get_input_height(XBilinear_fixed16_buffered *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_INPUT_HEIGHT_DATA);
    return Data;
}

void XBilinear_fixed16_buffered_Set_input_width(XBilinear_fixed16_buffered *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_INPUT_WIDTH_DATA, Data);
}

u32 XBilinear_fixed16_buffered_Get_input_width(XBilinear_fixed16_buffered *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_INPUT_WIDTH_DATA);
    return Data;
}

void XBilinear_fixed16_buffered_InterruptGlobalEnable(XBilinear_fixed16_buffered *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_GIE, 1);
}

void XBilinear_fixed16_buffered_InterruptGlobalDisable(XBilinear_fixed16_buffered *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_GIE, 0);
}

void XBilinear_fixed16_buffered_InterruptEnable(XBilinear_fixed16_buffered *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_IER);
    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_IER, Register | Mask);
}

void XBilinear_fixed16_buffered_InterruptDisable(XBilinear_fixed16_buffered *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_IER);
    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_IER, Register & (~Mask));
}

void XBilinear_fixed16_buffered_InterruptClear(XBilinear_fixed16_buffered *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XBilinear_fixed16_buffered_WriteReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_ISR, Mask);
}

u32 XBilinear_fixed16_buffered_InterruptGetEnabled(XBilinear_fixed16_buffered *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_IER);
}

u32 XBilinear_fixed16_buffered_InterruptGetStatus(XBilinear_fixed16_buffered *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XBilinear_fixed16_buffered_ReadReg(InstancePtr->Control_BaseAddress, XBILINEAR_FIXED16_BUFFERED_CONTROL_ADDR_ISR);
}

