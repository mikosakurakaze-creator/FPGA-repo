#include "zero_dce_cnn_top.h"

namespace {

// This table is generated from configs/zero_dce_pp_integer_rules.json. The
// offsets are element offsets into the four packed DDR arrays described in the
// public interface contract.
static const zero_dce_layer_spec_t kZeroDceLayers[14] = {
    {3, 3, 3, 14, 14, 3, 3, 1, 1, 0, 0, 0},
    {3, 32, 1, 14, 14, 1, 1, 0, 0, 27, 3, 3},
    {32, 32, 32, 14, 13, 3, 3, 1, 1, 123, 35, 35},
    {32, 32, 1, 13, 14, 1, 1, 0, 0, 411, 67, 67},
    {32, 32, 32, 14, 14, 3, 3, 1, 1, 1435, 99, 99},
    {32, 32, 1, 14, 14, 1, 1, 0, 0, 1723, 131, 131},
    {32, 32, 32, 14, 12, 3, 3, 1, 1, 2747, 163, 163},
    {32, 32, 1, 12, 12, 1, 1, 0, 0, 3035, 195, 195},
    {64, 64, 64, 12, 13, 3, 3, 1, 1, 4059, 227, 227},
    {64, 32, 1, 13, 13, 1, 1, 0, 0, 4635, 291, 291},
    {64, 64, 64, 13, 13, 3, 3, 1, 1, 6683, 323, 323},
    {64, 32, 1, 13, 14, 1, 1, 0, 0, 7259, 387, 387},
    {64, 64, 64, 14, 14, 3, 3, 1, 1, 9307, 419, 419},
    {64, 3, 1, 14, 16, 1, 1, 0, 0, 9883, 483, 483},
};

static const int kSkipFrac[6] = {14, 14, 14, 12, 13, 14};

static inline zero_dce_q16_t clamp_q16(long long value) {
#pragma HLS INLINE
    if (value > 32767) {
        return (zero_dce_q16_t)32767;
    }
    if (value < -32768) {
        return (zero_dce_q16_t)-32768;
    }
    return (zero_dce_q16_t)value;
}

// Signed nearest, ties to even. The software quantizer uses the same rule.
static inline long long round_shift_even(long long value, int shift) {
#pragma HLS INLINE
    if (shift <= 0) {
        // Multiplication is defined for negative values; left-shifting a
        // negative signed C++ value is not.
        return value * (1LL << (-shift));
    }
    const long long magnitude = value < 0 ? -value : value;
    const long long denominator = 1LL << shift;
    long long quotient = magnitude >> shift;
    const long long remainder = magnitude & (denominator - 1);
    if ((remainder > (denominator >> 1)) ||
        ((remainder == (denominator >> 1)) && (quotient & 1LL))) {
        ++quotient;
    }
    return value < 0 ? -quotient : quotient;
}

static inline zero_dce_q16_t rescale_q16(
    zero_dce_q16_t value, int old_frac, int new_frac) {
#pragma HLS INLINE
    return clamp_q16(round_shift_even((long long)value, old_frac - new_frac));
}

static inline int feature_index(int channel, int row, int column) {
#pragma HLS INLINE
    return (channel * ZERO_DCE_HEIGHT + row) * ZERO_DCE_WIDTH + column;
}

// Model arrays are copied once per invocation. No convolution MAC reads DDR.
static void load_model(
    const zero_dce_q8_t *weights_int8,
    const zero_dce_q32_t *bias_int32,
    const zero_dce_q8_t *weight_frac,
    const zero_dce_q16_t *tanh_lut_q15,
    zero_dce_q8_t local_weights[ZERO_DCE_WEIGHT_ELEMENTS],
    zero_dce_q32_t local_bias[ZERO_DCE_BIAS_ELEMENTS],
    zero_dce_q8_t local_frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    zero_dce_q16_t local_lut[ZERO_DCE_TANH_LUT_ELEMENTS]) {
    for (int index = 0; index < ZERO_DCE_WEIGHT_ELEMENTS; ++index) {
#pragma HLS PIPELINE II=1
        local_weights[index] = weights_int8[index];
    }
    for (int index = 0; index < ZERO_DCE_BIAS_ELEMENTS; ++index) {
#pragma HLS PIPELINE II=1
        local_bias[index] = bias_int32[index];
    }
    for (int index = 0; index < ZERO_DCE_WEIGHT_FRAC_ELEMENTS; ++index) {
#pragma HLS PIPELINE II=1
        local_frac[index] = weight_frac[index];
    }
    for (int index = 0; index < ZERO_DCE_TANH_LUT_ELEMENTS; ++index) {
#pragma HLS PIPELINE II=1
        local_lut[index] = tanh_lut_q15[index];
    }
}

// Read one tile plus its one-pixel halo. Concatenation and its required
// per-skip requantization happen here, before the depthwise convolution.
static void load_source_tile(
    const zero_dce_q16_t *input_q14,
    const zero_dce_q16_t *workspace_int16,
    int block, int tile_row, int tile_column, int channels, int input_frac,
    zero_dce_q16_t source_tile[ZERO_DCE_MAX_FEATURE_CHANNELS]
                               [ZERO_DCE_TILE_HEIGHT + 2]
                               [ZERO_DCE_TILE_WIDTH + 2]) {
    const int left_skip = block == 5 ? 2 : (block == 6 ? 1 : 0);
    const int right_skip = block == 5 ? 3 : (block == 6 ? 4 : 5);
    for (int channel = 0; channel < channels; ++channel) {
        const zero_dce_q16_t *source = block == 1 ? input_q14 : workspace_int16;
        int source_channel = channel;
        int source_frac = 14;
        int slot = 0;
        if (block >= 5) {
            const bool right_half = channel >= 32;
            slot = right_half ? right_skip : left_skip;
            source_channel = right_half ? channel - 32 : channel;
            source_frac = kSkipFrac[slot];
        } else if (block > 1) {
            slot = block - 2;
            source_frac = kSkipFrac[slot];
        }
        const int base = block == 1
                             ? source_channel * ZERO_DCE_SPATIAL
                             : ZERO_DCE_SKIP0_OFFSET +
                                   slot * ZERO_DCE_SKIP_STRIDE +
                                   source_channel * ZERO_DCE_SPATIAL;
        for (int local_row = 0; local_row < ZERO_DCE_TILE_HEIGHT + 2;
             ++local_row) {
            const int global_row = tile_row + local_row - 1;
            for (int local_column = 0;
                 local_column < ZERO_DCE_TILE_WIDTH + 2; ++local_column) {
#pragma HLS PIPELINE II=1
                source_tile[channel][local_row][local_column] = 0;
            }
            if (global_row >= 0 && global_row < ZERO_DCE_HEIGHT) {
                const int first_column = tile_column == 0 ? 1 : 0;
                const int end_column =
                    tile_column + ZERO_DCE_TILE_WIDTH + 1 < ZERO_DCE_WIDTH
                        ? ZERO_DCE_TILE_WIDTH + 2
                        : ZERO_DCE_WIDTH - tile_column + 1;
                const int row_base = base + global_row * ZERO_DCE_WIDTH +
                                     tile_column - 1;
                for (int local_column = first_column;
                     local_column < end_column; ++local_column) {
#pragma HLS PIPELINE II=1
                    const zero_dce_q16_t value = source[row_base + local_column];
                    source_tile[channel][local_row][local_column] =
                        rescale_q16(value, source_frac, input_frac);
                }
            }
        }
    }
}

static void compute_depth_tile(
    const zero_dce_q16_t source_tile[ZERO_DCE_MAX_FEATURE_CHANNELS]
                                      [ZERO_DCE_TILE_HEIGHT + 2]
                                      [ZERO_DCE_TILE_WIDTH + 2],
    zero_dce_q16_t middle_tile[ZERO_DCE_MAX_FEATURE_CHANNELS]
                                  [ZERO_DCE_TILE_HEIGHT]
                                  [ZERO_DCE_TILE_WIDTH],
    const zero_dce_q8_t local_weights[ZERO_DCE_WEIGHT_ELEMENTS],
    const zero_dce_q32_t local_bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t local_frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_layer_spec_t &depth,
    const zero_dce_layer_spec_t &point,
    int tile_height, int tile_width) {
    for (int channel = 0; channel < depth.output_channels; ++channel) {
        const int weight_base = depth.weight_offset + 9 * channel;
        const int shift = depth.input_frac +
                          (int)local_frac[depth.weight_frac_offset + channel] -
                          depth.output_frac;
        for (int row = 0; row < tile_height; ++row) {
            for (int column = 0; column < tile_width; ++column) {
                zero_dce_q32_t accumulator =
                    local_bias[depth.bias_offset + channel];
                for (int kernel_row = 0; kernel_row < 3; ++kernel_row) {
                    for (int kernel_column = 0; kernel_column < 3;
                         ++kernel_column) {
#pragma HLS PIPELINE II=1
                        accumulator +=
                            (zero_dce_q32_t)source_tile[channel]
                                                        [row + kernel_row]
                                                        [column + kernel_column] *
                            (zero_dce_q32_t)local_weights[
                                weight_base + 3 * kernel_row + kernel_column];
                    }
                }
                const zero_dce_q16_t depth_value = clamp_q16(
                    round_shift_even((long long)accumulator, shift));
                middle_tile[channel][row][column] = rescale_q16(
                    depth_value, depth.output_frac, point.input_frac);
            }
        }
    }
}

static void compute_point_tile(
    const zero_dce_q16_t middle_tile[ZERO_DCE_MAX_FEATURE_CHANNELS]
                                      [ZERO_DCE_TILE_HEIGHT]
                                      [ZERO_DCE_TILE_WIDTH],
    zero_dce_q16_t output_tile[32]
                                  [ZERO_DCE_TILE_HEIGHT]
                                  [ZERO_DCE_TILE_WIDTH],
    const zero_dce_q8_t local_weights[ZERO_DCE_WEIGHT_ELEMENTS],
    const zero_dce_q32_t local_bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t local_frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_q16_t local_lut[ZERO_DCE_TANH_LUT_ELEMENTS],
    const zero_dce_layer_spec_t &point,
    int block, int tile_height, int tile_width) {
    for (int output_channel = 0; output_channel < point.output_channels;
         ++output_channel) {
        const int weight_base =
            point.weight_offset + output_channel * point.input_channels;
        const int shift = point.input_frac +
                          (int)local_frac[point.weight_frac_offset +
                                          output_channel] -
                          point.output_frac;
        for (int row = 0; row < tile_height; ++row) {
            for (int column = 0; column < tile_width; ++column) {
                zero_dce_q32_t accumulator =
                    local_bias[point.bias_offset + output_channel];
                for (int input_channel = 0;
                     input_channel < point.input_channels; ++input_channel) {
#pragma HLS PIPELINE II=1
                    accumulator +=
                        (zero_dce_q32_t)middle_tile[input_channel][row][column] *
                        (zero_dce_q32_t)local_weights[
                            weight_base + input_channel];
                }
                zero_dce_q16_t value =
                    clamp_q16(round_shift_even((long long)accumulator, shift));
                if (block < 7) {
                    if (value < 0) {
                        value = 0;
                    }
                } else {
                    int q8_index = (int)round_shift_even((long long)value, 8);
                    if (q8_index < -2048) {
                        q8_index = -2048;
                    }
                    if (q8_index > 2048) {
                        q8_index = 2048;
                    }
                    value = clamp_q16(round_shift_even(
                        (long long)local_lut[q8_index + 2048], 1));
                }
                output_tile[output_channel][row][column] = value;
            }
        }
    }
}

static void store_output_tile(
    const zero_dce_q16_t output_tile[32]
                                      [ZERO_DCE_TILE_HEIGHT]
                                      [ZERO_DCE_TILE_WIDTH],
    zero_dce_q16_t *a_low_q14, zero_dce_q16_t *workspace_int16,
    int block, int tile_row, int tile_column, int channels,
    int tile_height, int tile_width) {
    zero_dce_q16_t *destination =
        block == 7 ? a_low_q14 : workspace_int16;
    const int slot_base =
        block == 7 ? 0 : ZERO_DCE_SKIP0_OFFSET +
                               (block - 1) * ZERO_DCE_SKIP_STRIDE;
    for (int channel = 0; channel < channels; ++channel) {
        const int base = slot_base + channel * ZERO_DCE_SPATIAL;
        for (int row = 0; row < tile_height; ++row) {
            for (int column = 0; column < tile_width; ++column) {
#pragma HLS PIPELINE II=1
                destination[base + (tile_row + row) * ZERO_DCE_WIDTH +
                            tile_column + column] =
                    output_tile[channel][row][column];
            }
        }
    }
}

}  // namespace

extern "C" void zero_dce_cnn_top(
    const zero_dce_q16_t *input_q14,
    const zero_dce_q8_t *weights_int8,
    const zero_dce_q32_t *bias_int32,
    const zero_dce_q8_t *weight_frac,
    const zero_dce_q16_t *tanh_lut_q15,
    zero_dce_q16_t *a_low_q14,
    zero_dce_q16_t *workspace_int16) {
#pragma HLS INTERFACE m_axi port=input_q14 offset=slave bundle=gmem_input depth=19080 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=weights_int8 offset=slave bundle=gmem8 depth=10075 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=bias_int32 offset=slave bundle=gmem32 depth=486 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=weight_frac offset=slave bundle=gmem8 depth=486 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=tanh_lut_q15 offset=slave bundle=gmem_lut depth=4097 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=a_low_q14 offset=slave bundle=gmem_output depth=19080 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=workspace_int16 offset=slave bundle=gmem_workspace depth=1221120 max_read_burst_length=64 max_write_burst_length=64
#pragma HLS INTERFACE s_axilite port=input_q14 bundle=control
#pragma HLS INTERFACE s_axilite port=weights_int8 bundle=control
#pragma HLS INTERFACE s_axilite port=bias_int32 bundle=control
#pragma HLS INTERFACE s_axilite port=weight_frac bundle=control
#pragma HLS INTERFACE s_axilite port=tanh_lut_q15 bundle=control
#pragma HLS INTERFACE s_axilite port=a_low_q14 bundle=control
#pragma HLS INTERFACE s_axilite port=workspace_int16 bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    zero_dce_q8_t local_weights[ZERO_DCE_WEIGHT_ELEMENTS];
    zero_dce_q32_t local_bias[ZERO_DCE_BIAS_ELEMENTS];
    zero_dce_q8_t local_frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS];
    zero_dce_q16_t local_lut[ZERO_DCE_TANH_LUT_ELEMENTS];
    zero_dce_q16_t source_tile[ZERO_DCE_MAX_FEATURE_CHANNELS]
                               [ZERO_DCE_TILE_HEIGHT + 2]
                               [ZERO_DCE_TILE_WIDTH + 2];
    zero_dce_q16_t middle_tile[ZERO_DCE_MAX_FEATURE_CHANNELS]
                               [ZERO_DCE_TILE_HEIGHT]
                               [ZERO_DCE_TILE_WIDTH];
    zero_dce_q16_t output_tile[32][ZERO_DCE_TILE_HEIGHT]
                               [ZERO_DCE_TILE_WIDTH];
#pragma HLS BIND_STORAGE variable=local_weights type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=local_bias type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=local_frac type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=local_lut type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=source_tile type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=middle_tile type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=output_tile type=ram_2p impl=bram

    load_model(weights_int8, bias_int32, weight_frac, tanh_lut_q15,
               local_weights, local_bias, local_frac, local_lut);
    for (int block = 1; block <= 7; ++block) {
        const zero_dce_layer_spec_t &depth = kZeroDceLayers[2 * (block - 1)];
        const zero_dce_layer_spec_t &point = kZeroDceLayers[2 * (block - 1) + 1];
        for (int tile_row = 0; tile_row < ZERO_DCE_HEIGHT;
             tile_row += ZERO_DCE_TILE_HEIGHT) {
            const int tile_height =
                tile_row + ZERO_DCE_TILE_HEIGHT <= ZERO_DCE_HEIGHT
                    ? ZERO_DCE_TILE_HEIGHT : ZERO_DCE_HEIGHT - tile_row;
            for (int tile_column = 0; tile_column < ZERO_DCE_WIDTH;
                 tile_column += ZERO_DCE_TILE_WIDTH) {
                const int tile_width =
                    tile_column + ZERO_DCE_TILE_WIDTH <= ZERO_DCE_WIDTH
                        ? ZERO_DCE_TILE_WIDTH : ZERO_DCE_WIDTH - tile_column;
                load_source_tile(input_q14, workspace_int16, block, tile_row,
                                 tile_column, depth.input_channels,
                                 depth.input_frac, source_tile);
                compute_depth_tile(source_tile, middle_tile, local_weights,
                                   local_bias, local_frac, depth, point,
                                   tile_height, tile_width);
                compute_point_tile(middle_tile, output_tile, local_weights,
                                   local_bias, local_frac, local_lut, point,
                                   block, tile_height, tile_width);
                store_output_tile(output_tile, a_low_q14, workspace_int16,
                                  block, tile_row, tile_column,
                                  point.output_channels, tile_height, tile_width);
            }
        }
    }
}
