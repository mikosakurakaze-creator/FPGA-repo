#pragma once
#include <cstdint>

// Internal operator IP, not the final image/driver ABI. All lengths count INT16
// scalars. NCHW tensors must be disjoint and owned by the caller until completion.
enum GdnElementOp { GDN_RELU=1, GDN_MULCOEF=2, GDN_ADD=3, GDN_CAT=4 };
extern "C" int griddehaze_elementwise_top(
    const std::int16_t* a, const std::int16_t* b,
    const std::int16_t* coefficients, std::int16_t* output,
    std::uint32_t a_length, std::uint32_t b_length,
    std::uint32_t coefficient_length, std::uint32_t output_length,
    int op, int channels_a, int channels_b, int channels_out,
    int height, int width, int frac_a, int frac_b, int frac_out);
