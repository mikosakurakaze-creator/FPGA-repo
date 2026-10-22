// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XWEATHER_FRAME_TOP_H
#define XWEATHER_FRAME_TOP_H

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
#include "xweather_frame_top_hw.h"

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
} XWeather_frame_top_Config;
#endif

typedef struct {
    u64 Ctrl_BaseAddress;
    u32 IsReady;
} XWeather_frame_top;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XWeather_frame_top_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XWeather_frame_top_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XWeather_frame_top_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XWeather_frame_top_ReadReg(BaseAddress, RegOffset) \
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
int XWeather_frame_top_Initialize(XWeather_frame_top *InstancePtr, UINTPTR BaseAddress);
XWeather_frame_top_Config* XWeather_frame_top_LookupConfig(UINTPTR BaseAddress);
#else
int XWeather_frame_top_Initialize(XWeather_frame_top *InstancePtr, u16 DeviceId);
XWeather_frame_top_Config* XWeather_frame_top_LookupConfig(u16 DeviceId);
#endif
int XWeather_frame_top_CfgInitialize(XWeather_frame_top *InstancePtr, XWeather_frame_top_Config *ConfigPtr);
#else
int XWeather_frame_top_Initialize(XWeather_frame_top *InstancePtr, const char* InstanceName);
int XWeather_frame_top_Release(XWeather_frame_top *InstancePtr);
#endif

void XWeather_frame_top_Start(XWeather_frame_top *InstancePtr);
u32 XWeather_frame_top_IsDone(XWeather_frame_top *InstancePtr);
u32 XWeather_frame_top_IsIdle(XWeather_frame_top *InstancePtr);
u32 XWeather_frame_top_IsReady(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_EnableAutoRestart(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_DisableAutoRestart(XWeather_frame_top *InstancePtr);
u32 XWeather_frame_top_Get_return(XWeather_frame_top *InstancePtr);

void XWeather_frame_top_Set_input_r(XWeather_frame_top *InstancePtr, u64 Data);
u64 XWeather_frame_top_Get_input_r(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_Set_output_r(XWeather_frame_top *InstancePtr, u64 Data);
u64 XWeather_frame_top_Get_output_r(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_Set_height(XWeather_frame_top *InstancePtr, u32 Data);
u32 XWeather_frame_top_Get_height(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_Set_width(XWeather_frame_top *InstancePtr, u32 Data);
u32 XWeather_frame_top_Get_width(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_Set_task_r(XWeather_frame_top *InstancePtr, u32 Data);
u32 XWeather_frame_top_Get_task_r(XWeather_frame_top *InstancePtr);

void XWeather_frame_top_InterruptGlobalEnable(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_InterruptGlobalDisable(XWeather_frame_top *InstancePtr);
void XWeather_frame_top_InterruptEnable(XWeather_frame_top *InstancePtr, u32 Mask);
void XWeather_frame_top_InterruptDisable(XWeather_frame_top *InstancePtr, u32 Mask);
void XWeather_frame_top_InterruptClear(XWeather_frame_top *InstancePtr, u32 Mask);
u32 XWeather_frame_top_InterruptGetEnabled(XWeather_frame_top *InstancePtr);
u32 XWeather_frame_top_InterruptGetStatus(XWeather_frame_top *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
