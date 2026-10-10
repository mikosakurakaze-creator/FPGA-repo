#include "curve_image.hpp"

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
        std::cerr << "usage: tb_curve_image RAW_DIR\n";
        return 2;
    }
    try {
        const std::filesystem::path dir(argv[1]);
        const auto input = read_raw(dir / "model_input.f32");
        const auto parameter = read_raw(dir / "parameters_fullres.f32");
        const auto enhanced = read_raw(dir / "enhanced.f32");
        constexpr unsigned int expected_count = 2747520;
        if (input.size() != expected_count || parameter.size() != expected_count ||
            enhanced.size() != expected_count) {
            throw std::runtime_error("reference tensor size differs from 2,747,520 elements");
        }

        std::vector<float> output(expected_count);
        curve_image_fp32(input.data(), parameter.data(), output.data(), expected_count);

        double max_abs_error = 0.0;
        double sum_abs_error = 0.0;
        for (unsigned int index = 0; index < expected_count; ++index) {
            if (!std::isfinite(output[index]) || !std::isfinite(enhanced[index])) {
                throw std::runtime_error("non-finite output/reference");
            }
            const double error = std::abs(static_cast<double>(output[index]) - enhanced[index]);
            if (error > max_abs_error) max_abs_error = error;
            sum_abs_error += error;
        }
        std::printf("elements=%u max_abs_error=%.9g mean_abs_error=%.9g\n",
                    expected_count, max_abs_error, sum_abs_error / expected_count);
        if (max_abs_error > 1e-6) {
            std::cerr << "FAIL: max_abs_error exceeds 1e-6\n";
            return 1;
        }
        std::cout << "PASS: max_abs_error <= 1e-6\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
