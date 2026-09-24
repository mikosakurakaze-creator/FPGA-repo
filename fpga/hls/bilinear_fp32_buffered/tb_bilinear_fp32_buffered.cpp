#include "bilinear_fp32_buffered.hpp"

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
std::vector<float> read_raw(const std::filesystem::path& path) {
    const auto bytes = std::filesystem::file_size(path);
    if (bytes == 0 || bytes % sizeof(float) != 0) {
        throw std::runtime_error("invalid float32 raw size: " + path.string());
    }
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
        std::cerr << "usage: tb_bilinear_fp32_buffered RAW_DIR\n";
        return 2;
    }
    try {
        const std::filesystem::path dir(argv[1]);
        const auto lowres = read_raw(dir / "parameters_lowres.f32");
        const auto fullres = read_raw(dir / "parameters_fullres.f32");
        constexpr unsigned int hi = 60;
        constexpr unsigned int wi = 106;
        constexpr unsigned int ho = hi * 12;
        constexpr unsigned int wo = wi * 12;
        constexpr unsigned int channels = 3;
        constexpr unsigned int input_count = channels * hi * wi;
        constexpr unsigned int output_count = channels * ho * wo;
        if (lowres.size() != input_count || fullres.size() != output_count) {
            throw std::runtime_error("reference element counts do not match NCHW shapes");
        }

        std::vector<float> output(output_count);
        bilinear_fp32_buffered(lowres.data(), output.data(), hi, wi);

        double max_abs_error = 0.0;
        double sum_abs_error = 0.0;
        unsigned long long input_nonfinite_count = 0;
        unsigned long long reference_nonfinite_count = 0;
        unsigned long long output_nonfinite_count = 0;
        for (float value : lowres) input_nonfinite_count += !std::isfinite(value);
        for (unsigned int index = 0; index < output_count; ++index) {
            reference_nonfinite_count += !std::isfinite(fullres[index]);
            output_nonfinite_count += !std::isfinite(output[index]);
            if (std::isfinite(fullres[index]) && std::isfinite(output[index])) {
                const double error = std::abs(double(output[index]) - double(fullres[index]));
                if (error > max_abs_error) max_abs_error = error;
                sum_abs_error += error;
            }
        }

        unsigned int corner_exact_to_input = 0;
        double corner_max_abs_vs_input = 0.0;
        double corner_max_abs_vs_reference = 0.0;
        for (unsigned int channel = 0; channel < channels; ++channel) {
            for (unsigned int edge_y = 0; edge_y < 2; ++edge_y) {
                for (unsigned int edge_x = 0; edge_x < 2; ++edge_x) {
                    const unsigned int iy = edge_y ? hi - 1 : 0;
                    const unsigned int ix = edge_x ? wi - 1 : 0;
                    const unsigned int oy = edge_y ? ho - 1 : 0;
                    const unsigned int ox = edge_x ? wo - 1 : 0;
                    const float source = lowres[channel * hi * wi + iy * wi + ix];
                    const unsigned int out_index = channel * ho * wo + oy * wo + ox;
                    const float actual = output[out_index];
                    const float expected = fullres[out_index];
                    corner_exact_to_input += actual == source;
                    const double input_error = std::abs(double(actual) - double(source));
                    const double ref_error = std::abs(double(actual) - double(expected));
                    if (input_error > corner_max_abs_vs_input)
                        corner_max_abs_vs_input = input_error;
                    if (ref_error > corner_max_abs_vs_reference)
                        corner_max_abs_vs_reference = ref_error;
                    std::printf("corner channel=%u output_yx=(%u,%u) input=%.9g output=%.9g reference=%.9g\n",
                                channel, oy, ox, source, actual, expected);
                }
            }
        }

        std::printf("output_shape=[1,%u,%u,%u] elements=%u\n",
                    channels, ho, wo, output_count);
        std::printf("max_abs_error=%.9g mean_abs_error=%.9g tolerance=1e-6\n",
                    max_abs_error, sum_abs_error / output_count);
        std::printf("input_nonfinite=%llu reference_nonfinite=%llu output_nonfinite=%llu\n",
                    input_nonfinite_count, reference_nonfinite_count, output_nonfinite_count);
        std::printf("corners_exact_to_input=%u/12 corner_max_abs_vs_input=%.9g corner_max_abs_vs_reference=%.9g\n",
                    corner_exact_to_input, corner_max_abs_vs_input, corner_max_abs_vs_reference);
        if (input_nonfinite_count || reference_nonfinite_count || output_nonfinite_count ||
            corner_exact_to_input != 12 || max_abs_error > 1e-6) {
            std::cerr << "FAIL: Bilinear FP32 CSim numerical checks\n";
            return 1;
        }
        std::cout << "PASS: Bilinear FP32 CSim numerical checks\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
