// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xderain_top.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XDerain_top_CfgInitialize(XDerain_top *InstancePtr, XDerain_top_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Ctrl_BaseAddress = ConfigPtr->Ctrl_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XDerain_top_Start(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL) & 0x80;
    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XDerain_top_IsDone(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XDerain_top_IsIdle(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XDerain_top_IsReady(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XDerain_top_EnableAutoRestart(XDerain_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL, 0x80);
}

void XDerain_top_DisableAutoRestart(XDerain_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_CTRL, 0);
}

u32 XDerain_top_Get_return(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_AP_RETURN);
    return Data;
}
void XDerain_top_Set_input_r(XDerain_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_INPUT_R_DATA, (u32)(Data));
    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XDerain_top_Get_input_r(XDerain_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_INPUT_R_DATA);
    Data += (u64)XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XDerain_top_Set_output_r(XDerain_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XDerain_top_Get_output_r(XDerain_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XDerain_top_Set_scratch(XDerain_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_SCRATCH_DATA, (u32)(Data));
    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_SCRATCH_DATA + 4, (u32)(Data >> 32));
}

u64 XDerain_top_Get_scratch(XDerain_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_SCRATCH_DATA);
    Data += (u64)XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_SCRATCH_DATA + 4) << 32;
    return Data;
}

void XDerain_top_Set_height(XDerain_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_HEIGHT_DATA, Data);
}

u32 XDerain_top_Get_height(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_HEIGHT_DATA);
    return Data;
}

void XDerain_top_Set_width(XDerain_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_WIDTH_DATA, Data);
}

u32 XDerain_top_Get_width(XDerain_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_WIDTH_DATA);
    return Data;
}

void XDerain_top_InterruptGlobalEnable(XDerain_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_GIE, 1);
}

void XDerain_top_InterruptGlobalDisable(XDerain_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_GIE, 0);
}

void XDerain_top_InterruptEnable(XDerain_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_IER);
    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_IER, Register | Mask);
}

void XDerain_top_InterruptDisable(XDerain_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_IER);
    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_IER, Register & (~Mask));
}

void XDerain_top_InterruptClear(XDerain_top *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XDerain_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_ISR, Mask);
}

u32 XDerain_top_InterruptGetEnabled(XDerain_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_IER);
}

u32 XDerain_top_InterruptGetStatus(XDerain_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XDerain_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XDERAIN_TOP_CTRL_ADDR_ISR);
}

