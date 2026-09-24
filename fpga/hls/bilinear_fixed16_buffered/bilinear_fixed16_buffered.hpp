#ifndef BILINEAR_FIXED16_BUFFERED_HPP
#define BILINEAR_FIXED16_BUFFERED_HPP

#include <ap_fixed.h>

// V1: NCHW, batch 1, three channels, scale factor 12, input width <= 128.
using bilinear_fixed16_t = ap_fixed<16, 2, AP_RND, AP_SAT>;

void bilinear_fixed16_buffered(const bilinear_fixed16_t* parameters_lowres,
                               bilinear_fixed16_t* parameters_fullres,
                               unsigned int input_height, unsigned int input_width);

#endif
