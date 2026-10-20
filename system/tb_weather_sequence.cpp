#include "weather_frame.h"
#include "weather_kernel.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <vector>

static void run(int task, int h, int w) {
    const size_t n=size_t(3)*h*w, depth=size_t(3)*720*1280;
    // Keep DMA ranges stable for the whole sequence, as in the standalone app.
    // Vendor AXI VIP accumulates address-region state across transactions.
    static std::vector<int16_t> input(depth),output(depth);
    std::fill(input.begin(),input.end(),int16_t(0x1357));
    std::fill(output.begin(),output.end(),int16_t(0x2468));
    std::vector<int16_t> expected(n),scratch(size_t(24)*h*w);
    for(size_t i=0;i<n;++i)
        input[i]=int16_t((i*197U+size_t(task)*379U+size_t(h)*11U)%16385U);
    const std::vector<int16_t> before=input;
    int ref=task ? dehaze_top(input.data(),expected.data(),scratch.data(),h,w)
                 : derain_top(input.data(),expected.data(),scratch.data(),h,w);
    if(ref || weather_frame_top(input.data(),output.data(),h,w,task))
        throw std::runtime_error("core return");
    if(!std::equal(expected.begin(),expected.end(),output.begin()) || input!=before)
        throw std::runtime_error("sequence numerical/input mismatch");
    for(size_t i=n;i<depth;++i)
        if(output[i]!=0x2468)throw std::runtime_error("sequence guard mismatch");
    std::cout<<"WEATHER_SEQUENCE_FRAME_PASS task="<<task<<" shape="<<h<<"x"<<w<<"\n";
}
int main() {
    try {
        run(0,8,8); run(1,8,8); run(0,8,8);
        // Cross vertical/horizontal 128-pixel boundaries independently. Direct
        // A reference accepts both full tensors and independently checks seams.
        // Thin frames bound the memory demand of the vendor UVM simulator.
        run(0,131,1); run(1,1,133);
        std::cout<<"WEATHER_SEQUENCE_PASS frames=5 tasks=0,1,0,0,1\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<"\n";return 1;}
}
