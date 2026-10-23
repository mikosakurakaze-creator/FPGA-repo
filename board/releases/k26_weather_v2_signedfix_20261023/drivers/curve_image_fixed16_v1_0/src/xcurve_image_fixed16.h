// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XCURVE_IMAGE_FIXED16_H
#define XCURVE_IMAGE_FIXED16_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xcurve_image_fixed16_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
#ifdef SDT
    char *Name;
#else
    u16 DeviceId;
#endif
    u64 Control_BaseAddress;
} XCurve_image_fixed16_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XCurve_image_fixed16;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XCurve_image_fixed16_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XCurve_image_fixed16_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XCurve_image_fixed16_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XCurve_image_fixed16_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
#ifdef SDT
int XCurve_image_fixed16_Initialize(XCurve_image_fixed16 *InstancePtr, UINTPTR BaseAddress);
XCurve_image_fixed16_Config* XCurve_image_fixed16_LookupConfig(UINTPTR BaseAddress);
#else
int XCurve_image_fixed16_Initialize(XCurve_image_fixed16 *InstancePtr, u16 DeviceId);
XCurve_image_fixed16_Config* XCurve_image_fixed16_LookupConfig(u16 DeviceId);
#endif
int XCurve_image_fixed16_CfgInitialize(XCurve_image_fixed16 *InstancePtr, XCurve_image_fixed16_Config *ConfigPtr);
#else
int XCurve_image_fixed16_Initialize(XCurve_image_fixed16 *InstancePtr, const char* InstanceName);
int XCurve_image_fixed16_Release(XCurve_image_fixed16 *InstancePtr);
#endif

void XCurve_image_fixed16_Start(XCurve_image_fixed16 *InstancePtr);
u32 XCurve_image_fixed16_IsDone(XCurve_image_fixed16 *InstancePtr);
u32 XCurve_image_fixed16_IsIdle(XCurve_image_fixed16 *InstancePtr);
u32 XCurve_image_fixed16_IsReady(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_EnableAutoRestart(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_DisableAutoRestart(XCurve_image_fixed16 *InstancePtr);

void XCurve_image_fixed16_Set_input_r(XCurve_image_fixed16 *InstancePtr, u64 Data);
u64 XCurve_image_fixed16_Get_input_r(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_Set_parameter_r(XCurve_image_fixed16 *InstancePtr, u64 Data);
u64 XCurve_image_fixed16_Get_parameter_r(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_Set_output_r(XCurve_image_fixed16 *InstancePtr, u64 Data);
u64 XCurve_image_fixed16_Get_output_r(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_Set_count(XCurve_image_fixed16 *InstancePtr, u32 Data);
u32 XCurve_image_fixed16_Get_count(XCurve_image_fixed16 *InstancePtr);

void XCurve_image_fixed16_InterruptGlobalEnable(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_InterruptGlobalDisable(XCurve_image_fixed16 *InstancePtr);
void XCurve_image_fixed16_InterruptEnable(XCurve_image_fixed16 *InstancePtr, u32 Mask);
void XCurve_image_fixed16_InterruptDisable(XCurve_image_fixed16 *InstancePtr, u32 Mask);
void XCurve_image_fixed16_InterruptClear(XCurve_image_fixed16 *InstancePtr, u32 Mask);
u32 XCurve_image_fixed16_InterruptGetEnabled(XCurve_image_fixed16 *InstancePtr);
u32 XCurve_image_fixed16_InterruptGetStatus(XCurve_image_fixed16 *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
