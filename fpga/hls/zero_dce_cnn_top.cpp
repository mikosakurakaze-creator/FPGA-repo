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

static void rescale_buffer(
    zero_dce_q16_t *buffer, int channels, int old_frac, int new_frac) {
#pragma HLS INLINE
    if (old_frac == new_frac) {
        return;
    }
    for (int channel = 0; channel < channels; ++channel) {
        for (int row = 0; row < ZERO_DCE_HEIGHT; ++row) {
            for (int column = 0; column < ZERO_DCE_WIDTH; ++column) {
#pragma HLS PIPELINE II=1
                const int index = feature_index(channel, row, column);
                buffer[index] = rescale_q16(buffer[index], old_frac, new_frac);
            }
        }
    }
}

static void copy_input(
    const zero_dce_q16_t *input_q14, zero_dce_q16_t *workspace) {
    for (int index = 0; index < ZERO_DCE_INPUT_ELEMENTS; ++index) {
#pragma HLS PIPELINE II=1
        workspace[index] = input_q14[index];
    }
}

static void copy_skip(
    const zero_dce_q16_t *source, zero_dce_q16_t *workspace, int skip_index) {
    const int destination_offset = ZERO_DCE_SKIP0_OFFSET +
                                   skip_index * ZERO_DCE_SKIP_STRIDE;
    for (int index = 0; index < ZERO_DCE_SKIP_ELEMENTS; ++index) {
#pragma HLS PIPELINE II=1
        workspace[destination_offset + index] = source[index];
    }
}

static void concat_skip(
    zero_dce_q16_t *destination,
    const zero_dce_q16_t *workspace,
    int left_skip,
    int right_skip,
    int destination_frac,
    int left_frac,
    int right_frac) {
    const int left_offset = ZERO_DCE_SKIP0_OFFSET + left_skip * ZERO_DCE_SKIP_STRIDE;
    const int right_offset = ZERO_DCE_SKIP0_OFFSET + right_skip * ZERO_DCE_SKIP_STRIDE;
    for (int channel = 0; channel < 32; ++channel) {
        for (int row = 0; row < ZERO_DCE_HEIGHT; ++row) {
            for (int column = 0; column < ZERO_DCE_WIDTH; ++column) {
#pragma HLS PIPELINE II=1
                const int index = feature_index(channel, row, column);
                destination[index] = rescale_q16(
                    workspace[left_offset + index], left_frac, destination_frac);
                destination[ZERO_DCE_SKIP_ELEMENTS + index] = rescale_q16(
                    workspace[right_offset + index], right_frac, destination_frac);
            }
        }
    }
}

static void convolution(
    const zero_dce_q16_t *source,
    zero_dce_q16_t *destination,
    const zero_dce_q8_t *weights_int8,
    const zero_dce_q32_t *bias_int32,
    const zero_dce_q8_t *weight_frac,
    const zero_dce_layer_spec_t &layer) {
    const int input_per_group = layer.input_channels / layer.groups;
    const int output_per_group = layer.output_channels / layer.groups;
    const int kernel_elements = layer.kernel_h * layer.kernel_w;

    for (int output_channel = 0; output_channel < layer.output_channels;
         ++output_channel) {
        const int group = output_channel / output_per_group;
        const int input_group_offset = group * input_per_group;
        const int weight_channel_offset =
            layer.weight_offset + output_channel * input_per_group * kernel_elements;
        const int weight_frac_value =
            (int)weight_frac[layer.weight_frac_offset + output_channel];
        const int rescale_shift =
            layer.input_frac + weight_frac_value - layer.output_frac;
        for (int row = 0; row < ZERO_DCE_HEIGHT; ++row) {
            for (int column = 0; column < ZERO_DCE_WIDTH; ++column) {
                zero_dce_q32_t accumulator =
                    bias_int32[layer.bias_offset + output_channel];
                for (int input_channel = 0; input_channel < input_per_group;
                     ++input_channel) {
                    for (int kernel_row = 0; kernel_row < layer.kernel_h;
                         ++kernel_row) {
                        for (int kernel_column = 0; kernel_column < layer.kernel_w;
                             ++kernel_column) {
                            const int source_row = row + kernel_row - layer.pad_h;
                            const int source_column =
                                column + kernel_column - layer.pad_w;
                            if (source_row >= 0 && source_row < ZERO_DCE_HEIGHT &&
                                source_column >= 0 &&
                                source_column < ZERO_DCE_WIDTH) {
                                const int source_index = feature_index(
                                    input_group_offset + input_channel,
                                    source_row, source_column);
                                const int weight_index =
                                    weight_channel_offset +
                                    (input_channel * kernel_elements) +
                                    kernel_row * layer.kernel_w + kernel_column;
                                accumulator +=
                                    (zero_dce_q32_t)source[source_index] *
                                    (zero_dce_q32_t)weights_int8[weight_index];
                            }
                        }
                    }
                }
                // The frozen quantization rules bound every accumulation
                // within signed INT32 for a signed INT16 input.
                const long long requantized =
                    round_shift_even((long long)accumulator, rescale_shift);
                destination[feature_index(output_channel, row, column)] =
                    clamp_q16(requantized);
            }
        }
    }
}

static void apply_relu(zero_dce_q16_t *buffer, int channels) {
    for (int channel = 0; channel < channels; ++channel) {
        for (int row = 0; row < ZERO_DCE_HEIGHT; ++row) {
            for (int column = 0; column < ZERO_DCE_WIDTH; ++column) {
#pragma HLS PIPELINE II=1
                const int index = feature_index(channel, row, column);
                if (buffer[index] < 0) {
                    buffer[index] = 0;
                }
            }
        }
    }
}

static void emit_a_low(
    const zero_dce_q16_t *features,
    const zero_dce_q16_t *tanh_lut_q15,
    zero_dce_q16_t *a_low_q14) {
    for (int channel = 0; channel < ZERO_DCE_OUTPUT_CHANNELS; ++channel) {
        for (int row = 0; row < ZERO_DCE_HEIGHT; ++row) {
            for (int column = 0; column < ZERO_DCE_WIDTH; ++column) {
#pragma HLS PIPELINE II=1
                const int index = feature_index(channel, row, column);
                int q8_index = (int)round_shift_even((long long)features[index], 8);
                if (q8_index < -2048) {
                    q8_index = -2048;
                }
                if (q8_index > 2048) {
                    q8_index = 2048;
                }
                const int lut_index = q8_index + 2048;
                const long long tanh_q15 = tanh_lut_q15[lut_index];
                a_low_q14[index] = clamp_q16(round_shift_even(tanh_q15, 1));
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
#pragma HLS INTERFACE m_axi port=input_q14 offset=slave bundle=gmem depth=19080 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=weights_int8 offset=slave bundle=gmem depth=10075 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=bias_int32 offset=slave bundle=gmem depth=486 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=weight_frac offset=slave bundle=gmem depth=486 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=tanh_lut_q15 offset=slave bundle=gmem depth=4097 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=a_low_q14 offset=slave bundle=gmem depth=19080 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=workspace_int16 offset=slave bundle=gmem depth=2035200 max_read_burst_length=64 max_write_burst_length=64
#pragma HLS INTERFACE s_axilite port=input_q14 bundle=control
#pragma HLS INTERFACE s_axilite port=weights_int8 bundle=control
#pragma HLS INTERFACE s_axilite port=bias_int32 bundle=control
#pragma HLS INTERFACE s_axilite port=weight_frac bundle=control
#pragma HLS INTERFACE s_axilite port=tanh_lut_q15 bundle=control
#pragma HLS INTERFACE s_axilite port=a_low_q14 bundle=control
#pragma HLS INTERFACE s_axilite port=workspace_int16 bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    zero_dce_q16_t *buffer0 =
        workspace_int16 + ZERO_DCE_WORK_BUFFER0_OFFSET;
    zero_dce_q16_t *buffer1 =
        workspace_int16 + ZERO_DCE_WORK_BUFFER1_OFFSET;

    copy_input(input_q14, buffer0);
    int current_frac = 14;
    int current_channels = 3;

    for (int block = 1; block <= 7; ++block) {
        const int depth_layer_index = 2 * (block - 1);
        const int point_layer_index = depth_layer_index + 1;
        const zero_dce_layer_spec_t &depth =
            kZeroDceLayers[depth_layer_index];
        const zero_dce_layer_spec_t &point =
            kZeroDceLayers[point_layer_index];

        if (block >= 5) {
            const int left = block == 5 ? 2 : (block == 6 ? 1 : 0);
            const int right = block == 5 ? 3 : (block == 6 ? 4 : 5);
            concat_skip(buffer0, workspace_int16, left, right,
                        depth.input_frac, kSkipFrac[left], kSkipFrac[right]);
            current_channels = 64;
            current_frac = depth.input_frac;
        }

        rescale_buffer(buffer0, current_channels, current_frac,
                       depth.input_frac);
        convolution(buffer0, buffer1, weights_int8, bias_int32, weight_frac,
                    depth);
        rescale_buffer(buffer1, depth.output_channels, depth.output_frac,
                       point.input_frac);
        convolution(buffer1, buffer0, weights_int8, bias_int32, weight_frac,
                    point);
        current_channels = point.output_channels;
        current_frac = point.output_frac;

        if (block < 7) {
            apply_relu(buffer0, current_channels);
            copy_skip(buffer0, workspace_int16, block - 1);
        }
    }

    // The final pointwise layer is Q16. Tanh LUT lookup is Q8-indexed and
    // returns Q15; the public CNN-to-Bilinear boundary is signed Q14.
    emit_a_low(buffer0, tanh_lut_q15, a_low_q14);
}
