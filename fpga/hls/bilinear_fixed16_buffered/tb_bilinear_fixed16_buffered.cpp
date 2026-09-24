#include "bilinear_fixed16_buffered.hpp"

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
std::vector<float> read_raw(const std::filesystem::path& path) {
    const auto bytes = std::filesystem::file_size(path);
    if (bytes == 0 || bytes % sizeof(float) != 0)
        throw std::runtime_error("invalid float32 raw size: " + path.string());
    std::vector<float> data(bytes / sizeof(float));
    std::FILE* file = std::fopen(path.string().c_str(), "rb");
    if (!file) throw std::runtime_error("cannot open: " + path.string());
    const auto read = std::fread(data.data(), sizeof(float), data.size(), file);
    std::fclose(file);
    if (read != data.size()) throw std::runtime_error("short read: " + path.string());
    return data;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: tb_bilinear_fixed16_buffered RAW_DIR\n";
        return 2;
    }
    try {
        const std::filesystem::path dir(argv[1]);
        const auto lowres_fp32 = read_raw(dir / "parameters_lowres.f32");
        const auto fullres_fp32 = read_raw(dir / "parameters_fullres.f32");
        constexpr unsigned int hi = 60;
        constexpr unsigned int wi = 106;
        constexpr unsigned int ho = hi * 12;
        constexpr unsigned int wo = wi * 12;
        constexpr unsigned int channels = 3;
        constexpr unsigned int input_count = channels * hi * wi;
        constexpr unsigned int output_count = channels * ho * wo;
        if (lowres_fp32.size() != input_count || fullres_fp32.size() != output_count)
            throw std::runtime_error("reference element counts do not match NCHW shapes");

        constexpr double fixed_min = -2.0;
        constexpr double fixed_max = 2.0 - 1.0 / 16384.0;
        std::vector<bilinear_fixed16_t> input(input_count), output(output_count);
        unsigned long long input_out_of_range = 0;
        unsigned long long input_nonfinite = 0;
        unsigned long long reference_nonfinite = 0;
        for (unsigned int index = 0; index < input_count; ++index) {
            const float value = lowres_fp32[index];
            input_nonfinite += !std::isfinite(value);
            if (std::isfinite(value)) {
                input_out_of_range += value < fixed_min || value > fixed_max;
                input[index] = bilinear_fixed16_t(value);
            }
        }
        for (float value : fullres_fp32) reference_nonfinite += !std::isfinite(value);
        if (input_nonfinite || reference_nonfinite)
            throw std::runtime_error("non-finite FP32 input/reference");

        bilinear_fixed16_buffered(input.data(), output.data(), hi, wi);

        double max_abs_error = 0.0;
        double sum_abs_error = 0.0;
        double output_min = fixed_max;
        double output_max = fixed_min;
        unsigned long long output_nonfinite = 0;
        unsigned long long output_at_saturation_limit = 0;
        for (unsigned int index = 0; index < output_count; ++index) {
            const double actual = output[index].to_double();
            output_nonfinite += !std::isfinite(actual);
            output_at_saturation_limit += actual == fixed_min || actual == fixed_max;
            if (actual < output_min) output_min = actual;
            if (actual > output_max) output_max = actual;
            const double error = std::abs(actual - double(fullres_fp32[index]));
            if (error > max_abs_error) max_abs_error = error;
            sum_abs_error += error;
        }

        unsigned int corners_exact_to_quantized_input = 0;
        double corner_max_abs_vs_quantized_input = 0.0;
        double corner_max_abs_vs_reference = 0.0;
        for (unsigned int channel = 0; channel < channels; ++channel) {
            for (unsigned int edge_y = 0; edge_y < 2; ++edge_y) {
                for (unsigned int edge_x = 0; edge_x < 2; ++edge_x) {
                    const unsigned int iy = edge_y ? hi - 1 : 0;
                    const unsigned int ix = edge_x ? wi - 1 : 0;
                    const unsigned int oy = edge_y ? ho - 1 : 0;
                    const unsigned int ox = edge_x ? wo - 1 : 0;
                    const unsigned int input_index = channel * hi * wi + iy * wi + ix;
                    const unsigned int output_index = channel * ho * wo + oy * wo + ox;
                    const double source = input[input_index].to_double();
                    const double actual = output[output_index].to_double();
                    const double expected = double(fullres_fp32[output_index]);
                    corners_exact_to_quantized_input += actual == source;
                    const double input_error = std::abs(actual - source);
                    const double ref_error = std::abs(actual - expected);
                    if (input_error > corner_max_abs_vs_quantized_input)
                        corner_max_abs_vs_quantized_input = input_error;
                    if (ref_error > corner_max_abs_vs_reference)
                        corner_max_abs_vs_reference = ref_error;
                    std::printf("corner channel=%u output_yx=(%u,%u) quantized_input=%.9g output=%.9g reference=%.9g\n",
                                channel, oy, ox, source, actual, expected);
                }
            }
        }

        std::printf("output_shape=[1,%u,%u,%u] elements=%u\n", channels, ho, wo, output_count);
        std::printf("max_abs_error=%.12g mean_abs_error=%.12g\n",
                    max_abs_error, sum_abs_error / output_count);
        std::printf("input_out_of_range=%llu input_nonfinite=%llu reference_nonfinite=%llu output_nonfinite=%llu\n",
                    input_out_of_range, input_nonfinite, reference_nonfinite, output_nonfinite);
        std::printf("output_min=%.9g output_max=%.9g output_at_saturation_limit=%llu\n",
                    output_min, output_max, output_at_saturation_limit);
        std::printf("corners_exact_to_quantized_input=%u/12 corner_max_abs_vs_quantized_input=%.12g corner_max_abs_vs_reference=%.12g\n",
                    corners_exact_to_quantized_input, corner_max_abs_vs_quantized_input,
                    corner_max_abs_vs_reference);
        if (output_nonfinite || corners_exact_to_quantized_input != 12)
            throw std::runtime_error("non-finite output or unexpected corner behavior");
        std::cout << "CSIM numerical comparison complete (no accuracy threshold set)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
