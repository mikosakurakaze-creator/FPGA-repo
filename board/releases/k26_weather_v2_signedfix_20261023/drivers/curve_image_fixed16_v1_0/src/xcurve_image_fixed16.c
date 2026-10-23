// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xcurve_image_fixed16.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XCurve_image_fixed16_CfgInitialize(XCurve_image_fixed16 *InstancePtr, XCurve_image_fixed16_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XCurve_image_fixed16_Start(XCurve_image_fixed16 *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL) & 0x80;
    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XCurve_image_fixed16_IsDone(XCurve_image_fixed16 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XCurve_image_fixed16_IsIdle(XCurve_image_fixed16 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XCurve_image_fixed16_IsReady(XCurve_image_fixed16 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XCurve_image_fixed16_EnableAutoRestart(XCurve_image_fixed16 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XCurve_image_fixed16_DisableAutoRestart(XCurve_image_fixed16 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_AP_CTRL, 0);
}

void XCurve_image_fixed16_Set_input_r(XCurve_image_fixed16 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XCurve_image_fixed16_Get_input_r(XCurve_image_fixed16 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XCurve_image_fixed16_Set_parameter_r(XCurve_image_fixed16 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_PARAMETER_R_DATA, (u32)(Data));
    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_PARAMETER_R_DATA + 4, (u32)(Data >> 32));
}

u64 XCurve_image_fixed16_Get_parameter_r(XCurve_image_fixed16 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_PARAMETER_R_DATA);
    Data += (u64)XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_PARAMETER_R_DATA + 4) << 32;
    return Data;
}

void XCurve_image_fixed16_Set_output_r(XCurve_image_fixed16 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XCurve_image_fixed16_Get_output_r(XCurve_image_fixed16 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XCurve_image_fixed16_Set_count(XCurve_image_fixed16 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_COUNT_DATA, Data);
}

u32 XCurve_image_fixed16_Get_count(XCurve_image_fixed16 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_COUNT_DATA);
    return Data;
}

void XCurve_image_fixed16_InterruptGlobalEnable(XCurve_image_fixed16 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_GIE, 1);
}

void XCurve_image_fixed16_InterruptGlobalDisable(XCurve_image_fixed16 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_GIE, 0);
}

void XCurve_image_fixed16_InterruptEnable(XCurve_image_fixed16 *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_IER);
    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_IER, Register | Mask);
}

void XCurve_image_fixed16_InterruptDisable(XCurve_image_fixed16 *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_IER);
    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_IER, Register & (~Mask));
}

void XCurve_image_fixed16_InterruptClear(XCurve_image_fixed16 *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XCurve_image_fixed16_WriteReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_ISR, Mask);
}

u32 XCurve_image_fixed16_InterruptGetEnabled(XCurve_image_fixed16 *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_IER);
}

u32 XCurve_image_fixed16_InterruptGetStatus(XCurve_image_fixed16 *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XCurve_image_fixed16_ReadReg(InstancePtr->Control_BaseAddress, XCURVE_IMAGE_FIXED16_CONTROL_ADDR_ISR);
}

