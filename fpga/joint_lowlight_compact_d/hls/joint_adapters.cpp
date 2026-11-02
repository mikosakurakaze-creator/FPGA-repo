#include "joint_adapters.hpp"
#include <hls_stream.h>

static int16_t original_raw(uint8_t p) {
#pragma HLS INLINE
    return static_cast<int16_t>((static_cast<uint32_t>(p) * 16384u + 127u) / 255u);
}

static int16_t d_raw(uint8_t p) {
#pragma HLS INLINE
    const int32_t numerator = (2 * static_cast<int32_t>(p) - 255) * 16384;
    const uint32_t magnitude = numerator < 0 ? -numerator : numerator;
    const int32_t rounded = (magnitude + 127u) / 255u;
    return static_cast<int16_t>(numerator < 0 ? -rounded : rounded);
}

static void read_rgb(const joint_word* rgb, hls::stream<joint_word>& pixels) {
#pragma HLS INLINE off
read_frame:
    for (int i = 0; i < JOINT_COUNT / 16; ++i) {
#pragma HLS PIPELINE II=1
        pixels.write(rgb[i]);
    }
}

static void convert_tiles(hls::stream<joint_word>& pixels,
                          hls::stream<joint_word>& original,
                          hls::stream<joint_word>& normalized,
                          hls::stream<joint_word>& small) {
#pragma HLS INLINE off
    joint_word original_tile[3][JOINT_TILE_WORDS];
    joint_word d_tile[3][JOINT_TILE_WORDS];
#pragma HLS ARRAY_PARTITION variable=original_tile complete dim=1
#pragma HLS ARRAY_PARTITION variable=d_tile complete dim=1
#pragma HLS BIND_STORAGE variable=original_tile type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=d_tile type=ram_2p impl=lutram
    // Only the horizontal pair from the first selected row is retained.
    // The second selected row completes the exact frozen 2x2 Q14 average.
    ap_uint<16> previous_pair[3][JOINT_LOW_W];
    ap_uint<15> left[3];
    joint_word small_image[3][JOINT_LOW_PLANE / 8];
    joint_word original_pack[3] = {}, d_pack[3] = {}, small_pack[3] = {};
#pragma HLS ARRAY_PARTITION variable=previous_pair complete dim=1
#pragma HLS ARRAY_PARTITION variable=left complete
#pragma HLS ARRAY_PARTITION variable=small_image complete dim=1
#pragma HLS ARRAY_PARTITION variable=original_pack complete
#pragma HLS ARRAY_PARTITION variable=d_pack complete
#pragma HLS ARRAY_PARTITION variable=small_pack complete
#pragma HLS BIND_STORAGE variable=previous_pair type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=small_image type=ram_2p impl=bram
    int x = 0, x12 = 0, y12 = 0, low_x = 0, small_index = 0;
tiles:
    for (int tile = 0; tile < JOINT_TILES; ++tile) {
groups:
        for (int group = 0; group < JOINT_TILE_PIXELS / 16; ++group) {
            // Three consecutive 128-bit words contain exactly sixteen RGB
            // pixels. A fixed shift exposes one complete pixel each cycle.
            ap_uint<384> packed = 0;
load_group:
            for (int w = 0; w < 3; ++w) {
#pragma HLS PIPELINE II=1
                packed.range(128*w+127, 128*w) = pixels.read();
            }
pixels_in_group:
            for (int k = 0; k < 16; ++k) {
#pragma HLS PIPELINE II=1
channels:
                for (int c = 0; c < 3; ++c) {
#pragma HLS UNROLL
                    const uint8_t p = packed.range(8*c+7, 8*c).to_uint();
                    const int16_t iq = original_raw(p);
                    const int16_t dq = d_raw(p);
                    original_pack[c] >>= 16;
                    d_pack[c] >>= 16;
                    original_pack[c].range(127,112) = static_cast<uint16_t>(iq);
                    d_pack[c].range(127,112) = static_cast<uint16_t>(dq);
                    if ((k & 7) == 7) {
                        original_tile[c][2*group+(k>>3)] = original_pack[c];
                        d_tile[c][2*group+(k>>3)] = d_pack[c];
                    }
                    if ((y12 == 5 || y12 == 6) && x12 == 5) left[c] = iq;
                    if ((y12 == 5 || y12 == 6) && x12 == 6) {
                        const ap_uint<16> pair = left[c] + ap_uint<16>(iq);
                        if (y12 == 5) previous_pair[c][low_x] = pair;
                        else {
                            const ap_uint<17> sum = ap_uint<17>(previous_pair[c][low_x]) + pair;
                            const unsigned q = sum.to_uint() >> 2;
                            const unsigned rem = sum.to_uint() & 3u;
                            const uint16_t value = q + (rem > 2u || (rem == 2u && (q & 1u)));
                            small_pack[c] >>= 16;
                            small_pack[c].range(127,112) = value;
                            if ((small_index & 7) == 7)
                                small_image[c][small_index >> 3] = small_pack[c];
                        }
                    }
                }
                if (y12 == 6 && x12 == 6) ++small_index;
                if (x == JOINT_W-1) {
                    x = 0; x12 = 0; low_x = 0;
                    y12 = y12 == 11 ? 0 : y12+1;
                } else {
                    ++x;
                    if (x12 == 11) {x12 = 0; ++low_x;} else ++x12;
                }
                packed >>= 24;
            }
        }
emit_channels:
        for (int c = 0; c < 3; ++c) {
emit_tile:
            for (int w = 0; w < JOINT_TILE_WORDS; ++w) {
#pragma HLS PIPELINE II=1
                original.write(original_tile[c][w]);
                normalized.write(d_tile[c][w]);
            }
        }
    }
emit_small_channels:
    for (int c = 0; c < 3; ++c) {
emit_small:
        for (int w = 0; w < JOINT_LOW_PLANE / 8; ++w) {
#pragma HLS PIPELINE II=1
            small.write(small_image[c][w]);
        }
    }
}

template<int Port>
static void write_full(hls::stream<joint_word>& data, joint_word* output) {
#pragma HLS INLINE off
write_tiles:
    for (int tile = 0; tile < JOINT_TILES; ++tile) {
write_planes:
        for (int c = 0; c < 3; ++c) {
write_burst:
            for (int w = 0; w < JOINT_TILE_WORDS; ++w) {
#pragma HLS PIPELINE II=1
                output[c*(JOINT_PLANE/8)+tile*JOINT_TILE_WORDS+w] = data.read();
            }
        }
    }
}

static void write_small(hls::stream<joint_word>& data, joint_word* output) {
#pragma HLS INLINE off
write_small_frame:
    for (int w = 0; w < JOINT_LOW_COUNT / 8; ++w) {
#pragma HLS PIPELINE II=1
        output[w] = data.read();
    }
}

static void prepare_frame(const joint_word* rgb, joint_word* original_q14,
                          joint_word* d_input_q14, joint_word* cnn_input_q14) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<joint_word> pixels("pixels"), original("original"), normalized("normalized"), small("small");
#pragma HLS STREAM variable=pixels depth=256
#pragma HLS STREAM variable=original depth=128
#pragma HLS STREAM variable=normalized depth=128
#pragma HLS STREAM variable=small depth=64
#pragma HLS BIND_STORAGE variable=pixels type=fifo impl=bram
#pragma HLS BIND_STORAGE variable=original type=fifo impl=bram
#pragma HLS BIND_STORAGE variable=normalized type=fifo impl=bram
#pragma HLS BIND_STORAGE variable=small type=fifo impl=bram
    read_rgb(rgb, pixels);
    convert_tiles(pixels, original, normalized, small);
    write_full<0>(original, original_q14);
    write_full<1>(normalized, d_input_q14);
    write_small(small, cnn_input_q14);
}

extern "C" int joint_rgb8_prepare(const joint_word* rgb, joint_word* original_q14,
                                  joint_word* d_input_q14, joint_word* cnn_input_q14,
                                  uint32_t abi_cookie) {
#pragma HLS INTERFACE m_axi port=rgb offset=slave bundle=gmem_rgb depth=171720 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE m_axi port=original_q14 offset=slave bundle=gmem_i depth=343440 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE m_axi port=d_input_q14 offset=slave bundle=gmem_d depth=343440 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE m_axi port=cnn_input_q14 offset=slave bundle=gmem_cnn depth=2385 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE s_axilite port=return bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=rgb bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=original_q14 bundle=control offset=0x24
#pragma HLS INTERFACE s_axilite port=d_input_q14 bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=cnn_input_q14 bundle=control offset=0x3c
#pragma HLS INTERFACE s_axilite port=abi_cookie bundle=control offset=0x48
    static_assert(JOINT_PLANE % JOINT_TILE_PIXELS == 0, "Complete tiles required");
    static_assert(JOINT_LOW_PLANE % 8 == 0, "Complete small-image words required");
    if (abi_cookie != JOINT_PREPARE_COOKIE) return -1;
    prepare_frame(rgb, original_q14, d_input_q14, cnn_input_q14);
    return 0;
}
