#ifndef CURVE_IMAGE_FIXED16_HPP
#define CURVE_IMAGE_FIXED16_HPP

#include <ap_fixed.h>

using curve_fixed16_t = ap_fixed<16, 2, AP_RND, AP_SAT>;

void curve_image_fixed16(const curve_fixed16_t* input,
                         const curve_fixed16_t* parameter,
                         curve_fixed16_t* output, unsigned int count);

#endif
