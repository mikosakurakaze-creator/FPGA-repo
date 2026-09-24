#ifndef CURVE_IMAGE_FIXED14_HPP
#define CURVE_IMAGE_FIXED14_HPP

#include <ap_fixed.h>

using curve_fixed14_t = ap_fixed<14, 2, AP_RND, AP_SAT>;

void curve_image_fixed14(const curve_fixed14_t* input,
                         const curve_fixed14_t* parameter,
                         curve_fixed14_t* output, unsigned int count);

#endif
