#include "elementwise_top.hpp"
#ifndef GDN_NATIVE_HOST
#include <ap_int.h>
using wide_t=ap_int<48>;
#else
using wide_t=std::int64_t;
#endif

namespace {
constexpr int BLOCK=256, MAX_CHANNELS=128;
wide_t rescale(wide_t value, int shift) {
    if(shift==0) return value;
    // F in [3,14]: feature upscaling is at most 11 bits. A signed INT16
    // coefficient product is at most 2^30 and its shift is in [3,25].
    // Every intermediate, including addition and rounding, fits signed 48 bits.
    const bool negative=value<0;
    const wide_t magnitude=negative?wide_t(-value):value;
    if(shift<0) {
        // Shift the nonnegative magnitude: no signed-negative shift in native
        // C++, and no general variable multiplier for a power-of-two scale.
        const wide_t scaled=magnitude<<(-shift);
        return negative?wide_t(-scaled):scaled;
    }
    const wide_t rounded=(magnitude+(wide_t(1)<<(shift-1)))>>shift;
    return negative?wide_t(-rounded):rounded;
}
std::int16_t saturate(wide_t value) {
    return value < -32768 ? -32768 : value > 32767 ? 32767 : static_cast<std::int16_t>(value);
}
}

extern "C" int griddehaze_elementwise_top(
    const std::int16_t* a, const std::int16_t* b,
    const std::int16_t* coefficients, std::int16_t* output,
    std::uint32_t a_length, std::uint32_t b_length,
    std::uint32_t coefficient_length, std::uint32_t output_length,
    int op, int channels_a, int channels_b, int channels_out,
    int height, int width, int frac_a, int frac_b, int frac_out) {
#ifndef GDN_FRAME_INTEGRATION
#pragma HLS INTERFACE m_axi port=a bundle=read_mem depth=117964800 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=b bundle=read_mem depth=117964800 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=coefficients bundle=read_mem depth=128 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=output bundle=write_mem depth=117964800 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS INTERFACE s_axilite port=a bundle=control
#pragma HLS INTERFACE s_axilite port=b bundle=control
#pragma HLS INTERFACE s_axilite port=coefficients bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=a_length bundle=control
#pragma HLS INTERFACE s_axilite port=b_length bundle=control
#pragma HLS INTERFACE s_axilite port=coefficient_length bundle=control
#pragma HLS INTERFACE s_axilite port=output_length bundle=control
#pragma HLS INTERFACE s_axilite port=op bundle=control
#pragma HLS INTERFACE s_axilite port=channels_a bundle=control
#pragma HLS INTERFACE s_axilite port=channels_b bundle=control
#pragma HLS INTERFACE s_axilite port=channels_out bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=frac_a bundle=control
#pragma HLS INTERFACE s_axilite port=frac_b bundle=control
#pragma HLS INTERFACE s_axilite port=frac_out bundle=control
#endif
#pragma HLS INLINE off
    // Shape, scale and logical lengths are checked before any memory access.
    // Physical address windows, pointer overlap and DMA ownership belong to the
    // future image wrapper; this is not a public Linux DMA endpoint.
    if(op<GDN_RELU || op>GDN_CAT || channels_a<1 || channels_a>MAX_CHANNELS ||
       channels_out<1 || channels_out>MAX_CHANNELS || channels_b<0 || channels_b>MAX_CHANNELS ||
       height<1 || height>720 || width<1 || width>1280 ||
       frac_a<3 || frac_a>14 || frac_out<3 || frac_out>14) return 1;
    const bool binary=op==GDN_ADD || op==GDN_CAT;
    if(binary) {
        if(channels_b<1 || frac_b<3 || frac_b>14) return 1;
        if(op==GDN_ADD && (channels_a!=channels_out || channels_b!=channels_out)) return 1;
        if(op==GDN_CAT && channels_a+channels_b!=channels_out) return 1;
    } else if(channels_a!=channels_out || channels_b!=0) return 1;
    const int plane=height*width;
    if(a_length<static_cast<std::uint32_t>(channels_a*plane) ||
       output_length<static_cast<std::uint32_t>(channels_out*plane) ||
       (binary && b_length<static_cast<std::uint32_t>(channels_b*plane)) ||
       (op==GDN_MULCOEF && coefficient_length<static_cast<std::uint32_t>(channels_out))) return 2;
    std::int16_t coefficient_cache[MAX_CHANNELS];
    std::int16_t a_cache[BLOCK],b_cache[BLOCK],result_cache[BLOCK];
#pragma HLS BIND_STORAGE variable=a_cache type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=b_cache type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=result_cache type=ram_2p impl=bram
    if(op==GDN_MULCOEF) for(int c=0;c<channels_out;++c) {
#pragma HLS PIPELINE II=1
        coefficient_cache[c]=coefficients[c];
    }
    for(int c=0;c<channels_out;++c) for(int base=0;base<plane;base+=BLOCK) {
        const int count=plane-base<BLOCK?plane-base:BLOCK;
        const bool second=op==GDN_CAT && c>=channels_a;
        const int source_channel=second?c-channels_a:c;
        for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
            const int index=source_channel*plane+base+i;
            a_cache[i]=second?b[index]:a[index];
        }
        if(op==GDN_ADD) for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
            b_cache[i]=b[c*plane+base+i];
        }
        const std::int16_t coefficient=op==GDN_MULCOEF?coefficient_cache[c]:std::int16_t(0);
        for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
            wide_t value;
            if(op==GDN_MULCOEF) {
                const std::int32_t product=std::int32_t(a_cache[i])*coefficient;
                value=rescale(wide_t(product),frac_a+14-frac_out);
            } else if(op==GDN_ADD) {
                // Do not saturate either aligned operand before addition.
                value=rescale(wide_t(a_cache[i]),frac_a-frac_out)+rescale(wide_t(b_cache[i]),frac_b-frac_out);
            } else {
                value=rescale(wide_t(a_cache[i]),(second?frac_b:frac_a)-frac_out);
                if(op==GDN_RELU && value<0) value=0;
            }
            result_cache[i]=saturate(value);
        }
        for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
            output[c*plane+base+i]=result_cache[i];
        }
    }
    return 0;
}
