#ifndef CURVE_IMAGE_FIXED12_HPP
#define CURVE_IMAGE_FIXED12_HPP

#include <ap_fixed.h>

using curve_fixed12_t = ap_fixed<12, 2, AP_RND, AP_SAT>;

void curve_image_fixed12(const curve_fixed12_t* input,
                         const curve_fixed12_t* parameter,
                         curve_fixed12_t* output, unsigned int count);

#endif
