#ifndef ZERO_DCE_CNN_TOP_H
#define ZERO_DCE_CNN_TOP_H

#include <ap_int.h>

// Candidate B: four depth channels, nine kernel products per channel,
// and four by eight pointwise products in parallel.
#define ZERO_DCE_DW_CHANNEL_PAR 4
#define ZERO_DCE_PW_INPUT_PAR 8
#define ZERO_DCE_PW_OUTPUT_PAR 4

// V1 CNN boundary: the input has already been reduced from the camera frame
// to 60x106 by the upstream fixed-point downsampler.
typedef ap_int<16> zero_dce_q16_t;
typedef ap_int<8> zero_dce_q8_t;
typedef ap_int<32> zero_dce_q32_t;

static const int ZERO_DCE_HEIGHT = 60;
static const int ZERO_DCE_WIDTH = 106;
static const int ZERO_DCE_INPUT_CHANNELS = 3;
static const int ZERO_DCE_OUTPUT_CHANNELS = 3;
static const int ZERO_DCE_SPATIAL = ZERO_DCE_HEIGHT * ZERO_DCE_WIDTH;
static const int ZERO_DCE_INPUT_ELEMENTS =
    ZERO_DCE_INPUT_CHANNELS * ZERO_DCE_SPATIAL;
static const int ZERO_DCE_OUTPUT_ELEMENTS =
    ZERO_DCE_OUTPUT_CHANNELS * ZERO_DCE_SPATIAL;
static const int ZERO_DCE_MAX_FEATURE_CHANNELS = 64;
static const int ZERO_DCE_MAX_FEATURE_ELEMENTS =
    ZERO_DCE_MAX_FEATURE_CHANNELS * ZERO_DCE_SPATIAL;
static const int ZERO_DCE_SKIP_ELEMENTS = 32 * ZERO_DCE_SPATIAL;
static const int ZERO_DCE_WORKSPACE_ELEMENTS = 6 * ZERO_DCE_SKIP_ELEMENTS;
static const int ZERO_DCE_TILE_HEIGHT = 8;
static const int ZERO_DCE_TILE_WIDTH = 16;
static const int ZERO_DCE_WEIGHT_ELEMENTS = 10075;
static const int ZERO_DCE_BIAS_ELEMENTS = 486;
static const int ZERO_DCE_WEIGHT_FRAC_ELEMENTS = 486;
static const int ZERO_DCE_TANH_LUT_ELEMENTS = 4097;

// The workspace contains only the six 32-channel ReLU skip tensors. The
// convolution working tiles and model arrays are held on chip during a run.
static const int ZERO_DCE_SKIP0_OFFSET = 0;
static const int ZERO_DCE_SKIP_STRIDE = ZERO_DCE_SKIP_ELEMENTS;

struct zero_dce_layer_spec_t {
    int input_channels;
    int output_channels;
    int groups;
    int input_frac;
    int output_frac;
    int kernel_h;
    int kernel_w;
    int pad_h;
    int pad_w;
    int weight_offset;
    int bias_offset;
    int weight_frac_offset;
};

// AXI4 master pointers use these packed arrays:
//   weights_int8: OIHW, layer order in kZeroDceLayers, little-endian bytes
//   bias_int32:   one INT32 per output channel, layer order
//   weight_frac:  one signed byte per output channel, layer order
//   tanh_lut_q15: 4097 entries for Q8 index -2048..2048
// The HLS ap_ctrl_hs return port supplies ap_start/ap_done/ap_idle/ap_ready.
extern "C" void zero_dce_cnn_top(
    const zero_dce_q16_t *input_q14,
    const zero_dce_q8_t *weights_int8,
    const zero_dce_q32_t *bias_int32,
    const zero_dce_q8_t *weight_frac,
    const zero_dce_q16_t *tanh_lut_q15,
    zero_dce_q16_t *a_low_q14,
    zero_dce_q16_t *workspace_int16);

#endif

