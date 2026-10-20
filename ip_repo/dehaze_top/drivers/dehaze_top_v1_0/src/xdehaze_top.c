// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xdehaze_top.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XDehaze_top_CfgInitialize(XDehaze_top *InstancePtr, XDehaze_top_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Ctrl_BaseAddress = ConfigPtr->Ctrl_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XDehaze_top_Start(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL) & 0x80;
    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XDehaze_top_IsDone(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XDehaze_top_IsIdle(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XDehaze_top_IsReady(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XDehaze_top_EnableAutoRestart(XDehaze_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL, 0x80);
}

void XDehaze_top_DisableAutoRestart(XDehaze_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_CTRL, 0);
}

u32 XDehaze_top_Get_return(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_AP_RETURN);
    return Data;
}
void XDehaze_top_Set_input_r(XDehaze_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_INPUT_R_DATA, (u32)(Data));
    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XDehaze_top_Get_input_r(XDehaze_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_INPUT_R_DATA);
    Data += (u64)XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XDehaze_top_Set_output_r(XDehaze_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XDehaze_top_Get_output_r(XDehaze_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XDehaze_top_Set_scratch(XDehaze_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_SCRATCH_DATA, (u32)(Data));
    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_SCRATCH_DATA + 4, (u32)(Data >> 32));
}

u64 XDehaze_top_Get_scratch(XDehaze_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_SCRATCH_DATA);
    Data += (u64)XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_SCRATCH_DATA + 4) << 32;
    return Data;
}

void XDehaze_top_Set_height(XDehaze_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_HEIGHT_DATA, Data);
}

u32 XDehaze_top_Get_height(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_HEIGHT_DATA);
    return Data;
}

void XDehaze_top_Set_width(XDehaze_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_WIDTH_DATA, Data);
}

u32 XDehaze_top_Get_width(XDehaze_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_WIDTH_DATA);
    return Data;
}

void XDehaze_top_InterruptGlobalEnable(XDehaze_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_GIE, 1);
}

void XDehaze_top_InterruptGlobalDisable(XDehaze_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_GIE, 0);
}

void XDehaze_top_InterruptEnable(XDehaze_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_IER);
    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_IER, Register | Mask);
}

void XDehaze_top_InterruptDisable(XDehaze_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_IER);
    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_IER, Register & (~Mask));
}

void XDehaze_top_InterruptClear(XDehaze_top *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDehaze_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_ISR, Mask);
}

u32 XDehaze_top_InterruptGetEnabled(XDehaze_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_IER);
}

u32 XDehaze_top_InterruptGetStatus(XDehaze_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDehaze_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDEHAZE_TOP_CTRL_ADDR_ISR);
}

