#include "../../hls/bilinear_fixed16_buffered/bilinear_fixed16_buffered.hpp"
#include "../../hls/curve_image_fixed16/curve_image_fixed16.hpp"
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

static std::vector<int16_t> read_raw(const std::string &path, size_t count) {
    std::vector<int16_t> values(count);
    FILE *f = std::fopen(path.c_str(), "rb");
    if (!f) throw std::runtime_error("Missing raw input");
    size_t n = std::fread(values.data(), 2, count, f);
    int extra = std::fgetc(f);
    std::fclose(f);
    if (n != count || extra != EOF) throw std::runtime_error("Wrong raw size");
    return values;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const std::string dir(argv[1]);
    const size_t n = 2747520;
    auto low = read_raw(dir + "/expected_a_low_q14.bin", 19080);
    auto model = read_raw(dir + "/model_input_q14.bin", n);
    auto expected_full = read_raw(dir + "/expected_a_full_q14.bin", n);
    auto expected_out = read_raw(dir + "/expected_enhanced_q14.bin", n);
    std::vector<bilinear_fixed16_t> a_low(19080), a_full(n);
    std::vector<curve_fixed16_t> image(n), enhanced(n);
    for (size_t i=0;i<19080;++i) a_low[i].range(15,0)=uint16_t(low[i]);
    for (size_t i=0;i<n;++i) image[i].range(15,0)=uint16_t(model[i]);
    bilinear_fixed16_buffered(a_low.data(),a_full.data(),60,106);
    uint64_t b_errors=0,c_errors=0;
    for (size_t i=0;i<n;++i) b_errors+=a_full[i].range(15,0).to_uint()!=uint16_t(expected_full[i]);
    std::printf("Bilinear vendor/reference raw count=%zu mismatches=%llu\n",n,(unsigned long long)b_errors);
    std::fflush(stdout);
    curve_image_fixed16(image.data(),a_full.data(),enhanced.data(),n);
    for (size_t i=0;i<n;++i) c_errors+=enhanced[i].range(15,0).to_uint()!=uint16_t(expected_out[i]);
    std::printf("Curve vendor/reference raw count=%zu mismatches=%llu\n",n,(unsigned long long)c_errors);
    if (b_errors || c_errors) return 1;
    std::puts("FULL_FIXED_POINT_VENDOR_GOLDEN_PASS");
    return 0;
}
