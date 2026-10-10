#ifndef BILINEAR_FP32_HPP
#define BILINEAR_FP32_HPP

// NCHW, batch 1, three channels, scale factor 12.
void bilinear_fp32(const float* parameters_lowres, float* parameters_fullres,
                   unsigned int input_height, unsigned int input_width);

#endif
