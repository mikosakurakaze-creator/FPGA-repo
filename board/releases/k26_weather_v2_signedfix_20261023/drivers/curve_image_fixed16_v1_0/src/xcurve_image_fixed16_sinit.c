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
#include "xcurve_image_fixed16.h"

extern XCurve_image_fixed16_Config XCurve_image_fixed16_ConfigTable[];

#ifdef SDT
XCurve_image_fixed16_Config *XCurve_image_fixed16_LookupConfig(UINTPTR BaseAddress) {
	XCurve_image_fixed16_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XCurve_image_fixed16_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XCurve_image_fixed16_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XCurve_image_fixed16_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XCurve_image_fixed16_Initialize(XCurve_image_fixed16 *InstancePtr, UINTPTR BaseAddress) {
	XCurve_image_fixed16_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XCurve_image_fixed16_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XCurve_image_fixed16_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XCurve_image_fixed16_Config *XCurve_image_fixed16_LookupConfig(u16 DeviceId) {
	XCurve_image_fixed16_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XCURVE_IMAGE_FIXED16_NUM_INSTANCES; Index++) {
		if (XCurve_image_fixed16_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XCurve_image_fixed16_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XCurve_image_fixed16_Initialize(XCurve_image_fixed16 *InstancePtr, u16 DeviceId) {
	XCurve_image_fixed16_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XCurve_image_fixed16_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XCurve_image_fixed16_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

