#include "curve_image_fixed12.hpp"

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
        std::cerr << "usage: tb_curve_image_fixed12 RAW_DIR\n";
        return 2;
    }
    try {
        const std::filesystem::path dir(argv[1]);
        const auto input_fp32 = read_raw(dir / "model_input.f32");
        const auto parameter_fp32 = read_raw(dir / "parameters_fullres.f32");
        const auto enhanced_fp32 = read_raw(dir / "enhanced.f32");
        constexpr unsigned int count = 2747520;
        if (input_fp32.size() != count || parameter_fp32.size() != count ||
            enhanced_fp32.size() != count) {
            throw std::runtime_error("reference tensor size differs from 2,747,520 elements");
        }

        std::vector<curve_fixed12_t> input(count), parameter(count), output(count);
        constexpr double fixed_min = -2.0;
        constexpr double fixed_max = 2.0 - 1.0 / 1024.0;
        unsigned long long input_saturation_count = 0;
        unsigned long long parameter_saturation_count = 0;
        for (unsigned int index = 0; index < count; ++index) {
            if (!std::isfinite(input_fp32[index]) || !std::isfinite(parameter_fp32[index]) ||
                !std::isfinite(enhanced_fp32[index])) {
                throw std::runtime_error("non-finite FP32 input/parameter/reference");
            }
            input_saturation_count += input_fp32[index] < fixed_min || input_fp32[index] > fixed_max;
            parameter_saturation_count += parameter_fp32[index] < fixed_min || parameter_fp32[index] > fixed_max;
            input[index] = curve_fixed12_t(input_fp32[index]);
            parameter[index] = curve_fixed12_t(parameter_fp32[index]);
        }

        curve_image_fixed12(input.data(), parameter.data(), output.data(), count);

        double max_abs_error = 0.0;
        double sum_abs_error = 0.0;
        double output_min = fixed_max;
        double output_max = fixed_min;
        unsigned long long output_at_saturation_limit_count = 0;
        for (unsigned int index = 0; index < count; ++index) {
            const double actual = output[index].to_double();
            if (!std::isfinite(actual)) throw std::runtime_error("non-finite Fixed12 output");
            if (actual < output_min) output_min = actual;
            if (actual > output_max) output_max = actual;
            output_at_saturation_limit_count += actual == fixed_min || actual == fixed_max;
            const double error = std::abs(actual - enhanced_fp32[index]);
            if (error > max_abs_error) max_abs_error = error;
            sum_abs_error += error;
        }
        std::printf("elements=%u max_abs_error=%.9g mean_abs_error=%.9g\n",
                    count, max_abs_error, sum_abs_error / count);
        std::printf("input_saturation_count=%llu parameter_saturation_count=%llu\n",
                    input_saturation_count, parameter_saturation_count);
        std::printf("output_min=%.9g output_max=%.9g output_at_saturation_limit_count=%llu\n",
                    output_min, output_max, output_at_saturation_limit_count);
        std::cout << "CSIM numerical comparison complete (no acceptance threshold set)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
