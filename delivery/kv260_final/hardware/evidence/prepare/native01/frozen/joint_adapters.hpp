#ifndef JOINT_ADAPTERS_HPP
#define JOINT_ADAPTERS_HPP
#include <stdint.h>

enum {
    JOINT_H = 720, JOINT_W = 1272, JOINT_PLANE = JOINT_H * JOINT_W,
    JOINT_COUNT = 3 * JOINT_PLANE, JOINT_LOW_H = 60, JOINT_LOW_W = 106,
    JOINT_LOW_COUNT = 3 * JOINT_LOW_H * JOINT_LOW_W
};
static const uint32_t JOINT_PREPARE_COOKIE = 0x4a503031;
static const uint32_t JOINT_COPY_COOKIE = 0x4a433031;

// Fixed 720x1272 RGB8 HWC -> three independent tensors, no resize/colour transform.
extern "C" int joint_rgb8_prepare(const uint8_t* rgb, int16_t* original_q14,
                                  int16_t* d_input_q14, int16_t* cnn_input_q14,
                                  uint32_t abi_cookie);
// L and D already use RGB/NCHW/signed Q14. Preserve all bits, including >1 values.
extern "C" int joint_q14_copy(const int16_t* source, int16_t* destination,
                              uint32_t abi_cookie);
#endif
