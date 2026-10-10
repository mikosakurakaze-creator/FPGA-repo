#include "../bilinear_fixed16_buffered/bilinear_fixed16_buffered.hpp"

#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <vector>

int main() {
    try {
        constexpr unsigned int hi = 3;
        constexpr unsigned int wi = 4;
        constexpr unsigned int ho = hi * 12;
        constexpr unsigned int wo = wi * 12;
        constexpr unsigned int channels = 3;
        constexpr unsigned int input_count = channels * hi * wi;
        constexpr unsigned int output_count = channels * ho * wo;
        std::vector<bilinear_fixed16_t> input(input_count), output(output_count);
        for (unsigned int channel = 0; channel < channels; ++channel) {
            for (unsigned int y = 0; y < hi; ++y) {
                for (unsigned int x = 0; x < wi; ++x) {
                    const float value = -0.35f + 0.06f * channel + 0.04f * y +
                                        0.03f * x + 0.005f * ((x + y) & 1u);
                    input[channel * hi * wi + y * wi + x] = bilinear_fixed16_t(value);
                }
            }
        }

        bilinear_fixed16_buffered(input.data(), output.data(), hi, wi);

        double min_value = 2.0;
        double max_value = -2.0;
        unsigned int nonfinite = 0;
        unsigned int exact_corners = 0;
        for (const bilinear_fixed16_t value : output) {
            const double actual = value.to_double();
            nonfinite += !std::isfinite(actual);
            if (actual < min_value) min_value = actual;
            if (actual > max_value) max_value = actual;
        }
        for (unsigned int channel = 0; channel < channels; ++channel) {
            for (unsigned int edge_y = 0; edge_y < 2; ++edge_y) {
                for (unsigned int edge_x = 0; edge_x < 2; ++edge_x) {
                    const unsigned int iy = edge_y ? hi - 1 : 0;
                    const unsigned int ix = edge_x ? wi - 1 : 0;
                    const unsigned int oy = edge_y ? ho - 1 : 0;
                    const unsigned int ox = edge_x ? wo - 1 : 0;
                    const double source = input[channel * hi * wi + iy * wi + ix].to_double();
                    const double actual = output[channel * ho * wo + oy * wo + ox].to_double();
                    exact_corners += actual == source;
                    std::printf("corner channel=%u output_yx=(%u,%u) input=%.9g output=%.9g\n",
                                channel, oy, ox, source, actual);
                }
            }
        }
        std::printf("bilinear_shape=[1,%u,%u,%u] output_elements=%u input_elements=%u\n",
                    channels, ho, wo, output_count, input_count);
        std::printf("bilinear_c_golden_output_min=%.9g max=%.9g nonfinite=%u exact_corners=%u/12\n",
                    min_value, max_value, nonfinite, exact_corners);
        if (nonfinite || exact_corners != 12)
            throw std::runtime_error("invalid C model output");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "FAIL: %s\n", error.what());
        return 1;
    }
}
