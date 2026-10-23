// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xweather_frame_top.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XWeather_frame_top_CfgInitialize(XWeather_frame_top *InstancePtr, XWeather_frame_top_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Ctrl_BaseAddress = ConfigPtr->Ctrl_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XWeather_frame_top_Start(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL) & 0x80;
    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XWeather_frame_top_IsDone(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XWeather_frame_top_IsIdle(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XWeather_frame_top_IsReady(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XWeather_frame_top_EnableAutoRestart(XWeather_frame_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL, 0x80);
}

void XWeather_frame_top_DisableAutoRestart(XWeather_frame_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_CTRL, 0);
}

u32 XWeather_frame_top_Get_return(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_AP_RETURN);
    return Data;
}
void XWeather_frame_top_Set_input_r(XWeather_frame_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_INPUT_R_DATA, (u32)(Data));
    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XWeather_frame_top_Get_input_r(XWeather_frame_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_INPUT_R_DATA);
    Data += (u64)XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XWeather_frame_top_Set_output_r(XWeather_frame_top *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XWeather_frame_top_Get_output_r(XWeather_frame_top *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XWeather_frame_top_Set_height(XWeather_frame_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_HEIGHT_DATA, Data);
}

u32 XWeather_frame_top_Get_height(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_HEIGHT_DATA);
    return Data;
}

void XWeather_frame_top_Set_width(XWeather_frame_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_WIDTH_DATA, Data);
}

u32 XWeather_frame_top_Get_width(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_WIDTH_DATA);
    return Data;
}

void XWeather_frame_top_Set_task_r(XWeather_frame_top *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_TASK_R_DATA, Data);
}

u32 XWeather_frame_top_Get_task_r(XWeather_frame_top *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_TASK_R_DATA);
    return Data;
}

void XWeather_frame_top_InterruptGlobalEnable(XWeather_frame_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_GIE, 1);
}

void XWeather_frame_top_InterruptGlobalDisable(XWeather_frame_top *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_GIE, 0);
}

void XWeather_frame_top_InterruptEnable(XWeather_frame_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_IER);
    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_IER, Register | Mask);
}

void XWeather_frame_top_InterruptDisable(XWeather_frame_top *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_IER);
    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_IER, Register & (~Mask));
}

void XWeather_frame_top_InterruptClear(XWeather_frame_top *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XWeather_frame_top_WriteReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_ISR, Mask);
}

u32 XWeather_frame_top_InterruptGetEnabled(XWeather_frame_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_IER);
}

u32 XWeather_frame_top_InterruptGetStatus(XWeather_frame_top *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XWeather_frame_top_ReadReg(InstancePtr->Ctrl_BaseAddress, XWEATHER_FRAME_TOP_CTRL_ADDR_ISR);
}

