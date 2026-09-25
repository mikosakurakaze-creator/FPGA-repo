#ifndef ZERO_DCE_NATIVE_AP_INT_SHIM_H
#define ZERO_DCE_NATIVE_AP_INT_SHIM_H

// Native C++ numerical check only. Vitis HLS must use its own ap_int.h.
#include <cstdint>

template <int Width> struct zero_dce_native_int;
template <> struct zero_dce_native_int<8> { typedef std::int8_t type; };
template <> struct zero_dce_native_int<16> { typedef std::int16_t type; };
template <> struct zero_dce_native_int<32> { typedef std::int32_t type; };
template <int Width>
using ap_int = typename zero_dce_native_int<Width>::type;

#endif
