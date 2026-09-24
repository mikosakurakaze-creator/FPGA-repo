#ifndef BILINEAR_FP32_BUFFERED_HPP
#define BILINEAR_FP32_BUFFERED_HPP

// V1: NCHW, batch 1, three channels, scale factor 12, input width <= 128.
void bilinear_fp32_buffered(const float* parameters_lowres,
                            float* parameters_fullres,
                            unsigned int input_height, unsigned int input_width);

#endif
