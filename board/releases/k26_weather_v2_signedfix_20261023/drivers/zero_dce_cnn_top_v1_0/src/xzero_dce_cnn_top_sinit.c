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
#include "xzero_dce_cnn_top.h"

extern XZero_dce_cnn_top_Config XZero_dce_cnn_top_ConfigTable[];

#ifdef SDT
XZero_dce_cnn_top_Config *XZero_dce_cnn_top_LookupConfig(UINTPTR BaseAddress) {
	XZero_dce_cnn_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XZero_dce_cnn_top_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XZero_dce_cnn_top_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XZero_dce_cnn_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XZero_dce_cnn_top_Initialize(XZero_dce_cnn_top *InstancePtr, UINTPTR BaseAddress) {
	XZero_dce_cnn_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XZero_dce_cnn_top_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XZero_dce_cnn_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XZero_dce_cnn_top_Config *XZero_dce_cnn_top_LookupConfig(u16 DeviceId) {
	XZero_dce_cnn_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XZERO_DCE_CNN_TOP_NUM_INSTANCES; Index++) {
		if (XZero_dce_cnn_top_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XZero_dce_cnn_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XZero_dce_cnn_top_Initialize(XZero_dce_cnn_top *InstancePtr, u16 DeviceId) {
	XZero_dce_cnn_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XZero_dce_cnn_top_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XZero_dce_cnn_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

