#ifndef JOINT_PREPARE_PIPELINED_HPP
#define JOINT_PREPARE_PIPELINED_HPP
#include <stdint.h>
#include <ap_int.h>

enum {
    JOINT_H = 720, JOINT_W = 1272, JOINT_PLANE = JOINT_H * JOINT_W,
    JOINT_COUNT = 3 * JOINT_PLANE, JOINT_LOW_H = 60, JOINT_LOW_W = 106,
    JOINT_LOW_PLANE = JOINT_LOW_H * JOINT_LOW_W,
    JOINT_LOW_COUNT = 3 * JOINT_LOW_PLANE,
    JOINT_TILE_PIXELS = 384, JOINT_TILES = JOINT_PLANE / JOINT_TILE_PIXELS,
    JOINT_TILE_WORDS = JOINT_TILE_PIXELS / 8
};
static const uint32_t JOINT_PREPARE_COOKIE = 0x4a503031;
typedef ap_uint<128> joint_word;

// Physical DDR buffers and AXI-Lite pointer offsets are unchanged. Each word
// transports sixteen RGB8 bytes or eight little-endian INT16 scalars.
extern "C" int joint_rgb8_prepare(const joint_word* rgb, joint_word* original_q14,
                                  joint_word* d_input_q14, joint_word* cnn_input_q14,
                                  uint32_t abi_cookie);
#endif
