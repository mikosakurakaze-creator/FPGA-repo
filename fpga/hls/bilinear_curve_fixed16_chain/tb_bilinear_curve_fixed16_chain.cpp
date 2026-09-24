#include "../bilinear_fixed16_buffered/bilinear_fixed16_buffered.hpp"
#include "../curve_image_fixed16/curve_image_fixed16.hpp"

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <type_traits>
#include <vector>

static_assert(std::is_same<bilinear_fixed16_t, curve_fixed16_t>::value,
              "Bilinear output and Curve parameter must have the same Fixed16 type");

namespace {
constexpr double kFixedMin = -2.0;
constexpr double kFixedMax = 2.0 - 1.0 / 16384.0;

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

struct ErrorStats {
    double max_abs = 0.0;
    double sum_abs = 0.0;
    unsigned long long nonfinite = 0;

    void add(double actual, double expected) {
        if (!std::isfinite(actual) || !std::isfinite(expected)) {
            ++nonfinite;
            return;
        }
        const double error = std::abs(actual - expected);
        if (error > max_abs) max_abs = error;
        sum_abs += error;
    }
    double mean(unsigned int count) const { return sum_abs / count; }
};
}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: tb_bilinear_curve_fixed16_chain ZERO_DCE_PP_OUTPUT_DIR\n";
        return 2;
    }
    try {
        const std::filesystem::path base(argv[1]);
        const auto lowres_fp32 = read_raw(base / "bilinear_fp32_raw" / "parameters_lowres.f32");
        const auto fullres_fp32 = read_raw(base / "bilinear_fp32_raw" / "parameters_fullres.f32");
        const auto model_fp32 = read_raw(base / "curve_fp32_raw" / "model_input.f32");
        const auto enhanced_fp32 = read_raw(base / "curve_fp32_raw" / "enhanced.f32");

        constexpr unsigned int hi = 60;
        constexpr unsigned int wi = 106;
        constexpr unsigned int ho = hi * 12;
        constexpr unsigned int wo = wi * 12;
        constexpr unsigned int channels = 3;
        constexpr unsigned int low_count = channels * hi * wi;
        constexpr unsigned int full_count = channels * ho * wo;
        if (lowres_fp32.size() != low_count || fullres_fp32.size() != full_count ||
            model_fp32.size() != full_count || enhanced_fp32.size() != full_count)
            throw std::runtime_error("reference element counts do not match NCHW shapes");

        std::vector<bilinear_fixed16_t> lowres_fixed(low_count);
        std::vector<bilinear_fixed16_t> generated_full_fixed(full_count);
        std::vector<curve_fixed16_t> model_fixed(full_count);
        std::vector<curve_fixed16_t> direct_full_fixed(full_count);
        std::vector<curve_fixed16_t> baseline_output(full_count);
        std::vector<curve_fixed16_t> chain_output(full_count);
        if (generated_full_fixed.size() != model_fixed.size() ||
            generated_full_fixed.size() != direct_full_fixed.size())
            throw std::runtime_error("Bilinear intermediate size differs from Curve parameter size");

        unsigned long long lowres_out_of_range = 0;
        unsigned long long model_out_of_range = 0;
        unsigned long long direct_parameter_out_of_range = 0;
        unsigned long long lowres_nonfinite = 0;
        unsigned long long fullres_nonfinite = 0;
        unsigned long long model_nonfinite = 0;
        unsigned long long enhanced_nonfinite = 0;
        for (unsigned int i = 0; i < low_count; ++i) {
            const float value = lowres_fp32[i];
            lowres_nonfinite += !std::isfinite(value);
            if (std::isfinite(value)) {
                lowres_out_of_range += value < kFixedMin || value > kFixedMax;
                lowres_fixed[i] = bilinear_fixed16_t(value);
            }
        }
        for (unsigned int i = 0; i < full_count; ++i) {
            const float image_value = model_fp32[i];
            const float parameter_value = fullres_fp32[i];
            model_nonfinite += !std::isfinite(image_value);
            fullres_nonfinite += !std::isfinite(parameter_value);
            enhanced_nonfinite += !std::isfinite(enhanced_fp32[i]);
            if (std::isfinite(image_value)) {
                model_out_of_range += image_value < kFixedMin || image_value > kFixedMax;
                model_fixed[i] = curve_fixed16_t(image_value);
            }
            if (std::isfinite(parameter_value)) {
                direct_parameter_out_of_range += parameter_value < kFixedMin ||
                                                 parameter_value > kFixedMax;
                direct_full_fixed[i] = curve_fixed16_t(parameter_value);
            }
        }
        if (lowres_nonfinite || fullres_nonfinite || model_nonfinite || enhanced_nonfinite)
            throw std::runtime_error("non-finite FP32 reference input detected");

        // The Fixed16 intermediate is passed directly to Curve, without a float round trip.
        bilinear_fixed16_buffered(lowres_fixed.data(), generated_full_fixed.data(), hi, wi);
        curve_image_fixed16(model_fixed.data(), direct_full_fixed.data(),
                            baseline_output.data(), full_count);
        curve_image_fixed16(model_fixed.data(), generated_full_fixed.data(),
                            chain_output.data(), full_count);

        ErrorStats bilinear_error;
        ErrorStats curve_baseline_error;
        ErrorStats chain_error;
        ErrorStats propagated_difference;
        double chain_min = kFixedMax;
        double chain_max = kFixedMin;
        unsigned long long chain_at_saturation_limit = 0;
        unsigned long long intermediate_at_saturation_limit = 0;
        unsigned long long baseline_at_saturation_limit = 0;
        unsigned long long intermediate_differs_from_direct = 0;
        for (unsigned int i = 0; i < full_count; ++i) {
            const double parameter = generated_full_fixed[i].to_double();
            const double direct_parameter = direct_full_fixed[i].to_double();
            const double baseline = baseline_output[i].to_double();
            const double chain = chain_output[i].to_double();
            bilinear_error.add(parameter, double(fullres_fp32[i]));
            curve_baseline_error.add(baseline, double(enhanced_fp32[i]));
            chain_error.add(chain, double(enhanced_fp32[i]));
            propagated_difference.add(chain, baseline);
            intermediate_differs_from_direct += parameter != direct_parameter;
            intermediate_at_saturation_limit += parameter == kFixedMin || parameter == kFixedMax;
            baseline_at_saturation_limit += baseline == kFixedMin || baseline == kFixedMax;
            chain_at_saturation_limit += chain == kFixedMin || chain == kFixedMax;
            if (chain < chain_min) chain_min = chain;
            if (chain > chain_max) chain_max = chain;
        }

        std::printf("shapes lowres=[1,3,%u,%u] fullres/model/enhanced=[1,3,%u,%u]\n",
                    hi, wi, ho, wo);
        std::printf("elements lowres=%u intermediate=%zu curve_parameter=%zu final=%u\n",
                    low_count, generated_full_fixed.size(), direct_full_fixed.size(), full_count);
        std::printf("type_compatible=%d fixed16_bits=16 integer_bits=2 fractional_bits=14\n",
                    std::is_same<bilinear_fixed16_t, curve_fixed16_t>::value);
        std::printf("input_out_of_range lowres=%llu model=%llu direct_fullres=%llu\n",
                    lowres_out_of_range, model_out_of_range, direct_parameter_out_of_range);
        std::printf("reference_nonfinite lowres=%llu fullres=%llu model=%llu enhanced=%llu\n",
                    lowres_nonfinite, fullres_nonfinite, model_nonfinite, enhanced_nonfinite);
        std::printf("A_bilinear_intermediate max_abs_error=%.12g mean_abs_error=%.12g nonfinite=%llu at_saturation_limit=%llu differs_from_direct_quantized=%llu\n",
                    bilinear_error.max_abs, bilinear_error.mean(full_count), bilinear_error.nonfinite,
                    intermediate_at_saturation_limit, intermediate_differs_from_direct);
        std::printf("B_curve_reference_parameter max_abs_error=%.12g mean_abs_error=%.12g nonfinite=%llu at_saturation_limit=%llu\n",
                    curve_baseline_error.max_abs, curve_baseline_error.mean(full_count),
                    curve_baseline_error.nonfinite, baseline_at_saturation_limit);
        std::printf("C_chain_vs_enhanced max_abs_error=%.12g mean_abs_error=%.12g output_min=%.12g output_max=%.12g nonfinite=%llu at_saturation_limit=%llu\n",
                    chain_error.max_abs, chain_error.mean(full_count), chain_min, chain_max,
                    chain_error.nonfinite, chain_at_saturation_limit);
        std::printf("D_chain_vs_curve_baseline max_abs_difference=%.12g mean_abs_difference=%.12g nonfinite=%llu\n",
                    propagated_difference.max_abs, propagated_difference.mean(full_count),
                    propagated_difference.nonfinite);
        if (bilinear_error.nonfinite || curve_baseline_error.nonfinite ||
            chain_error.nonfinite || propagated_difference.nonfinite)
            throw std::runtime_error("non-finite Fixed16 output detected");
        std::cout << "CSIM chain comparison complete (no accuracy threshold set)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
