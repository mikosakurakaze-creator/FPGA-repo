#include "curve_image.hpp"

void curve_image_fp32(const float* input, const float* parameter, float* output,
                      unsigned int count) {
    for (unsigned int index = 0; index < count; ++index) {
        float x = input[index];
        const float a = parameter[index];
        for (int iteration = 0; iteration < 8; ++iteration) {
            x = x + a * (x * x - x);
        }
        output[index] = x;
    }
}
