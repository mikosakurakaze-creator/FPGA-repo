#include "curve.hpp"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
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

struct ErrorStats {
    double sum = 0.0;
    double maximum = 0.0;
    void add(float actual, float expected) {
        if (!std::isfinite(actual) || !std::isfinite(expected)) {
            throw std::runtime_error("non-finite output/reference");
        }
        const double error = std::abs(static_cast<double>(actual) - expected);
        sum += error;
        if (error > maximum) maximum = error;
    }
};
}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: tb_curve RAW_DIR\n";
        return 2;
    }
    try {
        const std::filesystem::path dir(argv[1]);
        const auto input = read_raw(dir / "model_input.f32");
        const auto parameter = read_raw(dir / "parameters_fullres.f32");
        const auto enhanced = read_raw(dir / "enhanced.f32");
        std::vector<std::vector<float>> references;
        for (int round = 1; round <= 8; ++round) {
            char name[40];
            std::snprintf(name, sizeof(name), "enhancement_iter_%02d.f32", round);
            references.push_back(read_raw(dir / name));
        }
        const auto count = input.size();
        if (parameter.size() != count || enhanced.size() != count) {
            throw std::runtime_error("input, parameter, and final reference sizes differ");
        }
        for (const auto& reference : references) {
            if (reference.size() != count) throw std::runtime_error("round reference size differs");
        }

        ErrorStats round_stats[8];
        ErrorStats final_stats;
        for (std::size_t index = 0; index < count; ++index) {
            float rounds[8];
            curve_fp32(input[index], parameter[index], rounds);
            for (int round = 0; round < 8; ++round) {
                round_stats[round].add(rounds[round], references[round][index]);
            }
            final_stats.add(rounds[7], enhanced[index]);
        }
        for (int round = 0; round < 8; ++round) {
            std::printf("round %02d: max_abs=%.9g mean_abs=%.9g\n", round + 1,
                        round_stats[round].maximum, round_stats[round].sum / count);
        }
        std::printf("enhanced: max_abs=%.9g mean_abs=%.9g elements=%zu\n",
                    final_stats.maximum, final_stats.sum / count, count);
        const double tolerance = 1e-6;
        if (final_stats.maximum > tolerance) {
            std::cerr << "FAIL: final maximum absolute error exceeds 1e-6\n";
            return 1;
        }
        std::cout << "PASS: final maximum absolute error <= 1e-6\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
