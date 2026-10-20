// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XDEHAZE_TOP_H
#define XDEHAZE_TOP_H

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
#include "xdehaze_top_hw.h"

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
} XDehaze_top_Config;
#endif

typedef struct {
    u64 Ctrl_BaseAddress;
    u32 IsReady;
} XDehaze_top;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XDehaze_top_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XDehaze_top_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XDehaze_top_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XDehaze_top_ReadReg(BaseAddress, RegOffset) \
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
int XDehaze_top_Initialize(XDehaze_top *InstancePtr, UINTPTR BaseAddress);
XDehaze_top_Config* XDehaze_top_LookupConfig(UINTPTR BaseAddress);
#else
int XDehaze_top_Initialize(XDehaze_top *InstancePtr, u16 DeviceId);
XDehaze_top_Config* XDehaze_top_LookupConfig(u16 DeviceId);
#endif
int XDehaze_top_CfgInitialize(XDehaze_top *InstancePtr, XDehaze_top_Config *ConfigPtr);
#else
int XDehaze_top_Initialize(XDehaze_top *InstancePtr, const char* InstanceName);
int XDehaze_top_Release(XDehaze_top *InstancePtr);
#endif

void XDehaze_top_Start(XDehaze_top *InstancePtr);
u32 XDehaze_top_IsDone(XDehaze_top *InstancePtr);
u32 XDehaze_top_IsIdle(XDehaze_top *InstancePtr);
u32 XDehaze_top_IsReady(XDehaze_top *InstancePtr);
void XDehaze_top_EnableAutoRestart(XDehaze_top *InstancePtr);
void XDehaze_top_DisableAutoRestart(XDehaze_top *InstancePtr);
u32 XDehaze_top_Get_return(XDehaze_top *InstancePtr);

void XDehaze_top_Set_input_r(XDehaze_top *InstancePtr, u64 Data);
u64 XDehaze_top_Get_input_r(XDehaze_top *InstancePtr);
void XDehaze_top_Set_output_r(XDehaze_top *InstancePtr, u64 Data);
u64 XDehaze_top_Get_output_r(XDehaze_top *InstancePtr);
void XDehaze_top_Set_scratch(XDehaze_top *InstancePtr, u64 Data);
u64 XDehaze_top_Get_scratch(XDehaze_top *InstancePtr);
void XDehaze_top_Set_height(XDehaze_top *InstancePtr, u32 Data);
u32 XDehaze_top_Get_height(XDehaze_top *InstancePtr);
void XDehaze_top_Set_width(XDehaze_top *InstancePtr, u32 Data);
u32 XDehaze_top_Get_width(XDehaze_top *InstancePtr);

void XDehaze_top_InterruptGlobalEnable(XDehaze_top *InstancePtr);
void XDehaze_top_InterruptGlobalDisable(XDehaze_top *InstancePtr);
void XDehaze_top_InterruptEnable(XDehaze_top *InstancePtr, u32 Mask);
void XDehaze_top_InterruptDisable(XDehaze_top *InstancePtr, u32 Mask);
void XDehaze_top_InterruptClear(XDehaze_top *InstancePtr, u32 Mask);
u32 XDehaze_top_InterruptGetEnabled(XDehaze_top *InstancePtr);
u32 XDehaze_top_InterruptGetStatus(XDehaze_top *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
