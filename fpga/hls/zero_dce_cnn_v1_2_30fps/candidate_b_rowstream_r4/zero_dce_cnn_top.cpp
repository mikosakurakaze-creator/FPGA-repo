#include "zero_dce_cnn_top.h"
#include "../../../perf/cnn_v1_2_phase3b_r4/row_transfer.hpp"
#include <hls_streamofblocks.h>
#ifndef __SYNTHESIS__
#include <thread>
#endif

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

// Each pointwise lane owns one BRAM bank. The offsets count (Cout/4) *
// ceil(Cin/8) groups in the preceding blocks; unused tail lanes stay unread.
static const int kPointBankBase[7] = {0, 8, 40, 72, 104, 168, 232};
static const int kPointBankDepth = 240;

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
    zero_dce_q16_t local_lut[ZERO_DCE_PW_OUTPUT_PAR]
                              [ZERO_DCE_TANH_LUT_ELEMENTS]) {
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
        const zero_dce_q16_t value = tanh_lut_q15[index];
        for (int lane = 0; lane < ZERO_DCE_PW_OUTPUT_PAR; ++lane) {
#pragma HLS UNROLL
            local_lut[lane][index] = value;
        }
    }
}

// Repack the pointwise weights only once per invocation. For a given output
// group and input group, all 4*8 products read distinct on-chip banks.
static void bank_point_weights(
    const zero_dce_q8_t local_weights[ZERO_DCE_WEIGHT_ELEMENTS],
    zero_dce_q8_t point_banks[ZERO_DCE_PW_OUTPUT_PAR]
                             [ZERO_DCE_PW_INPUT_PAR][kPointBankDepth]) {
    for (int block_index = 0; block_index < 7; ++block_index) {
        const zero_dce_layer_spec_t &point =
            kZeroDceLayers[2 * block_index + 1];
        const int input_groups =
            (point.input_channels + ZERO_DCE_PW_INPUT_PAR - 1) /
            ZERO_DCE_PW_INPUT_PAR;
        for (int output_channel = 0;
             output_channel < point.output_channels; ++output_channel) {
            const int output_group =
                output_channel / ZERO_DCE_PW_OUTPUT_PAR;
            const int output_lane =
                output_channel % ZERO_DCE_PW_OUTPUT_PAR;
            for (int input_channel = 0;
                 input_channel < point.input_channels; ++input_channel) {
#pragma HLS PIPELINE II=1
                const int input_group =
                    input_channel / ZERO_DCE_PW_INPUT_PAR;
                const int input_lane =
                    input_channel % ZERO_DCE_PW_INPUT_PAR;
                const int address = kPointBankBase[block_index] +
                                    output_group * input_groups + input_group;
                point_banks[output_lane][input_lane][address] =
                    local_weights[point.weight_offset +
                                  output_channel * point.input_channels +
                                  input_channel];
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
    for (int channel_group = 0;
         channel_group < depth.output_channels;
         channel_group += ZERO_DCE_DW_CHANNEL_PAR) {
        zero_dce_q8_t kernel[ZERO_DCE_DW_CHANNEL_PAR][9];
        zero_dce_q32_t bias[ZERO_DCE_DW_CHANNEL_PAR];
        int shift[ZERO_DCE_DW_CHANNEL_PAR];
#pragma HLS ARRAY_PARTITION variable=kernel complete dim=0
#pragma HLS ARRAY_PARTITION variable=bias complete dim=0
#pragma HLS ARRAY_PARTITION variable=shift complete dim=0
        for (int lane = 0; lane < ZERO_DCE_DW_CHANNEL_PAR; ++lane) {
#pragma HLS UNROLL
            const int channel = channel_group + lane;
            if (channel < depth.output_channels) {
                bias[lane] = local_bias[depth.bias_offset + channel];
                shift[lane] = depth.input_frac +
                    (int)local_frac[depth.weight_frac_offset + channel] -
                    depth.output_frac;
                for (int k = 0; k < 9; ++k) {
                    kernel[lane][k] =
                        local_weights[depth.weight_offset + 9 * channel + k];
                }
            }
        }
        for (int row = 0; row < tile_height; ++row) {
            for (int column = 0; column < tile_width; ++column) {
#pragma HLS PIPELINE II=1
                for (int lane = 0; lane < ZERO_DCE_DW_CHANNEL_PAR; ++lane) {
#pragma HLS UNROLL
                    const int channel = channel_group + lane;
                    if (channel < depth.output_channels) {
                        zero_dce_q32_t products[9];
#pragma HLS ARRAY_PARTITION variable=products complete dim=0
                        for (int k = 0; k < 9; ++k) {
#pragma HLS UNROLL
                            products[k] =
                                (zero_dce_q32_t)source_tile[channel]
                                    [row + k / 3][column + k % 3] *
                                (zero_dce_q32_t)kernel[lane][k];
                        }
                        // The original accumulator wraps modulo 2^32 after
                        // every product. A balanced ap_int<32> reduction has
                        // the same residues, including signed overflow.
                        zero_dce_q32_t s01 = products[0] + products[1];
                        zero_dce_q32_t s23 = products[2] + products[3];
                        zero_dce_q32_t s45 = products[4] + products[5];
                        zero_dce_q32_t s67 = products[6] + products[7];
                        zero_dce_q32_t s0123 = s01 + s23;
                        zero_dce_q32_t s4567 = s45 + s67;
                        zero_dce_q32_t s0to7 = s0123 + s4567;
                        zero_dce_q32_t accumulator =
                            bias[lane] + s0to7 + products[8];
                        const zero_dce_q16_t depth_value = clamp_q16(
                            round_shift_even((long long)accumulator,
                                             shift[lane]));
                        middle_tile[channel][row][column] = rescale_q16(
                            depth_value, depth.output_frac,
                            point.input_frac);
                    }
                }
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
    const zero_dce_q8_t point_banks[ZERO_DCE_PW_OUTPUT_PAR]
                                   [ZERO_DCE_PW_INPUT_PAR][kPointBankDepth],
    const zero_dce_q32_t local_bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t local_frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_q16_t local_lut[ZERO_DCE_PW_OUTPUT_PAR]
                                   [ZERO_DCE_TANH_LUT_ELEMENTS],
    const zero_dce_layer_spec_t &point,
    int block, int tile_height, int tile_width) {
    const int block_index = block - 1;
    const int input_groups =
        (point.input_channels + ZERO_DCE_PW_INPUT_PAR - 1) /
        ZERO_DCE_PW_INPUT_PAR;
    for (int output_group = 0;
         output_group < point.output_channels;
         output_group += ZERO_DCE_PW_OUTPUT_PAR) {
        zero_dce_q32_t bias[ZERO_DCE_PW_OUTPUT_PAR] = {};
        int shift[ZERO_DCE_PW_OUTPUT_PAR] = {};
        zero_dce_q32_t accumulator_tile[ZERO_DCE_PW_OUTPUT_PAR]
                                       [ZERO_DCE_TILE_HEIGHT]
                                       [ZERO_DCE_TILE_WIDTH];
#pragma HLS ARRAY_PARTITION variable=bias complete dim=0
#pragma HLS ARRAY_PARTITION variable=shift complete dim=0
#pragma HLS ARRAY_PARTITION variable=accumulator_tile complete dim=1
#pragma HLS BIND_STORAGE variable=accumulator_tile type=ram_2p impl=bram
        for (int lane = 0; lane < ZERO_DCE_PW_OUTPUT_PAR; ++lane) {
#pragma HLS UNROLL
            const int output_channel = output_group + lane;
            if (output_channel < point.output_channels) {
                bias[lane] = local_bias[point.bias_offset + output_channel];
                shift[lane] = point.input_frac +
                    (int)local_frac[point.weight_frac_offset + output_channel]
                    - point.output_frac;
            }
        }
        // Move Cin-group reduction outside the pixel loops. Consecutive
        // pixels now enter the 32-lane MAC pipeline every cycle; the same
        // pixel's accumulator is revisited only after the full tile sweep.
        for (int input_group = 0;
             input_group < input_groups; ++input_group) {
            const int address = kPointBankBase[block_index] +
                (output_group / ZERO_DCE_PW_OUTPUT_PAR) *
                    input_groups + input_group;
            for (int row = 0; row < tile_height; ++row) {
                for (int column = 0; column < tile_width; ++column) {
#pragma HLS PIPELINE II=1
                    for (int lane = 0; lane < ZERO_DCE_PW_OUTPUT_PAR; ++lane) {
#pragma HLS UNROLL
                        if (output_group + lane < point.output_channels) {
                            zero_dce_q32_t product[ZERO_DCE_PW_INPUT_PAR];
#pragma HLS ARRAY_PARTITION variable=product complete dim=0
                            for (int input_lane = 0;
                                 input_lane < ZERO_DCE_PW_INPUT_PAR;
                                 ++input_lane) {
#pragma HLS UNROLL
                                const int input_channel =
                                    input_group * ZERO_DCE_PW_INPUT_PAR +
                                    input_lane;
                                if (input_channel < point.input_channels) {
                                    product[input_lane] =
                                        (zero_dce_q32_t)middle_tile
                                            [input_channel][row][column] *
                                        (zero_dce_q32_t)point_banks
                                            [lane][input_lane][address];
                                } else {
                                    product[input_lane] = 0;
                                }
                            }
                            zero_dce_q32_t p01 = product[0] + product[1];
                            zero_dce_q32_t p23 = product[2] + product[3];
                            zero_dce_q32_t p45 = product[4] + product[5];
                            zero_dce_q32_t p67 = product[6] + product[7];
                            zero_dce_q32_t p0123 = p01 + p23;
                            zero_dce_q32_t p4567 = p45 + p67;
                            const zero_dce_q32_t partial = p0123 + p4567;
                            zero_dce_q32_t accumulator = input_group == 0
                                ? bias[lane]
                                : accumulator_tile[lane][row][column];
                            accumulator += partial;
                            if (input_group + 1 == input_groups) {
                                zero_dce_q16_t value = clamp_q16(
                                    round_shift_even((long long)accumulator,
                                                     shift[lane]));
                                if (block < 7) {
                                    if (value < 0) {
                                        value = 0;
                                    }
                                } else {
                                    int q8_index =
                                        (int)round_shift_even((long long)value, 8);
                                    if (q8_index < -2048) q8_index = -2048;
                                    if (q8_index > 2048) q8_index = 2048;
                                    value = clamp_q16(round_shift_even(
                                        (long long)local_lut[lane][q8_index + 2048], 1));
                                }
                                output_tile[output_group + lane][row][column] = value;
                            } else {
                                accumulator_tile[lane][row][column] = accumulator;
                            }
                        }
                    }
                }
            }
        }

    }
}

#include "../../../perf/cnn_v1_2_phase3b_r4/rowstream_arch.inc"
#include "../../../perf/cnn_v1_2_phase3b_r4/rowstream_group_arch.inc"

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
    zero_dce_q8_t point_banks[ZERO_DCE_PW_OUTPUT_PAR]
                              [ZERO_DCE_PW_INPUT_PAR][kPointBankDepth];
    zero_dce_q32_t local_bias[ZERO_DCE_BIAS_ELEMENTS];
    zero_dce_q8_t local_frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS];
    zero_dce_q16_t local_lut[ZERO_DCE_PW_OUTPUT_PAR]
                              [ZERO_DCE_TANH_LUT_ELEMENTS];
#pragma HLS BIND_STORAGE variable=local_weights type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=point_banks type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=point_banks complete dim=1
#pragma HLS ARRAY_PARTITION variable=point_banks complete dim=2
#pragma HLS BIND_STORAGE variable=local_bias type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=local_frac type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=local_lut type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=local_lut complete dim=1
#pragma HLS ALLOCATION function instances=group_rowstream_block limit=1

    load_model(weights_int8, bias_int32, weight_frac, tanh_lut_q15,
               local_weights, local_bias, local_frac, local_lut);
    bank_point_weights(local_weights, point_banks);
    // All actor streams and outstanding writes drain at each block boundary.
    for(int block=1;block<=7;++block)
        group_rowstream_block(input_q14,workspace_int16,a_low_q14,
            local_weights,point_banks,local_bias,local_frac,local_lut,block);
}
