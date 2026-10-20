#ifndef WEATHER_B_ONCHIP_FRAME_H
#define WEATHER_B_ONCHIP_FRAME_H
#include <stdint.h>

// EXPERIMENTAL ABI v2. Not the ABI of the packaged A-group IP.
// Two nonoverlapping contiguous RGB NCHW INT16 little-endian frame buffers.
// Image values: Q14; all signed16 inputs supported; output clipped [0,16384].
// h:1..720, w:1..1280; task:0=derain, 1=dehaze; one task per invocation.
// 0=success, 1=invalid dimensions, 2=invalid task. Invalid arguments return
// before memory access. Valid arguments require caller-owned valid buffers.
// No external scratch, row stride, runtime weights, or AXI Stream.
extern "C" int weather_frame_top(const int16_t* input, int16_t* output,
                                 int height, int width, int task);

#ifndef __SYNTHESIS__
namespace weather_b {
// Host-only hooks for numerical verification; not an additional hardware ABI.
typedef void (*ScalarTrace)(int node, int channel, int y, int x,
                            int16_t value, void* user);
void set_trace(ScalarTrace callback, void* user);
int tile_local(const int16_t* input, int16_t* output, int h, int w, int task);
}
#endif
#endif
