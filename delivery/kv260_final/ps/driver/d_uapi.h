/* SPDX-License-Identifier: GPL-2.0 */
#ifndef D_ONCE_UAPI_H
#define D_ONCE_UAPI_H
#include <linux/types.h>
#include <linux/ioctl.h>
struct compact_d_status {
    __u32 abi, attempted, pending, completed;
    __s32 error;
    __u32 ctrl, core_return, completed_nodes, hardware_model, hardware_abi, guards_ok, reserved;
    __u64 elapsed_ns, clock_hz, dma[84];
};
#define D_STATUS _IOR('G',0xe0,struct compact_d_status)
#define D_RUN _IO('G',0xe1)
#define D_ALLOC _IO('G',0xe2)
#endif
