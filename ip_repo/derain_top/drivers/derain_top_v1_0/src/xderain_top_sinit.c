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
#include "xderain_top.h"

extern XDerain_top_Config XDerain_top_ConfigTable[];

#ifdef SDT
XDerain_top_Config *XDerain_top_LookupConfig(UINTPTR BaseAddress) {
	XDerain_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XDerain_top_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XDerain_top_ConfigTable[Index].Ctrl_BaseAddress == BaseAddress) {
			ConfigPtr = &XDerain_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDerain_top_Initialize(XDerain_top *InstancePtr, UINTPTR BaseAddress) {
	XDerain_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDerain_top_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDerain_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XDerain_top_Config *XDerain_top_LookupConfig(u16 DeviceId) {
	XDerain_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XDERAIN_TOP_NUM_INSTANCES; Index++) {
		if (XDerain_top_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XDerain_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDerain_top_Initialize(XDerain_top *InstancePtr, u16 DeviceId) {
	XDerain_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDerain_top_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDerain_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

