#include "bilinear_fixed16_buffered.hpp"

namespace {
constexpr unsigned int kMaxInputWidth = 128;

using coord_t = ap_ufixed<48, 16, AP_RND, AP_SAT>;   // 32 fractional bits
using ratio_t = ap_ufixed<33, 1, AP_RND, AP_SAT>;    // 32 fractional bits
using weight_t = ap_ufixed<33, 1, AP_RND, AP_SAT>;   // 32 fractional bits
using hproduct_t = ap_fixed<49, 3, AP_RND, AP_SAT>;  // 46 fractional bits
using hsum_t = ap_fixed<50, 4, AP_RND, AP_SAT>;      // 46 fractional bits
using vproduct_t = ap_fixed<65, 5, AP_RND, AP_SAT>;  // 60 fractional bits
using vsum_t = ap_fixed<66, 6, AP_RND, AP_SAT>;      // 60 fractional bits
}

void bilinear_fixed16_buffered(const bilinear_fixed16_t* parameters_lowres,
                               bilinear_fixed16_t* parameters_fullres,
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
    const ratio_t y_ratio = output_height == 1
                                ? ratio_t(0)
                                : ratio_t(coord_t(input_height - 1) / coord_t(output_height - 1));
    const ratio_t x_ratio = output_width == 1
                                ? ratio_t(0)
                                : ratio_t(coord_t(input_width - 1) / coord_t(output_width - 1));

    bilinear_fixed16_t row_a[kMaxInputWidth];
    bilinear_fixed16_t row_b[kMaxInputWidth];
#pragma HLS BIND_STORAGE variable=row_a type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=row_b type=ram_2p impl=bram

    for (unsigned int channel = 0; channel < 3; ++channel) {
        bool valid = false;
        bool a_is_y0 = true;
        unsigned int cached_y0 = 0;
        unsigned int cached_y1 = 0;
        const unsigned int channel_base = channel * input_plane;

        for (unsigned int oy = 0; oy < output_height; ++oy) {
            coord_t sy = coord_t(oy * y_ratio);
            if (oy == output_height - 1 || sy > coord_t(input_height - 1))
                sy = coord_t(input_height - 1);
            const unsigned int y0 = (unsigned int)sy;
            const unsigned int y1 = y0 + 1 < input_height ? y0 + 1 : y0;
            const weight_t wy = weight_t(sy - coord_t(y0));
            const weight_t one_minus_wy = weight_t(1) - wy;

            if (!valid || (y0 != cached_y0 && y0 != cached_y1)) {
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
                coord_t sx = coord_t(ox * x_ratio);
                if (ox == output_width - 1 || sx > coord_t(input_width - 1))
                    sx = coord_t(input_width - 1);
                const unsigned int x0 = (unsigned int)sx;
                const unsigned int x1 = x0 + 1 < input_width ? x0 + 1 : x0;
                const weight_t wx = weight_t(sx - coord_t(x0));
                const weight_t one_minus_wx = weight_t(1) - wx;

                const bilinear_fixed16_t a0 = row_a[x0];
                const bilinear_fixed16_t a1 = row_a[x1];
                const bilinear_fixed16_t b0 = row_b[x0];
                const bilinear_fixed16_t b1 = row_b[x1];
                const bilinear_fixed16_t v00 = a_is_y0 ? a0 : b0;
                const bilinear_fixed16_t v01 = a_is_y0 ? a1 : b1;
                const bilinear_fixed16_t v10 = y0 == y1 ? v00 : (a_is_y0 ? b0 : a0);
                const bilinear_fixed16_t v11 = y0 == y1 ? v01 : (a_is_y0 ? b1 : a1);

                const hproduct_t top_left = hproduct_t(one_minus_wx * v00);
                const hproduct_t top_right = hproduct_t(wx * v01);
                const hproduct_t bottom_left = hproduct_t(one_minus_wx * v10);
                const hproduct_t bottom_right = hproduct_t(wx * v11);
                const hsum_t top = hsum_t(top_left + top_right);
                const hsum_t bottom = hsum_t(bottom_left + bottom_right);
                const vproduct_t upper = vproduct_t(one_minus_wy * top);
                const vproduct_t lower = vproduct_t(wy * bottom);
                const vsum_t result = vsum_t(upper + lower);
                parameters_fullres[channel * output_plane + oy * output_width + ox] =
                    bilinear_fixed16_t(result);
            }
        }
    }
}
