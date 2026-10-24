#include "conv_micro.hpp"

// Valid for certified D accumulators and shifts 1..62. No saturation/reordering
// is allowed inside the product sum. Avoid right shift of a negative integer.
static int16_t requantize(int64_t accumulator, uint8_t shift) {
#pragma HLS INLINE
    const bool negative = accumulator < 0;
    const uint64_t magnitude = negative ? uint64_t(-accumulator) : uint64_t(accumulator);
    const uint64_t rounded = (magnitude + (uint64_t(1) << (shift - 1))) >> shift;
    const int64_t signed_value = negative ? -int64_t(rounded) : int64_t(rounded);
    return signed_value < -32768 ? int16_t(-32768)
         : signed_value > 32767 ? int16_t(32767) : int16_t(signed_value);
}

void d_conv_direct(const int16_t input[D_INPUTS],
                   const int16_t weight[D_WEIGHTS],
                   const int64_t bias[D_C], const uint8_t shift[D_C],
                   int16_t output[D_INPUTS]) {
#pragma HLS INTERFACE mode=ap_memory port=input
#pragma HLS INTERFACE mode=ap_memory port=weight
#pragma HLS INTERFACE mode=ap_memory port=bias
#pragma HLS INTERFACE mode=ap_memory port=shift
#pragma HLS INTERFACE mode=ap_memory port=output
    for (int co = 0; co < D_C; ++co) {
        for (int y = 0; y < D_H; ++y) {
            for (int x = 0; x < D_W; ++x) {
                int64_t accumulator = bias[co];
                DIRECT_MAC: for (int t = 0; t < D_C * 9; ++t) {
#pragma HLS PIPELINE II=1
                    const int ci = t / 9, ky = (t / 3) % 3, kx = t % 3;
                    const int iy = y + ky - 1, ix = x + kx - 1;
                    const int16_t sample = (iy >= 0 && iy < D_H && ix >= 0 && ix < D_W)
                        ? input[(ci * D_H + iy) * D_W + ix] : int16_t(0);
                    accumulator += int32_t(sample) * int32_t(weight[co * D_C * 9 + t]);
                }
                output[(co * D_H + y) * D_W + x] = requantize(accumulator, shift[co]);
            }
        }
    }
}

void d_conv_row_oc8(const int16_t input[D_INPUTS],
                    const int16_t weight[D_WEIGHTS],
                    const int64_t bias[D_C], const uint8_t shift[D_C],
                    int16_t output[D_INPUTS]) {
#pragma HLS INTERFACE mode=ap_memory port=input
#pragma HLS INTERFACE mode=ap_memory port=weight
#pragma HLS INTERFACE mode=ap_memory port=bias
#pragma HLS INTERFACE mode=ap_memory port=shift
#pragma HLS INTERFACE mode=ap_memory port=output
    int16_t cached_weight[D_C][D_C * 9];
    int16_t rows[3][D_C][D_W];
    int64_t cached_bias[D_C];
    uint8_t cached_shift[D_C];
#pragma HLS ARRAY_PARTITION variable=cached_weight complete dim=1
#pragma HLS ARRAY_PARTITION variable=cached_bias complete
#pragma HLS ARRAY_PARTITION variable=cached_shift complete
    LOAD_WEIGHT: for (int co = 0; co < D_C; ++co) {
        for (int t = 0; t < D_C * 9; ++t) {
#pragma HLS PIPELINE II=1
            cached_weight[co][t] = weight[co * D_C * 9 + t];
        }
        cached_bias[co] = bias[co]; cached_shift[co] = shift[co];
    }
    // Initialize the top zero row and the first actual row. Subsequent rows are
    // loaded exactly once, into the circular slot no longer needed by the stencil.
    for (int ci = 0; ci < D_C; ++ci) {
        for (int x = 0; x < D_W; ++x) {
#pragma HLS PIPELINE II=1
            rows[0][ci][x] = 0;
            rows[1][ci][x] = input[(ci * D_H) * D_W + x];
        }
    }
    for (int y = 0; y < D_H; ++y) {
        LOAD_ROW: for (int ci = 0; ci < D_C; ++ci) {
            for (int x = 0; x < D_W; ++x) {
#pragma HLS PIPELINE II=1
                rows[(y + 2) % 3][ci][x] = y + 1 < D_H
                    ? input[(ci * D_H + y + 1) * D_W + x] : int16_t(0);
            }
        }
        for (int x = 0; x < D_W; ++x) {
            int64_t accumulator[D_C];
#pragma HLS ARRAY_PARTITION variable=accumulator complete
            for (int co = 0; co < D_C; ++co) {
#pragma HLS UNROLL
                accumulator[co] = cached_bias[co];
            }
            ROW_MAC: for (int t = 0; t < D_C * 9; ++t) {
#pragma HLS PIPELINE II=1
                const int ci = t / 9, ky = (t / 3) % 3, kx = t % 3;
                const int ix = x + kx - 1;
                const int16_t sample = ix >= 0 && ix < D_W
                    ? rows[(y + ky) % 3][ci][ix] : int16_t(0);
                for (int co = 0; co < D_C; ++co) {
#pragma HLS UNROLL
                    accumulator[co] += int32_t(sample) * int32_t(cached_weight[co][t]);
                }
            }
            for (int co = 0; co < D_C; ++co) {
                output[(co * D_H + y) * D_W + x] = requantize(accumulator[co], cached_shift[co]);
            }
        }
    }
}
