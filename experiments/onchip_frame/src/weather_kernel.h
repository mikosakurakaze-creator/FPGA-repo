#ifndef WEATHER_A_COMPUTE_KERNEL_H
#define WEATHER_A_COMPUTE_KERNEL_H

#include <stdint.h>

// ABI v1. All arrays are contiguous NCHW signed 16-bit words (N=1).
// input and output contain 3*height*width words. scratch contains at least
// 24*height*width words. The three array ranges must not overlap.
// height,width in [1,140]. Returns 0 on success, 1 for invalid dimensions;
// invalid dimensions cause no pointer accesses. Buffers must otherwise be valid.
// Three AXI masters: gmem_in, gmem_out, gmem_work; AXI Lite bundle CTRL.
// Full signed INT16 inputs have proven safe INT32 MAC bounds; image input is Q14
// [0,16384]. Output is Q14 [0,16384]. No heap or on-chip image arrays are used.
extern "C" int derain_top(const int16_t* input, int16_t* output,
                           int16_t* scratch, int height, int width);
extern "C" int dehaze_top(const int16_t* input, int16_t* output,
                           int16_t* scratch, int height, int width);

namespace weather {
static const int MAX_HEIGHT = 140;
static const int MAX_WIDTH = 140;
static const int CHANNELS = 8;
static const int BLOCKS = 5;

// Arithmetic helpers are also exercised directly by the portable self-test.
int32_t round_shift_even(int32_t value, int power);
int32_t rescale(int32_t value, int old_frac, int new_frac);
int16_t saturate_int16(int32_t value);

#ifndef __SYNTHESIS__
typedef void (*TraceCallback)(const char* name, const int16_t* values,
                              int channels, int height, int width, void* user);
// Host-only instrumentation. Callback observes a layer before buffer reuse.
// Not reentrant or thread-safe. No callback state exists in the synthesized IP.
void set_trace_callback(TraceCallback callback, void* user);
#endif

namespace detail {
// Generated, fixed task parameters. Unused array tails are zero initialized.
struct LayerParams {
    int input_channels;
    int output_channels;
    int kernel;
    int groups;
    int padding;
    int input_frac;
    int output_frac;
    int weight_frac[8];
    int8_t weights[216];
    int32_t bias[8];
};
struct ModelParams {
    LayerParams layers[12];  // stem, (depth,point)*5, tail
    int add_frac[5];
    int tail_frac;
};
}  // namespace detail
}  // namespace weather
#endif
