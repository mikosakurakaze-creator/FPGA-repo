#include "conv_micro.hpp"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <random>
#include <vector>

static int16_t oracle_round(int64_t value, unsigned shift) {
    const int64_t divisor = int64_t(1) << shift;
    int64_t quotient = value / divisor;  // C++ division truncates toward zero.
    const int64_t remainder = value % divisor;
    if (remainder >= divisor / 2) ++quotient;
    if (remainder <= -divisor / 2) --quotient;
    return int16_t(std::max(int64_t(-32768), std::min(int64_t(32767), quotient)));
}

static void oracle(const int16_t *x, const int16_t *w, const int64_t *b,
                   const uint8_t *shift, int16_t *out) {
    for (int co=0; co<D_C; ++co) for (int y=0; y<D_H; ++y) for (int col=0; col<D_W; ++col) {
        int64_t sum=b[co];
        for (int ci=0; ci<D_C; ++ci) for (int ky=0; ky<3; ++ky) for (int kx=0; kx<3; ++kx) {
            const int iy=y+ky-1, ix=col+kx-1;
            if (iy>=0 && iy<D_H && ix>=0 && ix<D_W)
                sum += int64_t(x[(ci*D_H+iy)*D_W+ix])*w[((co*D_C+ci)*3+ky)*3+kx];
        }
        out[(co*D_H+y)*D_W+col] = oracle_round(sum,shift[co]);
    }
}

int main(int argc, char **argv) {
    int16_t input[D_INPUTS], weight[D_WEIGHTS], direct[D_INPUTS], row[D_INPUTS], expected[D_INPUTS];
    int64_t bias[D_C]; uint8_t shift[D_C];
    std::mt19937 random(20261025);
    int cases=0;
    for (int mode=0; mode<12; ++mode) {
        for (auto &v: input) v=mode==0 ? 0 : mode==1 ? -32768 : mode==2 ? 32767 : int16_t(random());
        for (auto &v: weight) v=mode==0 ? 0 : mode==1 ? -32768 : mode==2 ? 32767 : int16_t(random());
        for (int c=0;c<D_C;++c) {
            // modes 0 and 3 stress exact positive/negative ties, and modes 1/2
            // exercise INT16 saturation with certified-safe 64-bit accumulators.
            shift[c]=uint8_t(mode==0 ? 14 : 14+c%4);
            bias[c]=mode==0 ? (c%2 ? -8192 : 8192) : int64_t(int32_t(random()))/4;
        }
        oracle(input,weight,bias,shift,expected);
        d_conv_direct(input,weight,bias,shift,direct);
        d_conv_row_oc8(input,weight,bias,shift,row);
        if (!std::equal(expected,expected+D_INPUTS,direct) || !std::equal(expected,expected+D_INPUTS,row)) {
            std::cerr << "D_MICRO_FAIL synthetic case " << mode << '\n'; return 1;
        }
        ++cases;
    }
    // Optional actual D layer vectors: headerless little-endian arrays in the
    // order input i16, weights OIHW i16, bias i64, shift u8, expected output i16.
    if (argc>1) {
        std::ifstream stream(argv[1], std::ios::binary);
        stream.read(reinterpret_cast<char*>(input),sizeof(input));
        stream.read(reinterpret_cast<char*>(weight),sizeof(weight));
        stream.read(reinterpret_cast<char*>(bias),sizeof(bias));
        stream.read(reinterpret_cast<char*>(shift),sizeof(shift));
        stream.read(reinterpret_cast<char*>(expected),sizeof(expected));
        if (!stream || stream.peek()!=EOF) { std::cerr<<"Bad vector file\n"; return 2; }
        oracle(input,weight,bias,shift,direct);
        if (!std::equal(expected,expected+D_INPUTS,direct)) { std::cerr<<"Vector/oracle mismatch\n"; return 3; }
        d_conv_direct(input,weight,bias,shift,direct);
        d_conv_row_oc8(input,weight,bias,shift,row);
        if (!std::equal(expected,expected+D_INPUTS,direct) || !std::equal(expected,expected+D_INPUTS,row)) {
            std::cerr<<"D_MICRO_FAIL actual vector\n"; return 4;
        }
        ++cases;
    }
    // Host timing is diagnostic only; it is not a predictor of HLS/FPGA speed.
    auto start=std::chrono::steady_clock::now();
    for(int i=0;i<100;++i) d_conv_direct(input,weight,bias,shift,direct);
    auto mid=std::chrono::steady_clock::now();
    for(int i=0;i<100;++i) d_conv_row_oc8(input,weight,bias,shift,row);
    auto end=std::chrono::steady_clock::now();
    std::cout << "{\"status\":\"D_MICRO_EXACT_PASS\",\"cases\":" << cases
        << ",\"outputs_per_case\":"<<D_INPUTS
        << ",\"host_direct_100_us\":"<<std::chrono::duration_cast<std::chrono::microseconds>(mid-start).count()
        << ",\"host_row_oc8_100_us\":"<<std::chrono::duration_cast<std::chrono::microseconds>(end-mid).count()<<"}\n";
}
