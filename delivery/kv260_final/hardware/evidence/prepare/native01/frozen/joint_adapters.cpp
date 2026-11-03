#include "joint_adapters.hpp"

static int16_t original_raw(uint8_t p) {
    return static_cast<int16_t>((static_cast<uint32_t>(p) * 16384u + 127u) / 255u);
}

static int16_t d_raw(uint8_t p) {
    const int32_t numerator = (2 * static_cast<int32_t>(p) - 255) * 16384;
    const uint32_t magnitude = numerator < 0 ? -numerator : numerator;
    const int32_t rounded = (magnitude + 127u) / 255u;
    return static_cast<int16_t>(numerator < 0 ? -rounded : rounded);
}

static int16_t average_even(uint32_t sum) {
    const uint32_t q = sum >> 2;
    const uint32_t remainder = sum & 3u;
    return static_cast<int16_t>(q + (remainder > 2u || (remainder == 2u && (q & 1u))));
}

extern "C" int joint_rgb8_prepare(const uint8_t* rgb, int16_t* original_q14,
                                  int16_t* d_input_q14, int16_t* cnn_input_q14,
                                  uint32_t abi_cookie) {
#pragma HLS INTERFACE m_axi port=rgb offset=slave bundle=gmem_rgb depth=2747520
#pragma HLS INTERFACE m_axi port=original_q14 offset=slave bundle=gmem_i depth=2747520
#pragma HLS INTERFACE m_axi port=d_input_q14 offset=slave bundle=gmem_d depth=2747520
#pragma HLS INTERFACE m_axi port=cnn_input_q14 offset=slave bundle=gmem_cnn depth=19080
#pragma HLS INTERFACE s_axilite port=return bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=rgb bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=original_q14 bundle=control offset=0x24
#pragma HLS INTERFACE s_axilite port=d_input_q14 bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=cnn_input_q14 bundle=control offset=0x3c
#pragma HLS INTERFACE s_axilite port=abi_cookie bundle=control offset=0x48
    if (abi_cookie != JOINT_PREPARE_COOKIE) return -1;

    // Contiguous RGB reads. Separate planar writes keep the public layout NCHW.
    for (int pixel = 0; pixel < JOINT_PLANE; ++pixel) {
        for (int c = 0; c < 3; ++c) {
#pragma HLS PIPELINE II=1
            const uint8_t p = rgb[3 * pixel + c];
            original_q14[c * JOINT_PLANE + pixel] = original_raw(p);
            // Do not derive this from original_q14: that loses one raw bit for
            // some RGB8 values compared with the frozen D preprocessing Golden.
            d_input_q14[c * JOINT_PLANE + pixel] = d_raw(p);
        }
    }
    // Exact align_corners=False scale-1/12 bilinear sampling of the quantized
    // original: the two source coordinates are 12*k+5 and 12*k+6 per axis.
    for (int c = 0; c < 3; ++c) {
        for (int y = 0; y < JOINT_LOW_H; ++y) {
            for (int x = 0; x < JOINT_LOW_W; ++x) {
#pragma HLS PIPELINE II=1
                uint32_t sum = 0;
                for (int dy = 0; dy < 2; ++dy) {
                    for (int dx = 0; dx < 2; ++dx) {
                        const int pixel = (12 * y + 5 + dy) * JOINT_W + 12 * x + 5 + dx;
                        sum += original_raw(rgb[3 * pixel + c]);
                    }
                }
                cnn_input_q14[(c * JOINT_LOW_H + y) * JOINT_LOW_W + x] = average_even(sum);
            }
        }
    }
    return 0;
}

extern "C" int joint_q14_copy(const int16_t* source, int16_t* destination,
                              uint32_t abi_cookie) {
#pragma HLS INTERFACE m_axi port=source offset=slave bundle=gmem_source depth=2747520
#pragma HLS INTERFACE m_axi port=destination offset=slave bundle=gmem_destination depth=2747520
#pragma HLS INTERFACE s_axilite port=return bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=source bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=destination bundle=control offset=0x24
#pragma HLS INTERFACE s_axilite port=abi_cookie bundle=control offset=0x30
    if (abi_cookie != JOINT_COPY_COOKIE) return -1;
    for (int i = 0; i < JOINT_COUNT; ++i) {
#pragma HLS PIPELINE II=1
        destination[i] = source[i];
    }
    return 0;
}
