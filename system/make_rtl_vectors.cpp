#include "weather_kernel.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void dump(const std::string& path, const std::vector<int16_t>& data) {
    std::ofstream f(path.c_str());
    if (!f) throw std::runtime_error("fixture open");
    for (int16_t v : data)
        f << std::hex << std::setfill('0') << std::setw(4) << uint16_t(v) << '\n';
    if (!f) throw std::runtime_error("fixture write");
}
static void frame_reference(int mode,const std::vector<int16_t>& input,std::vector<int16_t>& output,int h,int w) {
    for(int y=0;y<h;y+=128)for(int x=0;x<w;x+=128) {
        const int y0=std::max(0,y-6),x0=std::max(0,x-6),y1=std::min(h,y+128),x1=std::min(w,x+128);
        const int ye=std::min(h,y1+6),xe=std::min(w,x1+6),th=ye-y0,tw=xe-x0;
        std::vector<int16_t> ti(3*th*tw),to(3*th*tw),scratch(24*th*tw);
        for(int c=0;c<3;++c)for(int iy=0;iy<th;++iy)for(int ix=0;ix<tw;++ix)
            ti[(c*th+iy)*tw+ix]=input[(c*h+y0+iy)*w+x0+ix];
        int rc=mode ? dehaze_top(ti.data(),to.data(),scratch.data(),th,tw) : derain_top(ti.data(),to.data(),scratch.data(),th,tw);
        if(rc)throw std::runtime_error("A tiled reference return");
        for(int c=0;c<3;++c)for(int iy=y;iy<y1;++iy)for(int ix=x;ix<x1;++ix)
            output[(c*h+iy)*w+ix]=to[(c*th+iy-y0)*tw+ix-x0];
    }
}
int main(int argc,char** argv) {
    // Same physical RTL instance, no reset between calls. Odd lengths and row
    // starts exercise byte lanes; the last two cases cross both tile seams.
    const int cases[][3] = {{0,8,8},{1,8,8},{0,8,8},
        {0,131,1},{1,1,133},{0,131,133},{1,131,133},{0,720,1280},{1,720,1280}};
    const int count=argc==2 && std::string(argv[1])=="--full-frame" ? 9 : 7;
    for (int t=0;t<count;++t) {
        const int mode=cases[t][0],h=cases[t][1],w=cases[t][2];
        const size_t n=size_t(3)*h*w;
        std::vector<int16_t> input(n),output(n),scratch(size_t(24)*h*w);
        for (size_t i=0;i<n;++i)
            input[i]=int16_t((i*197U+size_t(mode)*379U+size_t(h)*11U)%16385U);
        int rc=0;
        if(t>=7)frame_reference(mode,input,output,h,w);
        else rc=mode ? dehaze_top(input.data(),output.data(),scratch.data(),h,w)
                     : derain_top(input.data(),output.data(),scratch.data(),h,w);
        if(rc)throw std::runtime_error("A reference return");
        dump("input_"+std::to_string(t)+".hex",input);
        dump("golden_"+std::to_string(t)+".hex",output);
    }
    std::cout << "WEATHER_RTL_VECTORS_PASS cases=" << count << "\n";
}
