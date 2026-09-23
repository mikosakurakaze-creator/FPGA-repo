#include "curve_image.hpp"

void curve_image_fp32(const float* input, const float* parameter, float* output,
                      unsigned int count) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_input
#pragma HLS INTERFACE m_axi port=parameter offset=slave bundle=gmem_parameter
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_output
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=parameter bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=count bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    for (unsigned int index = 0; index < count; ++index) {
        float x = input[index];
        const float a = parameter[index];
        for (int iteration = 0; iteration < 8; ++iteration) {
            x = x + a * (x * x - x);
        }
        output[index] = x;
    }
}
