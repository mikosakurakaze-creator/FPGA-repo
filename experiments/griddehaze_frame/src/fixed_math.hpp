#pragma once
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace gdn {
// RHAZ without abs(INT64_MIN), signed shifts, or bias-addition overflow.
inline std::int64_t round_shift(std::int64_t value, int shift) {
    if (shift < -62 || shift > 62) throw std::invalid_argument("shift range");
    if (shift == 0) return value;
    if (shift < 0) {
        const auto factor = std::int64_t(1) << (-shift);
        if (value < std::numeric_limits<std::int64_t>::min()/factor ||
            value > std::numeric_limits<std::int64_t>::max()/factor)
            throw std::overflow_error("left rescale");
        return value * factor;
    }
    const bool negative = value < 0;
    const std::uint64_t magnitude = negative ? std::uint64_t(-(value+1))+1 : std::uint64_t(value);
    auto q = magnitude >> shift;
    const auto remainder = magnitude & ((std::uint64_t(1) << shift)-1);
    if (remainder >= (std::uint64_t(1) << (shift-1))) ++q;
    return negative ? -static_cast<std::int64_t>(q) : static_cast<std::int64_t>(q);
}
inline std::int16_t sat(std::int64_t x) {
    return static_cast<std::int16_t>(x < -32768 ? -32768 : x > 32767 ? 32767 : x);
}
}
