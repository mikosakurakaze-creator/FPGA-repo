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
#include "xweather_frame_top.h"

extern XWeather_frame_top_Config XWeather_frame_top_ConfigTable[];

#ifdef SDT
XWeather_frame_top_Config *XWeather_frame_top_LookupConfig(UINTPTR BaseAddress) {
	XWeather_frame_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XWeather_frame_top_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XWeather_frame_top_ConfigTable[Index].Ctrl_BaseAddress == BaseAddress) {
			ConfigPtr = &XWeather_frame_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XWeather_frame_top_Initialize(XWeather_frame_top *InstancePtr, UINTPTR BaseAddress) {
	XWeather_frame_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XWeather_frame_top_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XWeather_frame_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XWeather_frame_top_Config *XWeather_frame_top_LookupConfig(u16 DeviceId) {
	XWeather_frame_top_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XWEATHER_FRAME_TOP_NUM_INSTANCES; Index++) {
		if (XWeather_frame_top_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XWeather_frame_top_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XWeather_frame_top_Initialize(XWeather_frame_top *InstancePtr, u16 DeviceId) {
	XWeather_frame_top_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XWeather_frame_top_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XWeather_frame_top_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

