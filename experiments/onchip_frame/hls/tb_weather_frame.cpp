#include "weather_frame.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static std::vector<int16_t> read_tensor(const char* path,size_t n) {
    std::ifstream f(path,std::ios::binary);
    if(!f)throw std::runtime_error("input open");
    std::vector<int16_t> x(n);
    for(size_t i=0;i<n;++i) {
        unsigned char b[2];
        if(!f.read(reinterpret_cast<char*>(b),2))throw std::runtime_error("short input");
        uint16_t v=uint16_t(b[0])|(uint16_t(b[1])<<8);
        x[i]=v<32768U?int16_t(v):int16_t(int32_t(v)-65536);
    }
    char extra;if(f.get(extra))throw std::runtime_error("long input");return x;
}
int main(int argc,char** argv) {
    try {
        if(argc!=7)throw std::runtime_error("usage: TASK H W INPUT EXPECTED ACTUAL");
        int task=std::stoi(argv[1]),h=std::stoi(argv[2]),w=std::stoi(argv[3]);
        if(task<0 || task>1 || h<1 || h>720 || w<1 || w>1280)throw std::runtime_error("dimensions/task");
        size_t n=size_t(3)*h*w;
        auto x=read_tensor(argv[4],n),expected=read_tensor(argv[5],n);
        // The vendor wrap-C adapter copies the full declared m_axi depth,
        // even when the job uses an 8x8 or 96x96 active tensor.
        const size_t depth=size_t(3)*720*1280;
        x.resize(depth, int16_t(0x1357));
        std::vector<int16_t> out(depth, int16_t(0x2468));
        if(weather_frame_top(x.data(),out.data(),h,w,task))throw std::runtime_error("core status");
        std::ofstream f(argv[6],std::ios::binary);
        for(size_t i=0;i<n;++i) {
            uint16_t v=uint16_t(out[i]);
            unsigned char b[]={static_cast<unsigned char>(v),static_cast<unsigned char>(v>>8)};
            f.write(reinterpret_cast<const char*>(b),2);
        }
        if(!f)throw std::runtime_error("actual output write");
        if(!std::equal(expected.begin(),expected.end(),out.begin()))throw std::runtime_error("Golden mismatch");
        for(size_t i=n;i<depth;++i)
            if(out[i]!=int16_t(0x2468))throw std::runtime_error("output guard mismatch");
        std::cout<<"WEATHER_FRAME_GOLDEN_PASS task="<<task<<" shape="<<h<<"x"<<w<<"\n";return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<"\n";return 1;}
}
