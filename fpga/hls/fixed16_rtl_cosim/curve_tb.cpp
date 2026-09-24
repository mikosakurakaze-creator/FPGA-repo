#include "../curve_image_fixed16/curve_image_fixed16.hpp"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<float> read_raw(const std::string& path, std::size_t count) {
    std::vector<float> data(count);
    std::FILE* file = std::fopen(path.c_str(), "rb");
    if (!file) throw std::runtime_error("cannot open reference file");
    const auto read = std::fread(data.data(), sizeof(float), data.size(), file);
    const int extra = std::fgetc(file);
    std::fclose(file);
    if (read != data.size() || extra != EOF)
        throw std::runtime_error("reference file size mismatch");
    return data;
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("expected curve raw directory");
        constexpr unsigned int full_count = 2747520;
        constexpr unsigned int count = 512;
        constexpr unsigned int real_count = 448;
        constexpr unsigned int special_count = 8;
        static_assert(count == real_count + special_count + 56, "sample size mismatch");
        const std::string dir(argv[1]);
        const auto image_ref = read_raw(dir + "/model_input.f32", full_count);
        const auto parameter_ref = read_raw(dir + "/parameters_fullres.f32", full_count);
        if (image_ref.size() != full_count || parameter_ref.size() != full_count)
            throw std::runtime_error("reference count mismatch");

        std::vector<curve_fixed16_t> input(count), parameter(count), output(count);
        for (unsigned int i = 0; i < real_count; ++i) {
            const std::uint64_t index = std::uint64_t(i) * (full_count - 1) / (real_count - 1);
            input[i] = curve_fixed16_t(image_ref[index]);
            parameter[i] = curve_fixed16_t(parameter_ref[index]);
        }
        const float special_x[special_count] = {
            0.0f, 1.0f, 0.125f, 0.25f, 0.5f, 0.75f, 0.875f, 0.9999f};
        const float special_a[special_count] = {
            -0.35f, -0.05f, -0.33f, -0.27f, -0.20f, -0.12f, -0.08f, -0.30f};
        for (unsigned int j = 0; j < special_count; ++j) {
            input[real_count + j] = curve_fixed16_t(special_x[j]);
            parameter[real_count + j] = curve_fixed16_t(special_a[j]);
        }
        std::uint32_t state = 0x5eeda11u;
        for (unsigned int i = real_count + special_count; i < count; ++i) {
            state = state * 1664525u + 1013904223u;
            const float x = float(state & 0xffffu) / 65535.0f;
            state = state * 1664525u + 1013904223u;
            const float a = -0.35f + 0.30f * float(state & 0xffffu) / 65535.0f;
            input[i] = curve_fixed16_t(x);
            parameter[i] = curve_fixed16_t(a);
        }

        curve_image_fixed16(input.data(), parameter.data(), output.data(), count);

        double min_value = 2.0;
        double max_value = -2.0;
        unsigned int nonfinite = 0;
        unsigned int at_boundary = 0;
        for (const curve_fixed16_t value : output) {
            const double actual = value.to_double();
            nonfinite += !std::isfinite(actual);
            at_boundary += actual == -2.0 || actual == 2.0 - 1.0 / 16384.0;
            if (actual < min_value) min_value = actual;
            if (actual > max_value) max_value = actual;
        }
        std::printf("curve_samples=%u real=%u special=%u deterministic_random=%u\n",
                    count, real_count, special_count, count - real_count - special_count);
        std::printf("curve_c_golden_output_min=%.9g max=%.9g nonfinite=%u at_fixed16_boundary=%u\n",
                    min_value, max_value, nonfinite, at_boundary);
        if (nonfinite) throw std::runtime_error("non-finite C model output");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "FAIL: %s\n", error.what());
        return 1;
    }
}
