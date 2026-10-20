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
#include "xdehaze_top.h"

extern XDehaze_top_Config XDehaze_top_ConfigTable[];

#ifdef SDT
XDehaze_top_Config *XDehaze_top_LookupConfig(UINTPTR BaseAddress) {
	XDehaze_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XDehaze_top_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XDehaze_top_ConfigTable[Index].Ctrl_BaseAddress == BaseAddress) {
			ConfigPtr = &XDehaze_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDehaze_top_Initialize(XDehaze_top *InstancePtr, UINTPTR BaseAddress) {
	XDehaze_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDehaze_top_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDehaze_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XDehaze_top_Config *XDehaze_top_LookupConfig(u16 DeviceId) {
	XDehaze_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XDEHAZE_TOP_NUM_INSTANCES; Index++) {
		if (XDehaze_top_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XDehaze_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XDehaze_top_Initialize(XDehaze_top *InstancePtr, u16 DeviceId) {
	XDehaze_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XDehaze_top_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XDehaze_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

