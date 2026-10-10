#include "curve_image_fixed12.hpp"

// Full precision of each fixed-point operation is retained until the update
// is explicitly rounded and saturated back to the 12-bit pixel format.
using square_t = ap_fixed<24, 4, AP_RND, AP_SAT>;  // 20 fractional bits
using delta_t = ap_fixed<25, 5, AP_RND, AP_SAT>;   // 20 fractional bits
using term_t = ap_fixed<37, 7, AP_RND, AP_SAT>;    // 30 fractional bits
using sum_t = ap_fixed<38, 8, AP_RND, AP_SAT>;     // 30 fractional bits

void curve_image_fixed12(const curve_fixed12_t* input,
                         const curve_fixed12_t* parameter,
                         curve_fixed12_t* output, unsigned int count) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_input
#pragma HLS INTERFACE m_axi port=parameter offset=slave bundle=gmem_parameter
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_output
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=parameter bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=count bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    for (unsigned int index = 0; index < count; ++index) {
        curve_fixed12_t x = input[index];
        const curve_fixed12_t a = parameter[index];
        for (int iteration = 0; iteration < 8; ++iteration) {
            const square_t square = x * x;
            const delta_t delta = square - x;
            const term_t term = a * delta;
            const sum_t updated = x + term;  // x + A * (x*x - x)
            x = curve_fixed12_t(updated);
        }
        output[index] = x;
    }
}
