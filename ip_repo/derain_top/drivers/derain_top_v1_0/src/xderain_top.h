// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XDERAIN_TOP_H
#define XDERAIN_TOP_H

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
#include "xderain_top_hw.h"

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
    u64 Ctrl_BaseAddress;
} XDerain_top_Config;
#endif

typedef struct {
    u64 Ctrl_BaseAddress;
    u32 IsReady;
} XDerain_top;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XDerain_top_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XDerain_top_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XDerain_top_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XDerain_top_ReadReg(BaseAddress, RegOffset) \
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
int XDerain_top_Initialize(XDerain_top *InstancePtr, UINTPTR BaseAddress);
XDerain_top_Config* XDerain_top_LookupConfig(UINTPTR BaseAddress);
#else
int XDerain_top_Initialize(XDerain_top *InstancePtr, u16 DeviceId);
XDerain_top_Config* XDerain_top_LookupConfig(u16 DeviceId);
#endif
int XDerain_top_CfgInitialize(XDerain_top *InstancePtr, XDerain_top_Config *ConfigPtr);
#else
int XDerain_top_Initialize(XDerain_top *InstancePtr, const char* InstanceName);
int XDerain_top_Release(XDerain_top *InstancePtr);
#endif

void XDerain_top_Start(XDerain_top *InstancePtr);
u32 XDerain_top_IsDone(XDerain_top *InstancePtr);
u32 XDerain_top_IsIdle(XDerain_top *InstancePtr);
u32 XDerain_top_IsReady(XDerain_top *InstancePtr);
void XDerain_top_EnableAutoRestart(XDerain_top *InstancePtr);
void XDerain_top_DisableAutoRestart(XDerain_top *InstancePtr);
u32 XDerain_top_Get_return(XDerain_top *InstancePtr);

void XDerain_top_Set_input_r(XDerain_top *InstancePtr, u64 Data);
u64 XDerain_top_Get_input_r(XDerain_top *InstancePtr);
void XDerain_top_Set_output_r(XDerain_top *InstancePtr, u64 Data);
u64 XDerain_top_Get_output_r(XDerain_top *InstancePtr);
void XDerain_top_Set_scratch(XDerain_top *InstancePtr, u64 Data);
u64 XDerain_top_Get_scratch(XDerain_top *InstancePtr);
void XDerain_top_Set_height(XDerain_top *InstancePtr, u32 Data);
u32 XDerain_top_Get_height(XDerain_top *InstancePtr);
void XDerain_top_Set_width(XDerain_top *InstancePtr, u32 Data);
u32 XDerain_top_Get_width(XDerain_top *InstancePtr);

void XDerain_top_InterruptGlobalEnable(XDerain_top *InstancePtr);
void XDerain_top_InterruptGlobalDisable(XDerain_top *InstancePtr);
void XDerain_top_InterruptEnable(XDerain_top *InstancePtr, u32 Mask);
void XDerain_top_InterruptDisable(XDerain_top *InstancePtr, u32 Mask);
void XDerain_top_InterruptClear(XDerain_top *InstancePtr, u32 Mask);
u32 XDerain_top_InterruptGetEnabled(XDerain_top *InstancePtr);
u32 XDerain_top_InterruptGetStatus(XDerain_top *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
