#include "bilinear_fp32.hpp"

void bilinear_fp32(const float* parameters_lowres, float* parameters_fullres,
                   unsigned int input_height, unsigned int input_width) {
#pragma HLS INTERFACE m_axi port=parameters_lowres offset=slave bundle=gmem_input
#pragma HLS INTERFACE m_axi port=parameters_fullres offset=slave bundle=gmem_output
#pragma HLS INTERFACE s_axilite port=parameters_lowres bundle=control
#pragma HLS INTERFACE s_axilite port=parameters_fullres bundle=control
#pragma HLS INTERFACE s_axilite port=input_height bundle=control
#pragma HLS INTERFACE s_axilite port=input_width bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    if (input_height == 0 || input_width == 0) return;

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

    for (unsigned int channel = 0; channel < 3; ++channel) {
        for (unsigned int oy = 0; oy < output_height; ++oy) {
            float sy = float(oy) * y_ratio;
            if (sy > float(input_height - 1)) sy = float(input_height - 1);
            // sy is nonnegative, so conversion to unsigned is floor(sy).
            const unsigned int y0 = (unsigned int)sy;
            const unsigned int y1 = y0 + 1 < input_height ? y0 + 1 : y0;
            const float wy = sy - float(y0);
            const float one_minus_wy = 1.0f - wy;
            for (unsigned int ox = 0; ox < output_width; ++ox) {
                float sx = float(ox) * x_ratio;
                if (sx > float(input_width - 1)) sx = float(input_width - 1);
                // sx is nonnegative, so conversion to unsigned is floor(sx).
                const unsigned int x0 = (unsigned int)sx;
                const unsigned int x1 = x0 + 1 < input_width ? x0 + 1 : x0;
                const float wx = sx - float(x0);
                const float one_minus_wx = 1.0f - wx;

                const unsigned int base = channel * input_plane;
                const float v00 = parameters_lowres[base + y0 * input_width + x0];
                const float v01 = parameters_lowres[base + y0 * input_width + x1];
                const float v10 = parameters_lowres[base + y1 * input_width + x0];
                const float v11 = parameters_lowres[base + y1 * input_width + x1];
                const float top = one_minus_wx * v00 + wx * v01;
                const float bottom = one_minus_wx * v10 + wx * v11;
                const float result = one_minus_wy * top + wy * bottom;
                parameters_fullres[channel * output_plane + oy * output_width + ox] = result;
            }
        }
    }
}
