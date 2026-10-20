#ifndef WEATHER_XILINX_STANDALONE_H
#define WEATHER_XILINX_STANDALONE_H
#include "weather_control.h"

/* A53 standalone BSP with identity-mapped, linker-owned low DDR buffers.
 * Not a Linux backend. The caller exclusively owns the IP and allocations.
 */
struct weather_xilinx_context { uintptr_t control_base; };
int weather_xilinx_platform(struct weather_platform*, struct weather_xilinx_context*);
#endif
