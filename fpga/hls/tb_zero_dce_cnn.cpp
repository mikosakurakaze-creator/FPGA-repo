#include "zero_dce_cnn_top.h"

#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<unsigned char> read_bytes(
    const std::string &path, std::size_t expected_bytes) {
    std::ifstream file(path.c_str(), std::ios::binary | std::ios::ate);
    if (!file) {
        throw std::runtime_error("cannot open: " + path);
    }
    const std::streamoff length = file.tellg();
    if (length < 0 || static_cast<std::size_t>(length) != expected_bytes) {
        throw std::runtime_error("unexpected file size: " + path);
    }
    std::vector<unsigned char> bytes(expected_bytes);
    file.seekg(0);
    file.read(reinterpret_cast<char *>(bytes.data()), length);
    if (!file) {
        throw std::runtime_error("cannot read: " + path);
    }
    return bytes;
}

template <typename T>
std::vector<T> decode_signed8(const std::string &path, std::size_t count) {
    const std::vector<unsigned char> bytes = read_bytes(path, count);
    std::vector<T> result(count);
    for (std::size_t index = 0; index < count; ++index) {
        const int signed_value = bytes[index] < 128
                                     ? static_cast<int>(bytes[index])
                                     : static_cast<int>(bytes[index]) - 256;
        result[index] = signed_value;
    }
    return result;
}

template <typename T>
std::vector<T> decode_signed16(const std::string &path, std::size_t count) {
    const std::vector<unsigned char> bytes = read_bytes(path, count * 2);
    std::vector<T> result(count);
    for (std::size_t index = 0; index < count; ++index) {
        const unsigned int raw = static_cast<unsigned int>(bytes[index * 2]) |
                                 (static_cast<unsigned int>(bytes[index * 2 + 1]) << 8);
        const int signed_value = raw < 32768U
                                     ? static_cast<int>(raw)
                                     : static_cast<int>(raw) - 65536;
        result[index] = signed_value;
    }
    return result;
}

template <typename T>
std::vector<T> decode_signed32(const std::string &path, std::size_t count) {
    const std::vector<unsigned char> bytes = read_bytes(path, count * 4);
    std::vector<T> result(count);
    for (std::size_t index = 0; index < count; ++index) {
        const unsigned long long raw =
            static_cast<unsigned long long>(bytes[index * 4]) |
            (static_cast<unsigned long long>(bytes[index * 4 + 1]) << 8) |
            (static_cast<unsigned long long>(bytes[index * 4 + 2]) << 16) |
            (static_cast<unsigned long long>(bytes[index * 4 + 3]) << 24);
        const long long signed_value = raw < 2147483648ULL
                                           ? static_cast<long long>(raw)
                                           : static_cast<long long>(raw) - 4294967296LL;
        result[index] = signed_value;
    }
    return result;
}

std::string path_in(const std::string &directory, const char *filename) {
    return directory + "/" + filename;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc > 2) {
        std::cerr << "usage: tb_zero_dce_cnn [hls_cnn_package_dir]\n";
        return 2;
    }
    try {
        const std::string directory = argc == 2 ? argv[1] : ".";
        std::vector<zero_dce_q16_t> input = decode_signed16<zero_dce_q16_t>(
            path_in(directory, "input_q14.bin"), ZERO_DCE_INPUT_ELEMENTS);
        std::vector<zero_dce_q8_t> weights = decode_signed8<zero_dce_q8_t>(
            path_in(directory, "weights_int8.bin"), ZERO_DCE_WEIGHT_ELEMENTS);
        std::vector<zero_dce_q32_t> bias = decode_signed32<zero_dce_q32_t>(
            path_in(directory, "bias_int32.bin"), ZERO_DCE_BIAS_ELEMENTS);
        std::vector<zero_dce_q8_t> fraction = decode_signed8<zero_dce_q8_t>(
            path_in(directory, "weight_frac.bin"),
            ZERO_DCE_WEIGHT_FRAC_ELEMENTS);
        std::vector<zero_dce_q16_t> lookup = decode_signed16<zero_dce_q16_t>(
            path_in(directory, "tanh_lut_q15.bin"),
            ZERO_DCE_TANH_LUT_ELEMENTS);
        std::vector<zero_dce_q16_t> expected = decode_signed16<zero_dce_q16_t>(
            path_in(directory, "expected_a_low_q14.bin"),
            ZERO_DCE_OUTPUT_ELEMENTS);
        std::vector<zero_dce_q16_t> actual(ZERO_DCE_OUTPUT_ELEMENTS);
        std::vector<zero_dce_q16_t> workspace(ZERO_DCE_WORKSPACE_ELEMENTS);

        zero_dce_cnn_top(input.data(), weights.data(), bias.data(),
                          fraction.data(), lookup.data(), actual.data(),
                          workspace.data());

        int mismatches = 0;
        int max_absolute_error = 0;
        for (int index = 0; index < ZERO_DCE_OUTPUT_ELEMENTS; ++index) {
            const int error = static_cast<int>(actual[index]) -
                              static_cast<int>(expected[index]);
            const int absolute_error = error < 0 ? -error : error;
            if (absolute_error != 0) {
                if (mismatches < 8) {
                    std::cerr << "mismatch index " << index << ": actual="
                              << static_cast<int>(actual[index]) << " expected="
                              << static_cast<int>(expected[index]) << "\n";
                }
                ++mismatches;
            }
            if (absolute_error > max_absolute_error) {
                max_absolute_error = absolute_error;
            }
        }
        std::cout << "A_low Q14: " << ZERO_DCE_OUTPUT_ELEMENTS
                  << " scalars, mismatches=" << mismatches
                  << ", max_abs_raw_error=" << max_absolute_error << "\n";
        return mismatches == 0 ? 0 : 1;
    } catch (const std::exception &error) {
        std::cerr << error.what() << "\n";
        return 2;
    }
}
