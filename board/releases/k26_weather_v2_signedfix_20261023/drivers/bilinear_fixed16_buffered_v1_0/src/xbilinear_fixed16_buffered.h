// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XBILINEAR_FIXED16_BUFFERED_H
#define XBILINEAR_FIXED16_BUFFERED_H

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
#include "xbilinear_fixed16_buffered_hw.h"

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
} XBilinear_fixed16_buffered_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XBilinear_fixed16_buffered;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XBilinear_fixed16_buffered_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XBilinear_fixed16_buffered_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XBilinear_fixed16_buffered_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XBilinear_fixed16_buffered_ReadReg(BaseAddress, RegOffset) \
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
int XBilinear_fixed16_buffered_Initialize(XBilinear_fixed16_buffered *InstancePtr, UINTPTR BaseAddress);
XBilinear_fixed16_buffered_Config* XBilinear_fixed16_buffered_LookupConfig(UINTPTR BaseAddress);
#else
int XBilinear_fixed16_buffered_Initialize(XBilinear_fixed16_buffered *InstancePtr, u16 DeviceId);
XBilinear_fixed16_buffered_Config* XBilinear_fixed16_buffered_LookupConfig(u16 DeviceId);
#endif
int XBilinear_fixed16_buffered_CfgInitialize(XBilinear_fixed16_buffered *InstancePtr, XBilinear_fixed16_buffered_Config *ConfigPtr);
#else
int XBilinear_fixed16_buffered_Initialize(XBilinear_fixed16_buffered *InstancePtr, const char* InstanceName);
int XBilinear_fixed16_buffered_Release(XBilinear_fixed16_buffered *InstancePtr);
#endif

void XBilinear_fixed16_buffered_Start(XBilinear_fixed16_buffered *InstancePtr);
u32 XBilinear_fixed16_buffered_IsDone(XBilinear_fixed16_buffered *InstancePtr);
u32 XBilinear_fixed16_buffered_IsIdle(XBilinear_fixed16_buffered *InstancePtr);
u32 XBilinear_fixed16_buffered_IsReady(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_EnableAutoRestart(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_DisableAutoRestart(XBilinear_fixed16_buffered *InstancePtr);

void XBilinear_fixed16_buffered_Set_parameters_lowres(XBilinear_fixed16_buffered *InstancePtr, u64 Data);
u64 XBilinear_fixed16_buffered_Get_parameters_lowres(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_Set_parameters_fullres(XBilinear_fixed16_buffered *InstancePtr, u64 Data);
u64 XBilinear_fixed16_buffered_Get_parameters_fullres(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_Set_input_height(XBilinear_fixed16_buffered *InstancePtr, u32 Data);
u32 XBilinear_fixed16_buffered_Get_input_height(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_Set_input_width(XBilinear_fixed16_buffered *InstancePtr, u32 Data);
u32 XBilinear_fixed16_buffered_Get_input_width(XBilinear_fixed16_buffered *InstancePtr);

void XBilinear_fixed16_buffered_InterruptGlobalEnable(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_InterruptGlobalDisable(XBilinear_fixed16_buffered *InstancePtr);
void XBilinear_fixed16_buffered_InterruptEnable(XBilinear_fixed16_buffered *InstancePtr, u32 Mask);
void XBilinear_fixed16_buffered_InterruptDisable(XBilinear_fixed16_buffered *InstancePtr, u32 Mask);
void XBilinear_fixed16_buffered_InterruptClear(XBilinear_fixed16_buffered *InstancePtr, u32 Mask);
u32 XBilinear_fixed16_buffered_InterruptGetEnabled(XBilinear_fixed16_buffered *InstancePtr);
u32 XBilinear_fixed16_buffered_InterruptGetStatus(XBilinear_fixed16_buffered *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
