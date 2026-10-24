#pragma once
#include <cstdint>

// Numerical microbenchmark only: no AXI/driver/system ABI is defined here.
constexpr int D_C = 8;
constexpr int D_H = 8;
constexpr int D_W = 8;
constexpr int D_INPUTS = D_C * D_H * D_W;
constexpr int D_WEIGHTS = D_C * D_C * 9;

void d_conv_direct(const int16_t input[D_INPUTS],
                   const int16_t weight[D_WEIGHTS],
                   const int64_t bias[D_C], const uint8_t shift[D_C],
                   int16_t output[D_INPUTS]);
void d_conv_row_oc8(const int16_t input[D_INPUTS],
                    const int16_t weight[D_WEIGHTS],
                    const int64_t bias[D_C], const uint8_t shift[D_C],
                    int16_t output[D_INPUTS]);
