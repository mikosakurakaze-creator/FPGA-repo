// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XZERO_DCE_CNN_TOP_H
#define XZERO_DCE_CNN_TOP_H

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
#include "xzero_dce_cnn_top_hw.h"

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
} XZero_dce_cnn_top_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XZero_dce_cnn_top;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XZero_dce_cnn_top_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XZero_dce_cnn_top_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XZero_dce_cnn_top_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XZero_dce_cnn_top_ReadReg(BaseAddress, RegOffset) \
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
int XZero_dce_cnn_top_Initialize(XZero_dce_cnn_top *InstancePtr, UINTPTR BaseAddress);
XZero_dce_cnn_top_Config* XZero_dce_cnn_top_LookupConfig(UINTPTR BaseAddress);
#else
int XZero_dce_cnn_top_Initialize(XZero_dce_cnn_top *InstancePtr, u16 DeviceId);
XZero_dce_cnn_top_Config* XZero_dce_cnn_top_LookupConfig(u16 DeviceId);
#endif
int XZero_dce_cnn_top_CfgInitialize(XZero_dce_cnn_top *InstancePtr, XZero_dce_cnn_top_Config *ConfigPtr);
#else
int XZero_dce_cnn_top_Initialize(XZero_dce_cnn_top *InstancePtr, const char* InstanceName);
int XZero_dce_cnn_top_Release(XZero_dce_cnn_top *InstancePtr);
#endif

void XZero_dce_cnn_top_Start(XZero_dce_cnn_top *InstancePtr);
u32 XZero_dce_cnn_top_IsDone(XZero_dce_cnn_top *InstancePtr);
u32 XZero_dce_cnn_top_IsIdle(XZero_dce_cnn_top *InstancePtr);
u32 XZero_dce_cnn_top_IsReady(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_EnableAutoRestart(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_DisableAutoRestart(XZero_dce_cnn_top *InstancePtr);

void XZero_dce_cnn_top_Set_input_q14(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_input_q14(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_Set_weights_int8(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_weights_int8(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_Set_bias_int32(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_bias_int32(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_Set_weight_frac(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_weight_frac(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_Set_tanh_lut_q15(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_tanh_lut_q15(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_Set_a_low_q14(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_a_low_q14(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_Set_workspace_int16(XZero_dce_cnn_top *InstancePtr, u64 Data);
u64 XZero_dce_cnn_top_Get_workspace_int16(XZero_dce_cnn_top *InstancePtr);

void XZero_dce_cnn_top_InterruptGlobalEnable(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_InterruptGlobalDisable(XZero_dce_cnn_top *InstancePtr);
void XZero_dce_cnn_top_InterruptEnable(XZero_dce_cnn_top *InstancePtr, u32 Mask);
void XZero_dce_cnn_top_InterruptDisable(XZero_dce_cnn_top *InstancePtr, u32 Mask);
void XZero_dce_cnn_top_InterruptClear(XZero_dce_cnn_top *InstancePtr, u32 Mask);
u32 XZero_dce_cnn_top_InterruptGetEnabled(XZero_dce_cnn_top *InstancePtr);
u32 XZero_dce_cnn_top_InterruptGetStatus(XZero_dce_cnn_top *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
