#pragma once
#include <cstdint>
// A single output tile, not the full network ABI. Native OIHW / IOHW weights.
extern "C" int griddehaze_conv_tile_top(
    const std::int16_t* feature, const std::int16_t* weights,
    const std::int64_t* bias, const std::int8_t* shifts, std::int16_t* output,
    int cin,int cout,int ih,int iw,int oh,int ow,int kernel,int stride,int padding,
    int transpose,int oy0,int ox0,int co0);
