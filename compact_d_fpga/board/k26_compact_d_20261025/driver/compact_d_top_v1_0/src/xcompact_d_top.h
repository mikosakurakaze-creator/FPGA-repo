// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XCOMPACT_D_TOP_H
#define XCOMPACT_D_TOP_H

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
#include "xcompact_d_top_hw.h"

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
} XCompact_d_top_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XCompact_d_top;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XCompact_d_top_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XCompact_d_top_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XCompact_d_top_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XCompact_d_top_ReadReg(BaseAddress, RegOffset) \
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
int XCompact_d_top_Initialize(XCompact_d_top *InstancePtr, UINTPTR BaseAddress);
XCompact_d_top_Config* XCompact_d_top_LookupConfig(UINTPTR BaseAddress);
#else
int XCompact_d_top_Initialize(XCompact_d_top *InstancePtr, u16 DeviceId);
XCompact_d_top_Config* XCompact_d_top_LookupConfig(u16 DeviceId);
#endif
int XCompact_d_top_CfgInitialize(XCompact_d_top *InstancePtr, XCompact_d_top_Config *ConfigPtr);
#else
int XCompact_d_top_Initialize(XCompact_d_top *InstancePtr, const char* InstanceName);
int XCompact_d_top_Release(XCompact_d_top *InstancePtr);
#endif

void XCompact_d_top_Start(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_IsDone(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_IsIdle(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_IsReady(XCompact_d_top *InstancePtr);
void XCompact_d_top_EnableAutoRestart(XCompact_d_top *InstancePtr);
void XCompact_d_top_DisableAutoRestart(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_Get_return(XCompact_d_top *InstancePtr);

void XCompact_d_top_Set_input_r(XCompact_d_top *InstancePtr, u64 Data);
u64 XCompact_d_top_Get_input_r(XCompact_d_top *InstancePtr);
void XCompact_d_top_Set_output_r(XCompact_d_top *InstancePtr, u64 Data);
u64 XCompact_d_top_Get_output_r(XCompact_d_top *InstancePtr);
void XCompact_d_top_Set_height(XCompact_d_top *InstancePtr, u32 Data);
u32 XCompact_d_top_Get_height(XCompact_d_top *InstancePtr);
void XCompact_d_top_Set_width(XCompact_d_top *InstancePtr, u32 Data);
u32 XCompact_d_top_Get_width(XCompact_d_top *InstancePtr);
void XCompact_d_top_Set_abi_cookie(XCompact_d_top *InstancePtr, u32 Data);
u32 XCompact_d_top_Get_abi_cookie(XCompact_d_top *InstancePtr);
u64 XCompact_d_top_Get_work_cycles(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_Get_work_cycles_vld(XCompact_d_top *InstancePtr);
u64 XCompact_d_top_Get_input_cycles(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_Get_input_cycles_vld(XCompact_d_top *InstancePtr);

void XCompact_d_top_InterruptGlobalEnable(XCompact_d_top *InstancePtr);
void XCompact_d_top_InterruptGlobalDisable(XCompact_d_top *InstancePtr);
void XCompact_d_top_InterruptEnable(XCompact_d_top *InstancePtr, u32 Mask);
void XCompact_d_top_InterruptDisable(XCompact_d_top *InstancePtr, u32 Mask);
void XCompact_d_top_InterruptClear(XCompact_d_top *InstancePtr, u32 Mask);
u32 XCompact_d_top_InterruptGetEnabled(XCompact_d_top *InstancePtr);
u32 XCompact_d_top_InterruptGetStatus(XCompact_d_top *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
