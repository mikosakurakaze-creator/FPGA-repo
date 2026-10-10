#pragma once
#include <ap_int.h>
#include <hls_stream.h>
#ifndef __SYNTHESIS__
#include <thread>
#endif

// External objects stay signed INT16. Word packing is only on chip; no cast
// changes the seven-pointer CNN ABI or little-endian DDR representation.
namespace rowstream_io {
typedef ap_int<16> row_q16;
typedef ap_uint<32> row_word;
static const int kRowScalars=106, kRowWords=53;
template<typename T> static T take(hls::stream<T> &values) {
#pragma HLS INLINE
#ifndef __SYNTHESIS__
    while(values.empty()) std::this_thread::yield();
#endif
    return values.read();
}

static void row_axi_reader(const row_q16 *source,int scalar_base,
                           hls::stream<row_q16> &values) {
#pragma HLS INLINE off
    for(int scalar=0;scalar<kRowScalars;++scalar) {
#pragma HLS PIPELINE II=1
        values.write(source[scalar_base+scalar]);
    }
}

static void row_unpack(hls::stream<row_q16> &values,row_word *bulk,
                       int word_base) {
#pragma HLS INLINE off
    row_word word=0;
    for(int scalar=0;scalar<kRowScalars;++scalar) {
#pragma HLS PIPELINE II=1
        const row_q16 value=take(values);
        if((scalar&1)==0) word.range(15,0)=value.range(15,0);
        else {
            word.range(31,16)=value.range(15,0);
            bulk[word_base+scalar/2]=word;
        }
    }
}

static void row_unpack_words(hls::stream<row_q16> &values,
                             hls::stream<row_word> &words) {
#pragma HLS INLINE off
    row_word word=0;
    for(int scalar=0;scalar<kRowScalars;++scalar) {
#pragma HLS PIPELINE II=1
        const row_q16 value=take(values);
        if((scalar&1)==0) word.range(15,0)=value.range(15,0);
        else {
            word.range(31,16)=value.range(15,0);
            words.write(word);
        }
    }
}

static void row_pack(const row_word *bulk,int word_base,
                     hls::stream<row_q16> &values) {
#pragma HLS INLINE off
    row_word word=0;
    for(int scalar=0;scalar<kRowScalars;++scalar) {
#pragma HLS PIPELINE II=1
        if((scalar&1)==0) word=bulk[word_base+scalar/2];
        row_q16 value;
        value.range(15,0)=(scalar&1)?word.range(31,16):word.range(15,0);
        values.write(value);
    }
}

static void row_axi_writer(row_q16 *destination,int scalar_base,
                           hls::stream<row_q16> &values) {
#pragma HLS INLINE off
    for(int scalar=0;scalar<kRowScalars;++scalar) {
#pragma HLS PIPELINE II=1
        destination[scalar_base+scalar]=take(values);
    }
}
} // namespace rowstream_io
