#include "weather_kernel.h"
#if !defined(WEATHER_TASK_DEHAZE)
#include "params_derain.h"
#endif
#if !defined(WEATHER_TASK_DERAIN)
#include "params_dehaze.h"
#endif

namespace weather {

int32_t round_shift_even(int32_t value, int power) {
#pragma HLS INLINE
    // All powers are validated by the generator / internal calls: 0..30.
    // Avoid abs(INT32_MIN), negative right shifts, and negative left shifts.
    if (power == 0) return value;
    const uint32_t magnitude = value < 0
        ? static_cast<uint32_t>(-(value + 1)) + 1U
        : static_cast<uint32_t>(value);
    const uint32_t divisor = uint32_t(1) << power;
    uint32_t quotient = magnitude >> power;
    const uint32_t remainder = magnitude & (divisor - 1U);
    const uint32_t half = divisor >> 1;
    if (remainder > half || (remainder == half && (quotient & 1U))) ++quotient;
    const int32_t rounded = static_cast<int32_t>(quotient);  // <= 2^30 for power >= 1
    return value < 0 ? -rounded : rounded;
}

int32_t rescale(int32_t value, int old_frac, int new_frac) {
#pragma HLS INLINE
    if (old_frac >= new_frac) return round_shift_even(value, old_frac - new_frac);
    // Only residual INT16 operands use a left scale, by at most 8 bits.
    // Multiplication remains in INT32; no signed left shift is used.
    return value * (int32_t(1) << (new_frac - old_frac));
}

int16_t saturate_int16(int32_t value) {
#pragma HLS INLINE
    if (value < -32768) return -32768;
    if (value > 32767) return 32767;
    return static_cast<int16_t>(value);
}

#ifndef __SYNTHESIS__
static TraceCallback trace_callback = 0;
static void* trace_user = 0;
void set_trace_callback(TraceCallback callback, void* user) {
    trace_callback = callback;
    trace_user = user;
}
static void trace(const char* name, const int16_t* values, int channels, int h, int w) {
    if (trace_callback) trace_callback(name, values, channels, h, w, trace_user);
}
#define WEATHER_TRACE(name, values, channels) trace(name, values, channels, height, width)
#else
#define WEATHER_TRACE(name, values, channels) ((void)0)
#endif

namespace detail {

// Sequential convolutions execute one layer at a time. All intermediate frames
// reside in caller-owned DDR; only model constants / scalars are on-chip.
// Inline at the four graph call sites: forcing one shared function across AXI
// input/work/output port signatures crashes Vitis 2025.2 frontend reflow. The
// block-loop depth/point call sites still serve all five residual blocks.
// Bounds in parameter_provenance.json prove every partial MAC fits signed INT32,
// even for the complete signed INT16 domain and any accumulation order.
static void convolution(const int16_t* input, int16_t* output,
                        const LayerParams& layer, int height, int width) {
#pragma HLS INLINE
    const int plane = height * width;
    const int per_group = layer.groups == 1 ? layer.input_channels : 1;
    const int kernel_area = layer.kernel * layer.kernel;
conv_output_channels:
    for (int oc = 0; oc < layer.output_channels; ++oc) {
#pragma HLS LOOP_TRIPCOUNT min=3 max=8
        const int channel_start = layer.groups == 1 ? 0 : oc;
        const int shift = layer.input_frac + layer.weight_frac[oc] - layer.output_frac;
conv_rows:
        for (int y = 0; y < height; ++y) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=140
conv_columns:
            for (int x = 0; x < width; ++x) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=140
                int32_t accumulator = layer.bias[oc];
conv_kernel_rows:
                for (int ky = 0; ky < layer.kernel; ++ky) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=3
conv_kernel_columns:
                    for (int kx = 0; kx < layer.kernel; ++kx) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=3
                        const int iy = y + ky - layer.padding;
                        const int ix = x + kx - layer.padding;
conv_input_channels:
                        for (int ic = 0; ic < per_group; ++ic) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=8
#pragma HLS PIPELINE II=1
                            if (iy >= 0 && iy < height && ix >= 0 && ix < width) {
                                const int source = (channel_start + ic) * plane + iy * width + ix;
                                const int weight = (oc * per_group + ic) * kernel_area + ky * layer.kernel + kx;
                                const int32_t product = static_cast<int32_t>(input[source]) *
                                    static_cast<int32_t>(layer.weights[weight]);
                                accumulator += product;
                            }
                        }
                    }
                }
                output[oc * plane + y * width + x] =
                    saturate_int16(round_shift_even(accumulator, shift));
            }
        }
    }
}

static void relu(int16_t* values, int count) {
#pragma HLS INLINE off
relu_elements:
    for (int i = 0; i < count; ++i) {
#pragma HLS LOOP_TRIPCOUNT min=8 max=156800
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=values inter false
        // Only values[i] is read/written. Distinct iterations use distinct
        // addresses; the intra-iteration read-before-write remains required.
        const int16_t value = values[i];
        values[i] = value < 0 ? int16_t(0) : value;
    }
}

static void residual_add(int16_t* skip, const int16_t* point, int count,
                         int skip_frac, int point_frac, int output_frac) {
#pragma HLS INLINE off
residual_elements:
    for (int i = 0; i < count; ++i) {
#pragma HLS LOOP_TRIPCOUNT min=8 max=156800
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=skip inter false
#pragma HLS DEPENDENCE variable=point inter false
        // skip=[scratch,scratch+8*H*W), point starts at scratch+16*H*W;
        // both spans contain count=8*H*W words and cannot overlap. Iteration
        // i accesses only element i of each span. No inter-iteration RAW/WAR/WAW.
        // Each operand must be rounded independently BEFORE the addition.
        const int32_t a = rescale(skip[i], skip_frac, output_frac);
        const int32_t b = rescale(point[i], point_frac, output_frac);
        skip[i] = saturate_int16(a + b);
    }
}

static void final_add(const int16_t* input, int16_t* residual, int count, int tail_frac) {
#pragma HLS INLINE off
output_elements:
    for (int i = 0; i < count; ++i) {
#pragma HLS LOOP_TRIPCOUNT min=3 max=58800
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=residual inter false
        // The ABI requires nonoverlapping input/output ranges; residual is
        // output. Iteration i only reads/writes its own residual[i].
        const int32_t value = static_cast<int32_t>(input[i]) + rescale(residual[i], tail_frac, 14);
        residual[i] = value < 0 ? int16_t(0) : value > 16384 ? int16_t(16384) : static_cast<int16_t>(value);
    }
}

static int restore(const int16_t* input, int16_t* output, int16_t* scratch,
                    int height, int width, const ModelParams& params) {
#pragma HLS INLINE
#pragma HLS ALLOCATION function instances=relu limit=1
#pragma HLS ALLOCATION function instances=residual_add limit=1
    if (height < 1 || height > MAX_HEIGHT || width < 1 || width > MAX_WIDTH) return 1;
    const int plane = height * width;
    int16_t* main = scratch;
    int16_t* depth = scratch + 8 * plane;
    int16_t* point = scratch + 16 * plane;
    WEATHER_TRACE("input", input, 3);
    convolution(input, main, params.layers[0], height, width);
    WEATHER_TRACE("stem", main, 8);
    relu(main, 8 * plane);
    WEATHER_TRACE("stem_relu", main, 8);
    int skip_frac = params.layers[0].output_frac;
restore_blocks:
    for (int block = 0; block < BLOCKS; ++block) {
#pragma HLS LOOP_TRIPCOUNT min=5 max=5
        const LayerParams& dp = params.layers[1 + block * 2];
        const LayerParams& pp = params.layers[2 + block * 2];
        convolution(main, depth, dp, height, width);
#ifndef __SYNTHESIS__
        static const char* const depth_names[5] = {"blocks.0.depth", "blocks.1.depth", "blocks.2.depth", "blocks.3.depth", "blocks.4.depth"};
        static const char* const depth_relu_names[5] = {"blocks.0.depth_relu", "blocks.1.depth_relu", "blocks.2.depth_relu", "blocks.3.depth_relu", "blocks.4.depth_relu"};
        static const char* const point_names[5] = {"blocks.0.point", "blocks.1.point", "blocks.2.point", "blocks.3.point", "blocks.4.point"};
        static const char* const add_names[5] = {"blocks.0.add", "blocks.1.add", "blocks.2.add", "blocks.3.add", "blocks.4.add"};
        static const char* const relu_names[5] = {"blocks.0.relu", "blocks.1.relu", "blocks.2.relu", "blocks.3.relu", "blocks.4.relu"};
        WEATHER_TRACE(depth_names[block], depth, 8);
#endif
        relu(depth, 8 * plane);
#ifndef __SYNTHESIS__
        WEATHER_TRACE(depth_relu_names[block], depth, 8);
#endif
        convolution(depth, point, pp, height, width);
#ifndef __SYNTHESIS__
        WEATHER_TRACE(point_names[block], point, 8);
#endif
        residual_add(main, point, 8 * plane, skip_frac, pp.output_frac, params.add_frac[block]);
#ifndef __SYNTHESIS__
        WEATHER_TRACE(add_names[block], main, 8);
#endif
        relu(main, 8 * plane);
#ifndef __SYNTHESIS__
        WEATHER_TRACE(relu_names[block], main, 8);
#endif
        skip_frac = params.add_frac[block];
    }
    convolution(main, output, params.layers[11], height, width);
    WEATHER_TRACE("tail", output, 3);
    final_add(input, output, 3 * plane, params.tail_frac);
    WEATHER_TRACE("output", output, 3);
    return 0;
}
}  // namespace detail
}  // namespace weather

#if !defined(WEATHER_TASK_DEHAZE)
extern "C" int derain_top(const int16_t* input, int16_t* output,
                           int16_t* scratch, int height, int width) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_in depth=58800 max_read_burst_length=64 num_read_outstanding=2
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_out depth=58800 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE m_axi port=scratch offset=slave bundle=gmem_work depth=470400 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE s_axilite port=input bundle=CTRL offset=0x18
#pragma HLS INTERFACE s_axilite port=output bundle=CTRL offset=0x24
#pragma HLS INTERFACE s_axilite port=scratch bundle=CTRL offset=0x30
#pragma HLS INTERFACE s_axilite port=height bundle=CTRL offset=0x3c
#pragma HLS INTERFACE s_axilite port=width bundle=CTRL offset=0x44
#pragma HLS INTERFACE s_axilite port=return bundle=CTRL
    return weather::detail::restore(input, output, scratch, height, width, weather::detail::DERAIN_PARAMS);
}
#endif

#if !defined(WEATHER_TASK_DERAIN)
extern "C" int dehaze_top(const int16_t* input, int16_t* output,
                           int16_t* scratch, int height, int width) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_in depth=58800 max_read_burst_length=64 num_read_outstanding=2
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_out depth=58800 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE m_axi port=scratch offset=slave bundle=gmem_work depth=470400 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE s_axilite port=input bundle=CTRL offset=0x18
#pragma HLS INTERFACE s_axilite port=output bundle=CTRL offset=0x24
#pragma HLS INTERFACE s_axilite port=scratch bundle=CTRL offset=0x30
#pragma HLS INTERFACE s_axilite port=height bundle=CTRL offset=0x3c
#pragma HLS INTERFACE s_axilite port=width bundle=CTRL offset=0x44
#pragma HLS INTERFACE s_axilite port=return bundle=CTRL
    return weather::detail::restore(input, output, scratch, height, width, weather::detail::DEHAZE_PARAMS);
}
#endif
