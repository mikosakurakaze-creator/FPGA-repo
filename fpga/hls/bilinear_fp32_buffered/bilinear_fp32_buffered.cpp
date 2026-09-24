#include "bilinear_fp32_buffered.hpp"

namespace {
constexpr unsigned int kMaxInputWidth = 128;
}

void bilinear_fp32_buffered(const float* parameters_lowres,
                            float* parameters_fullres,
                            unsigned int input_height, unsigned int input_width) {
#pragma HLS INTERFACE m_axi port=parameters_lowres offset=slave bundle=gmem_input
#pragma HLS INTERFACE m_axi port=parameters_fullres offset=slave bundle=gmem_output
#pragma HLS INTERFACE s_axilite port=parameters_lowres bundle=control
#pragma HLS INTERFACE s_axilite port=parameters_fullres bundle=control
#pragma HLS INTERFACE s_axilite port=input_height bundle=control
#pragma HLS INTERFACE s_axilite port=input_width bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    if (input_height == 0 || input_width == 0 || input_width > kMaxInputWidth) return;

    const unsigned int output_height = input_height * 12;
    const unsigned int output_width = input_width * 12;
    const unsigned int input_plane = input_height * input_width;
    const unsigned int output_plane = output_height * output_width;
    const float y_ratio = output_height == 1
                              ? 0.0f
                              : float(input_height - 1) / float(output_height - 1);
    const float x_ratio = output_width == 1
                              ? 0.0f
                              : float(input_width - 1) / float(output_width - 1);

    // Physical banks are exchanged logically when y0 advances to the old y1.
    // Each bank needs two reads per output pixel (x0 and x1).
    float row_a[kMaxInputWidth];
    float row_b[kMaxInputWidth];
#pragma HLS BIND_STORAGE variable=row_a type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=row_b type=ram_2p impl=bram

    for (unsigned int channel = 0; channel < 3; ++channel) {
        bool valid = false;
        bool a_is_y0 = true;
        unsigned int cached_y0 = 0;
        unsigned int cached_y1 = 0;
        const unsigned int channel_base = channel * input_plane;

        for (unsigned int oy = 0; oy < output_height; ++oy) {
            float sy = float(oy) * y_ratio;
            if (sy > float(input_height - 1)) sy = float(input_height - 1);
            const unsigned int y0 = (unsigned int)sy;  // floor for nonnegative sy
            const unsigned int y1 = y0 + 1 < input_height ? y0 + 1 : y0;
            const float wy = sy - float(y0);
            const float one_minus_wy = 1.0f - wy;

            if (!valid || y0 != cached_y0 && y0 != cached_y1) {
                for (unsigned int x = 0; x < input_width; ++x) {
                    row_a[x] = parameters_lowres[channel_base + y0 * input_width + x];
                    row_b[x] = parameters_lowres[channel_base + y1 * input_width + x];
                }
                a_is_y0 = true;
            } else if (y0 == cached_y1 && y0 != cached_y0) {
                a_is_y0 = !a_is_y0;
                if (y1 != y0) {
                    for (unsigned int x = 0; x < input_width; ++x) {
                        if (a_is_y0) {
                            row_b[x] = parameters_lowres[channel_base + y1 * input_width + x];
                        } else {
                            row_a[x] = parameters_lowres[channel_base + y1 * input_width + x];
                        }
                    }
                }
            }
            valid = true;
            cached_y0 = y0;
            cached_y1 = y1;

            for (unsigned int ox = 0; ox < output_width; ++ox) {
                float sx = float(ox) * x_ratio;
                if (sx > float(input_width - 1)) sx = float(input_width - 1);
                const unsigned int x0 = (unsigned int)sx;  // floor for nonnegative sx
                const unsigned int x1 = x0 + 1 < input_width ? x0 + 1 : x0;
                const float wx = sx - float(x0);
                const float one_minus_wx = 1.0f - wx;

                const float a0 = row_a[x0];
                const float a1 = row_a[x1];
                const float b0 = row_b[x0];
                const float b1 = row_b[x1];
                const float v00 = a_is_y0 ? a0 : b0;
                const float v01 = a_is_y0 ? a1 : b1;
                const float v10 = y0 == y1 ? v00 : (a_is_y0 ? b0 : a0);
                const float v11 = y0 == y1 ? v01 : (a_is_y0 ? b1 : a1);
                const float top = one_minus_wx * v00 + wx * v01;
                const float bottom = one_minus_wx * v10 + wx * v11;
                const float result = one_minus_wy * top + wy * bottom;
                parameters_fullres[channel * output_plane + oy * output_width + ox] = result;
            }
        }
    }
}
