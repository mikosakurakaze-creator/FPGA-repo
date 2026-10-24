#include "conv_tile_top.hpp"
#ifndef GDN_NATIVE_HOST
#include <ap_int.h>
using accum_t=ap_int<48>;
#else
using accum_t=std::int64_t;
#endif

namespace {
constexpr int LANES=8, TILE=16, MAX_CIN=128, CACHE=128*18*18;
int floor_div(int value,int divisor) { return divisor==1?value:(value>=0?value/2:-((-value+1)/2)); }
int scale(int value,int stride) { return stride==2?value*2:value; }
std::int16_t requantize(accum_t value,int shift) {
    // Validated package shifts are [13,20]; 48-bit arithmetic bound was proved.
    const bool negative=value<0;
    const accum_t magnitude=negative ? accum_t(-value) : value;
    const accum_t rounded=(magnitude+(accum_t(1)<<(shift-1)))>>shift;
    const accum_t result=negative ? accum_t(-rounded) : rounded;
    return result < -32768 ? -32768 : result > 32767 ? 32767 : static_cast<std::int16_t>(result);
}
}

extern "C" int griddehaze_conv_tile_top(
    const std::int16_t* feature, const std::int16_t* weights,
    const std::int64_t* bias, const std::int8_t* shifts, std::int16_t* output,
    int cin,int cout,int ih,int iw,int oh,int ow,int kernel,int stride,int padding,
    int transpose,int oy0,int ox0,int co0) {
#ifndef GDN_FRAME_INTEGRATION
#pragma HLS INTERFACE m_axi port=feature bundle=read_mem depth=117964800 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=weights bundle=read_mem depth=958723 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=bias bundle=read_mem depth=64 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=shifts bundle=read_mem depth=64 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=output bundle=write_mem depth=117964800 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS INTERFACE s_axilite port=feature bundle=control
#pragma HLS INTERFACE s_axilite port=weights bundle=control
#pragma HLS INTERFACE s_axilite port=bias bundle=control
#pragma HLS INTERFACE s_axilite port=shifts bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=cin bundle=control
#pragma HLS INTERFACE s_axilite port=cout bundle=control
#pragma HLS INTERFACE s_axilite port=ih bundle=control
#pragma HLS INTERFACE s_axilite port=iw bundle=control
#pragma HLS INTERFACE s_axilite port=oh bundle=control
#pragma HLS INTERFACE s_axilite port=ow bundle=control
#pragma HLS INTERFACE s_axilite port=kernel bundle=control
#pragma HLS INTERFACE s_axilite port=stride bundle=control
#pragma HLS INTERFACE s_axilite port=padding bundle=control
#pragma HLS INTERFACE s_axilite port=transpose bundle=control
#pragma HLS INTERFACE s_axilite port=oy0 bundle=control
#pragma HLS INTERFACE s_axilite port=ox0 bundle=control
#pragma HLS INTERFACE s_axilite port=co0 bundle=control
#endif
#pragma HLS INLINE off
    // Invalid shape descriptors are rejected before any DMA transaction.
    if(cin<1 || cin>MAX_CIN || cout<1 || cout>64 || ih<1 || ih>720 || iw<1 || iw>1280 ||
       oh<1 || oh>720 || ow<1 || ow>1280 || (kernel!=1 && kernel!=3) ||
       (stride!=1 && stride!=2) || padding<0 || padding>1 ||
       (transpose!=0 && transpose!=1) || oy0<0 || oy0>=oh || ox0<0 || ox0>=ow || co0<0 || co0>=cout) return 1;
    const int minimum_h=transpose ? scale(ih-1,stride)-2*padding+kernel : floor_div(ih+2*padding-kernel,stride)+1;
    const int minimum_w=transpose ? scale(iw-1,stride)-2*padding+kernel : floor_div(iw+2*padding-kernel,stride)+1;
    if(transpose ? (oh<minimum_h || oh>=minimum_h+stride || ow<minimum_w || ow>=minimum_w+stride) :
                   (oh!=minimum_h || ow!=minimum_w)) return 1;
    const int th=oh-oy0<TILE?oh-oy0:TILE,tw=ow-ox0<TILE?ow-ox0:TILE;
    const int nc=cout-co0<LANES?cout-co0:LANES;
    const int ybase=transpose?floor_div(oy0+padding-kernel+1,stride):scale(oy0,stride)-padding;
    const int xbase=transpose?floor_div(ox0+padding-kernel+1,stride):scale(ox0,stride)-padding;
    const int ch=transpose?floor_div(oy0+th-1+padding,stride)-ybase+1:scale(th-1,stride)+kernel;
    const int cw=transpose?floor_div(ox0+tw-1+padding,stride)-xbase+1:scale(tw-1,stride)+kernel;
    if(cin*ch*cw>CACHE) return 2;
    std::int16_t input_cache[CACHE];
    std::int16_t weight_cache[LANES][MAX_CIN*9];
    accum_t initial[LANES]; std::int8_t shift_cache[LANES];
    std::int16_t result_cache[LANES][TILE*TILE];
#pragma HLS BIND_STORAGE variable=input_cache type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=weight_cache complete dim=1
#pragma HLS ARRAY_PARTITION variable=result_cache complete dim=1
#pragma HLS ARRAY_PARTITION variable=initial complete
#pragma HLS ARRAY_PARTITION variable=shift_cache complete
    // Load contiguous rows once per tile. No DDR access in the MAC loop below.
    for(int ci=0;ci<cin;++ci) for(int y=0;y<ch;++y) for(int x=0;x<cw;++x) {
#pragma HLS PIPELINE II=1
        const int iy=ybase+y,ix=xbase+x;
        input_cache[(ci*ch+y)*cw+x]=(iy>=0 && iy<ih && ix>=0 && ix<iw)?feature[(ci*ih+iy)*iw+ix]:0;
    }
    for(int lane=0;lane<nc;++lane) {
        const int o=co0+lane;
        // Host package audit proves bias and every partial sum fit signed 40 bits.
        // Hardware uses 48, including the RHAZ temporary; no source truncation.
        initial[lane]=bias[o]; shift_cache[lane]=shifts[o];
        if(shift_cache[lane]<13 || shift_cache[lane]>20) return 3;
        for(int ci=0;ci<cin;++ci) for(int ky=0;ky<kernel;++ky) for(int kx=0;kx<kernel;++kx) {
#pragma HLS PIPELINE II=1
            const int wi=transpose?((ci*cout+o)*kernel+ky)*kernel+kx:((o*cin+ci)*kernel+ky)*kernel+kx;
            weight_cache[lane][(ci*kernel+ky)*kernel+kx]=weights[wi];
        }
    }
    for(int y=0;y<th;++y) for(int x=0;x<tw;++x) {
        accum_t acc[LANES];
#pragma HLS ARRAY_PARTITION variable=acc complete
        for(int lane=0;lane<LANES;++lane) {
#pragma HLS UNROLL
            acc[lane]=lane<nc?initial[lane]:accum_t(0);
        }
        for(int ci=0;ci<cin;++ci) for(int ky=0;ky<kernel;++ky) for(int kx=0;kx<kernel;++kx) {
#pragma HLS PIPELINE II=1
            int iy=transpose ? oy0+y+padding-ky : scale(oy0+y,stride)-padding+ky;
            int ix=transpose ? ox0+x+padding-kx : scale(ox0+x,stride)-padding+kx;
            const bool valid=!transpose || stride==1 || (iy%2==0 && ix%2==0);
            if(transpose) { iy=floor_div(iy,stride); ix=floor_div(ix,stride); }
            const auto sample=valid?input_cache[(ci*ch+iy-ybase)*cw+ix-xbase]:std::int16_t(0);
            for(int lane=0;lane<LANES;++lane) {
#pragma HLS UNROLL
                if(lane<nc) {
                    const std::int32_t product=std::int32_t(sample)*weight_cache[lane][(ci*kernel+ky)*kernel+kx];
                    acc[lane]+=product;
                }
            }
        }
        for(int lane=0;lane<LANES;++lane) {
#pragma HLS UNROLL
            if(lane<nc) result_cache[lane][y*TILE+x]=requantize(acc[lane],shift_cache[lane]);
        }
    }
    for(int lane=0;lane<nc;++lane) for(int y=0;y<th;++y) for(int x=0;x<tw;++x) {
#pragma HLS PIPELINE II=1
        output[((co0+lane)*oh+oy0+y)*ow+ox0+x]=result_cache[lane][y*TILE+x];
    }
    return 0;
}
