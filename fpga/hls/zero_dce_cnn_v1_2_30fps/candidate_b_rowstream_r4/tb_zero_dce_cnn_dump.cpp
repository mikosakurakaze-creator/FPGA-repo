#include "zero_dce_cnn_top.h"

#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<unsigned char> read_bytes(const std::string &path, std::size_t expected_bytes) {
    std::ifstream file(path.c_str(), std::ios::binary | std::ios::ate);
    if (!file) throw std::runtime_error("cannot open: " + path);
    const std::streamoff length = file.tellg();
    if (length < 0 || static_cast<std::size_t>(length) != expected_bytes)
        throw std::runtime_error("unexpected file size: " + path);
    std::vector<unsigned char> bytes(expected_bytes);
    file.seekg(0);
    file.read(reinterpret_cast<char *>(bytes.data()), length);
    if (!file) throw std::runtime_error("cannot read: " + path);
    return bytes;
}

template <typename T>
std::vector<T> decode_signed(const std::string &path, std::size_t count, unsigned width) {
    const auto bytes = read_bytes(path, count * width);
    std::vector<T> result(count);
    const unsigned long long modulus = 1ULL << (8 * width);
    for (std::size_t i = 0; i < count; ++i) {
        unsigned long long bits = 0;
        for (unsigned j = 0; j < width; ++j)
            bits |= static_cast<unsigned long long>(bytes[i * width + j]) << (8 * j);
        const long long signed_value = bits < modulus / 2
            ? static_cast<long long>(bits)
            : static_cast<long long>(bits) - static_cast<long long>(modulus);
        result[i] = signed_value;
    }
    return result;
}

std::string path_in(const std::string &directory, const char *filename) {
    return directory + "/" + filename;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    try {
        const std::string directory(argv[1]);
        auto input = decode_signed<zero_dce_q16_t>(path_in(directory, "input_q14.bin"), ZERO_DCE_INPUT_ELEMENTS, 2);
        auto weights = decode_signed<zero_dce_q8_t>(path_in(directory, "weights_int8.bin"), ZERO_DCE_WEIGHT_ELEMENTS, 1);
        auto bias = decode_signed<zero_dce_q32_t>(path_in(directory, "bias_int32.bin"), ZERO_DCE_BIAS_ELEMENTS, 4);
        auto fraction = decode_signed<zero_dce_q8_t>(path_in(directory, "weight_frac.bin"), ZERO_DCE_WEIGHT_FRAC_ELEMENTS, 1);
        auto lookup = decode_signed<zero_dce_q16_t>(path_in(directory, "tanh_lut_q15.bin"), ZERO_DCE_TANH_LUT_ELEMENTS, 2);
        auto expected = decode_signed<zero_dce_q16_t>(path_in(directory, "expected_a_low_q14.bin"), ZERO_DCE_OUTPUT_ELEMENTS, 2);
        std::vector<zero_dce_q16_t> actual(ZERO_DCE_OUTPUT_ELEMENTS);
        std::vector<zero_dce_q16_t> workspace(ZERO_DCE_WORKSPACE_ELEMENTS);
        zero_dce_cnn_top(input.data(), weights.data(), bias.data(), fraction.data(),
                         lookup.data(), actual.data(), workspace.data());
        std::ofstream output(path_in(directory, "cnn_csim_actual_a_low_q14.bin"), std::ios::binary);
        if (!output) throw std::runtime_error("cannot create CSim vector");
        int mismatches = 0;
        int max_abs_raw_error = 0;
        long long sum_abs_raw_error = 0;
        for (int i = 0; i < ZERO_DCE_OUTPUT_ELEMENTS; ++i) {
            const int raw = static_cast<int>(actual[i]);
            const unsigned int bits = static_cast<unsigned int>(raw) & 0xffffU;
            const char pair[2] = {static_cast<char>(bits & 0xffU), static_cast<char>((bits >> 8) & 0xffU)};
            output.write(pair, 2);
            const int error = raw - static_cast<int>(expected[i]);
            const int abs_error = error < 0 ? -error : error;
            mismatches += abs_error != 0;
            if (abs_error > max_abs_raw_error) max_abs_raw_error = abs_error;
            sum_abs_raw_error += abs_error;
        }
        if (!output) throw std::runtime_error("cannot write CSim vector");
        std::cout << "A_low Q14: " << ZERO_DCE_OUTPUT_ELEMENTS
                  << " scalars, mismatches=" << mismatches
                  << ", max_abs_raw_error=" << max_abs_raw_error
                  << ", mean_abs_raw_error=" << static_cast<double>(sum_abs_raw_error) / ZERO_DCE_OUTPUT_ELEMENTS << "\n";
        return mismatches == 0 ? 0 : 1;
    } catch (const std::exception &error) {
        std::cerr << error.what() << "\n";
        return 2;
    }
}


