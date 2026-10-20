#include "weather_frame.h"
// Fixed A-group parameters; scripts/verify_host.py checks their pinned hashes.
#include "params_derain.h"
#include "params_dehaze.h"

namespace weather_b {
using weather::detail::LayerParams;
using weather::detail::ModelParams;
static const int MAX_TILE = 140;
static const int PIXELS = MAX_TILE * MAX_TILE;
static const int CORE = 128;
static const int HALO = 6;

#ifndef __SYNTHESIS__
static ScalarTrace trace_callback = 0;
static void* trace_user = 0;
void set_trace(ScalarTrace callback, void* user) {
    trace_callback = callback;
    trace_user = user;
}
static void trace(int node, int channel, int y, int x, int16_t value) {
    if (trace_callback) trace_callback(node, channel, y, x, value, trace_user);
}
#else
static void trace(int, int, int, int, int16_t) {}
#endif

static int32_t rne(int32_t value, int shift) {
#pragma HLS INLINE
    if (!shift) return value;
    const uint32_t magnitude = value < 0 ? uint32_t(-(value + 1)) + 1U : uint32_t(value);
    const uint32_t mask = (uint32_t(1) << shift) - 1U;
    uint32_t quotient = magnitude >> shift;
    const uint32_t remainder = magnitude & mask;
    const uint32_t half = uint32_t(1) << (shift - 1);
    if (remainder > half || (remainder == half && (quotient & 1U))) ++quotient;
    return value < 0 ? -int32_t(quotient) : int32_t(quotient);
}
static int32_t scale(int16_t value, int old_frac, int new_frac) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
#pragma HLS LATENCY min=3
    return old_frac >= new_frac ? rne(value, old_frac - new_frac)
        : int32_t(value) * (int32_t(1) << (new_frac - old_frac));
}
static int16_t sat(int32_t value) {
#pragma HLS INLINE
    return value < -32768 ? int16_t(-32768)
         : value > 32767 ? int16_t(32767) : int16_t(value);
}
static int16_t quantize(int32_t value, const LayerParams& p, int oc) {
#pragma HLS INLINE
    return sat(rne(value, p.input_frac + p.weight_frac[oc] - p.output_frac));
}

// Read the fixed model through one sequential ROM port before starting a layer.
// Parallel arithmetic then uses small, completely partitioned register banks.
// Passing the entire model ROM into each unrolled MAC replicated it per read port.
static void load_layer(const ModelParams& params, int index, LayerParams& local) {
#pragma HLS INLINE off
    local.input_frac = params.layers[index].input_frac;
    local.output_frac = params.layers[index].output_frac;
    for (int i = 0; i < 216; ++i) {
#pragma HLS PIPELINE II=1
        local.weights[i] = params.layers[index].weights[i];
    }
    for (int i = 0; i < 8; ++i) {
#pragma HLS PIPELINE II=1
        local.bias[i] = params.layers[index].bias[i];
        local.weight_frac[i] = params.layers[index].weight_frac[i];
    }
}

// Eight independent output sums share a loaded input sample. Fixed C8 loops
// remove generic grouped-convolution branches from the sequential baseline.
static void stem(const int16_t rgb[3][PIXELS], int16_t main[8][PIXELS],
                 int h, int w, const LayerParams& p) {
#pragma HLS INLINE off
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            int32_t acc[8];
#pragma HLS ARRAY_PARTITION variable=acc complete
            for (int oc = 0; oc < 8; ++oc) {
#pragma HLS UNROLL
                acc[oc] = p.bias[oc];
            }
            for (int ky = 0; ky < 3; ++ky) {
                for (int kx = 0; kx < 3; ++kx) {
                    for (int ic = 0; ic < 3; ++ic) {
#pragma HLS PIPELINE II=1
                        const int iy = y + ky - 1, ix = x + kx - 1;
                        const int16_t v = iy >= 0 && iy < h && ix >= 0 && ix < w
                            ? rgb[ic][iy * w + ix] : int16_t(0);
                        for (int oc = 0; oc < 8; ++oc) {
#pragma HLS UNROLL
                            acc[oc] += int32_t(v) * int32_t(p.weights[oc * 27 + ic * 9 + ky * 3 + kx]);
                        }
                    }
                }
            }
            for (int oc = 0; oc < 8; ++oc) {
#pragma HLS UNROLL
                const int16_t q = quantize(acc[oc], p, oc);
                const int16_t activated = q < 0 ? int16_t(0) : q;
                trace(1, oc, y, x, q);
                trace(2, oc, y, x, activated);
                main[oc][y * w + x] = activated;
            }
        }
    }
}

static void depthwise(const int16_t main[8][PIXELS], int16_t depth[8][PIXELS],
                      int h, int w, const LayerParams& p, int block) {
#pragma HLS INLINE off
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            int32_t acc[8];
#pragma HLS ARRAY_PARTITION variable=acc complete
            for (int c = 0; c < 8; ++c) {
#pragma HLS UNROLL
                acc[c] = p.bias[c];
            }
            for (int ky = 0; ky < 3; ++ky) {
                for (int kx = 0; kx < 3; ++kx) {
#pragma HLS PIPELINE II=1
                    const int iy = y + ky - 1, ix = x + kx - 1;
                    for (int c = 0; c < 8; ++c) {
#pragma HLS UNROLL
                        const int16_t v = iy >= 0 && iy < h && ix >= 0 && ix < w
                            ? main[c][iy * w + ix] : int16_t(0);
                        acc[c] += int32_t(v) * int32_t(p.weights[c * 9 + ky * 3 + kx]);
                    }
                }
            }
            for (int c = 0; c < 8; ++c) {
#pragma HLS UNROLL
                const int16_t q = quantize(acc[c], p, c);
                const int16_t activated = q < 0 ? int16_t(0) : q;
                trace(3 + block * 5, c, y, x, q);
                trace(4 + block * 5, c, y, x, activated);
                depth[c][y * w + x] = activated;
            }
        }
    }
}

// Balanced eight-way reduction: avoids a serial chain of eight dependent MACs.
// Original parameter bounds cover the absolute sum of all products and bias.
static int32_t dot8(const int16_t values[8], const LayerParams& p, int oc) {
#pragma HLS INLINE
    int32_t product[8];
#pragma HLS ARRAY_PARTITION variable=product complete
    for (int ic = 0; ic < 8; ++ic) {
#pragma HLS UNROLL
        product[ic] = int32_t(values[ic]) * int32_t(p.weights[oc * 8 + ic]);
    }
    const int32_t a = (product[0] + product[1]) + (product[2] + product[3]);
    const int32_t b = (product[4] + product[5]) + (product[6] + product[7]);
    return (a + b) + p.bias[oc];
}

static void point_add_relu(int16_t main[8][PIXELS], const int16_t depth[8][PIXELS],
                           int h, int w, const LayerParams& p,
                           int skip_frac, int add_frac, int block) {
#pragma HLS INLINE off
    for (int i = 0; i < h * w; ++i) {
#pragma HLS PIPELINE II=1
        int16_t pixel[8], skip[8];
#pragma HLS ARRAY_PARTITION variable=pixel complete
#pragma HLS ARRAY_PARTITION variable=skip complete
        for (int ic = 0; ic < 8; ++ic) {
#pragma HLS UNROLL
            pixel[ic] = depth[ic][i];
            skip[ic] = main[ic][i];
        }
        for (int oc = 0; oc < 8; ++oc) {
#pragma HLS UNROLL
            // Preserve point saturation BEFORE independent residual rescaling.
            const int16_t point = quantize(dot8(pixel, p, oc), p, oc);
            const int16_t added = sat(scale(skip[oc], skip_frac, add_frac)
                                   + scale(point, p.output_frac, add_frac));
            const int16_t activated = added < 0 ? int16_t(0) : added;
            trace(5 + block * 5, oc, i / w, i % w, point);
            trace(6 + block * 5, oc, i / w, i % w, added);
            trace(7 + block * 5, oc, i / w, i % w, activated);
            main[oc][i] = activated;
        }
    }
}

static void load_tile(const int16_t* input, int16_t rgb[3][PIXELS],
                      int frame_h, int frame_w, int y0, int x0, int h, int w) {
#pragma HLS INLINE off
    for (int c = 0; c < 3; ++c) {
        for (int y = 0; y < h; ++y) {
            const int source = (c * frame_h + y0 + y) * frame_w + x0;
            for (int x = 0; x < w; ++x) {
#pragma HLS PIPELINE II=1
                const int16_t v = input[source + x];
                rgb[c][y * w + x] = v;
                trace(0, c, y, x, v);
            }
        }
    }
}

// Keep the DDR write loop separate from the deep tail/quantization pipeline.
// With a 1-pixel row, flattening all three loops issued more row requests than
// the adapter's four credits before the first data reached its write stage.
// The resulting global pipeline stall also stopped that first data (deadlock).
static void write_row(int16_t* output, const int16_t row[MAX_TILE], int dest, int width) {
#pragma HLS INLINE off
    for (int x = 0; x < width; ++x) {
#pragma HLS PIPELINE II=1
        output[dest + x] = row[x];
    }
}

static void store_core(const int16_t main[8][PIXELS], const int16_t rgb[3][PIXELS],
                       int16_t* output, int frame_h, int frame_w,
                       int y0, int x0, int tile_w, int cy, int cx, int ch, int cw,
                       const LayerParams& tail, int tail_frac) {
#pragma HLS INLINE off
    // tile_local() also verifies full 140-wide A tiles on host.
    int16_t row[MAX_TILE];
#pragma HLS BIND_STORAGE variable=row type=ram_2p impl=bram
    for (int c = 0; c < 3; ++c) {
#pragma HLS LOOP_FLATTEN off
        for (int y = 0; y < ch; ++y) {
#pragma HLS LOOP_FLATTEN off
            const int dest = (c * frame_h + y0 + cy + y) * frame_w + x0 + cx;
            for (int x = 0; x < cw; ++x) {
#pragma HLS PIPELINE II=1
                const int i = (cy + y) * tile_w + cx + x;
                int16_t pixel[8];
#pragma HLS ARRAY_PARTITION variable=pixel complete
                for (int ic = 0; ic < 8; ++ic) {
#pragma HLS UNROLL
                    pixel[ic] = main[ic][i];
                }
                const int16_t residual = quantize(dot8(pixel, tail, c), tail, c);
                const int32_t value = int32_t(rgb[c][i]) + scale(residual, tail_frac, 14);
                const int16_t q = value < 0 ? int16_t(0)
                    : value > 16384 ? int16_t(16384) : int16_t(value);
                trace(28, c, cy + y, cx + x, residual);
                trace(29, c, cy + y, cx + x, q);
                row[x] = q;
            }
            write_row(output, row, dest, cw);
        }
    }
}

// One reused tile engine. Both fixed parameter sets remain distinct, selected
// for the entire call. Static banks are rewritten before any read each tile.
static void run_tile(const int16_t* input, int16_t* output,
                     int frame_h, int frame_w, int y0, int x0, int h, int w,
                     int cy, int cx, int ch, int cw, const ModelParams& params) {
#pragma HLS INLINE off
    static int16_t rgb[3][PIXELS];
    static int16_t main[8][PIXELS];
    static int16_t depth[8][PIXELS];
#pragma HLS ARRAY_PARTITION variable=rgb complete dim=1
#pragma HLS ARRAY_PARTITION variable=main complete dim=1
#pragma HLS ARRAY_PARTITION variable=depth complete dim=1
    // Pack four adjacent 16-bit samples per 64-bit word before URAM binding.
    // Requested mapping only: the achieved II/ports/resources require HLS.
#pragma HLS ARRAY_RESHAPE variable=main cyclic factor=4 dim=2
#pragma HLS ARRAY_RESHAPE variable=depth cyclic factor=4 dim=2
#pragma HLS BIND_STORAGE variable=rgb type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=main type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=depth type=ram_2p impl=uram
    LayerParams local;
#pragma HLS ARRAY_PARTITION variable=local.weights complete
#pragma HLS ARRAY_PARTITION variable=local.bias complete
#pragma HLS ARRAY_PARTITION variable=local.weight_frac complete
    load_tile(input, rgb, frame_h, frame_w, y0, x0, h, w);
    load_layer(params, 0, local);
    stem(rgb, main, h, w, local);
    int skip_frac = local.output_frac;
    for (int b = 0; b < 5; ++b) {
        load_layer(params, 1 + 2 * b, local);
        depthwise(main, depth, h, w, local, b);
        load_layer(params, 2 + 2 * b, local);
        point_add_relu(main, depth, h, w, local,
                       skip_frac, params.add_frac[b], b);
        skip_frac = params.add_frac[b];
    }
    load_layer(params, 11, local);
    store_core(main, rgb, output, frame_h, frame_w, y0, x0, w,
               cy, cx, ch, cw, local, params.tail_frac);
}

#ifndef __SYNTHESIS__
int tile_local(const int16_t* input, int16_t* output, int h, int w, int task) {
    if (h < 1 || h > 140 || w < 1 || w > 140) return 1;
    if (task < 0 || task > 1) return 2;
    const ModelParams& p = task ? weather::detail::DEHAZE_PARAMS : weather::detail::DERAIN_PARAMS;
    run_tile(input, output, h, w, 0, 0, h, w, 0, 0, h, w, p);
    return 0;
}
#endif
}  // namespace weather_b

extern "C" int weather_frame_top(const int16_t* input, int16_t* output,
                                 int height, int width, int task) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_in depth=2764800 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_out depth=2764800 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=input bundle=CTRL offset=0x18
#pragma HLS INTERFACE s_axilite port=output bundle=CTRL offset=0x24
#pragma HLS INTERFACE s_axilite port=height bundle=CTRL offset=0x30
#pragma HLS INTERFACE s_axilite port=width bundle=CTRL offset=0x38
#pragma HLS INTERFACE s_axilite port=task bundle=CTRL offset=0x40
#pragma HLS INTERFACE s_axilite port=return bundle=CTRL
    if (height < 1 || height > 720 || width < 1 || width > 1280) return 1;
    if (task < 0 || task > 1) return 2;
    const weather::detail::ModelParams& params = task
        ? weather::detail::DEHAZE_PARAMS : weather::detail::DERAIN_PARAMS;
    for (int y = 0; y < height; y += weather_b::CORE) {
        for (int x = 0; x < width; x += weather_b::CORE) {
            const int y1 = y + 128 < height ? y + 128 : height;
            const int x1 = x + 128 < width ? x + 128 : width;
            const int y0 = y > weather_b::HALO ? y - weather_b::HALO : 0;
            const int x0 = x > weather_b::HALO ? x - weather_b::HALO : 0;
            const int ye = y1 + 6 < height ? y1 + 6 : height;
            const int xe = x1 + 6 < width ? x1 + 6 : width;
            weather_b::run_tile(input, output, height, width, y0, x0,
                                ye - y0, xe - x0, y - y0, x - x0,
                                y1 - y, x1 - x, params);
        }
    }
    return 0;
}
