#ifndef CURVE_FP32_HPP
#define CURVE_FP32_HPP

// One NCHW tensor element per call. rounds[7] is the final enhanced value.
void curve_fp32(float input, float parameter, float rounds[8]);

#endif
