// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#ifdef SDT
#include "xparameters.h"
#endif
#include "xbilinear_fixed16_buffered.h"

extern XBilinear_fixed16_buffered_Config XBilinear_fixed16_buffered_ConfigTable[];

#ifdef SDT
XBilinear_fixed16_buffered_Config *XBilinear_fixed16_buffered_LookupConfig(UINTPTR BaseAddress) {
	XBilinear_fixed16_buffered_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XBilinear_fixed16_buffered_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XBilinear_fixed16_buffered_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XBilinear_fixed16_buffered_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XBilinear_fixed16_buffered_Initialize(XBilinear_fixed16_buffered *InstancePtr, UINTPTR BaseAddress) {
	XBilinear_fixed16_buffered_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XBilinear_fixed16_buffered_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XBilinear_fixed16_buffered_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XBilinear_fixed16_buffered_Config *XBilinear_fixed16_buffered_LookupConfig(u16 DeviceId) {
	XBilinear_fixed16_buffered_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XBILINEAR_FIXED16_BUFFERED_NUM_INSTANCES; Index++) {
		if (XBilinear_fixed16_buffered_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XBilinear_fixed16_buffered_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XBilinear_fixed16_buffered_Initialize(XBilinear_fixed16_buffered *InstancePtr, u16 DeviceId) {
	XBilinear_fixed16_buffered_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XBilinear_fixed16_buffered_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XBilinear_fixed16_buffered_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

