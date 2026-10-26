// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xcompact_d_top.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XCompact_d_top_CfgInitialize(XCompact_d_top *InstancePtr, XCompact_d_top_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XCompact_d_top_Start(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL) & 0x80;
    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XCompact_d_top_IsDone(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XCompact_d_top_IsIdle(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XCompact_d_top_IsReady(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XCompact_d_top_EnableAutoRestart(XCompact_d_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XCompact_d_top_DisableAutoRestart(XCompact_d_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_CTRL, 0);
}

u32 XCompact_d_top_Get_return(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_AP_RETURN);
    return Data;
}
void XCompact_d_top_Set_input_r(XCompact_d_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XCompact_d_top_Get_input_r(XCompact_d_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XCompact_d_top_Set_output_r(XCompact_d_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XCompact_d_top_Get_output_r(XCompact_d_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XCompact_d_top_Set_height(XCompact_d_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_HEIGHT_DATA, Data);
}

u32 XCompact_d_top_Get_height(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_HEIGHT_DATA);
    return Data;
}

void XCompact_d_top_Set_width(XCompact_d_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_WIDTH_DATA, Data);
}

u32 XCompact_d_top_Get_width(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_WIDTH_DATA);
    return Data;
}

void XCompact_d_top_Set_abi_cookie(XCompact_d_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_ABI_COOKIE_DATA, Data);
}

u32 XCompact_d_top_Get_abi_cookie(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_ABI_COOKIE_DATA);
    return Data;
}

u64 XCompact_d_top_Get_work_cycles(XCompact_d_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_WORK_CYCLES_DATA);
    Data += (u64)XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_WORK_CYCLES_DATA + 4) << 32;
    return Data;
}

u32 XCompact_d_top_Get_work_cycles_vld(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_WORK_CYCLES_CTRL);
    return Data & 0x1;
}

u64 XCompact_d_top_Get_input_cycles(XCompact_d_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_CYCLES_DATA);
    Data += (u64)XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_CYCLES_DATA + 4) << 32;
    return Data;
}

u32 XCompact_d_top_Get_input_cycles_vld(XCompact_d_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_INPUT_CYCLES_CTRL);
    return Data & 0x1;
}

void XCompact_d_top_InterruptGlobalEnable(XCompact_d_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_GIE, 1);
}

void XCompact_d_top_InterruptGlobalDisable(XCompact_d_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_GIE, 0);
}

void XCompact_d_top_InterruptEnable(XCompact_d_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_IER);
    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_IER, Register | Mask);
}

void XCompact_d_top_InterruptDisable(XCompact_d_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_IER);
    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_IER, Register & (~Mask));
}

void XCompact_d_top_InterruptClear(XCompact_d_top *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCompact_d_top_WriteReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_ISR, Mask);
}

u32 XCompact_d_top_InterruptGetEnabled(XCompact_d_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_IER);
}

u32 XCompact_d_top_InterruptGetStatus(XCompact_d_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XCompact_d_top_ReadReg(InstancePtr->Control_BaseAddress, XCOMPACT_D_TOP_CONTROL_ADDR_ISR);
}

