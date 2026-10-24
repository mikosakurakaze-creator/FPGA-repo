#include "conv_tile_top.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
template<class T> std::vector<T> read(const std::string& name,std::size_t count) {
    std::vector<T> data(count); std::ifstream f(name,std::ios::binary);
    f.read(reinterpret_cast<char*>(data.data()),count*sizeof(T));
    if(!f || f.peek()!=std::char_traits<char>::eof()) throw std::runtime_error("fixture size "+name);
    return data;
}
int main(int argc,char**argv) try {
    if(argc!=2) throw std::runtime_error("provide cases.txt");
    std::ifstream cases(argv[1]); int count; cases>>count;
    for(int case_index=0;case_index<count;++case_index) {
        std::string prefix; int ci,co,ih,iw,oh,ow,k,s,p,tr;
        cases>>prefix>>ci>>co>>ih>>iw>>oh>>ow>>k>>s>>p>>tr;
        if(!cases) throw std::runtime_error("case metadata");
        auto input=read<std::int16_t>(prefix+"_input.raw",ci*ih*iw);
        const auto copy=input;
        const auto weights=read<std::int16_t>(prefix+"_weights.raw",ci*co*k*k);
        const auto bias=read<std::int64_t>(prefix+"_bias.raw",co);
        const auto shifts=read<std::int8_t>(prefix+"_shifts.raw",co);
        const auto expected=read<std::int16_t>(prefix+"_expected.raw",co*oh*ow);
        std::vector<std::int16_t> output(co*oh*ow+64,0x5A39);
        for(int c=0;c<co;c+=8) for(int y=0;y<oh;y+=16) for(int x=0;x<ow;x+=16) {
            if(griddehaze_conv_tile_top(input.data(),weights.data(),bias.data(),shifts.data(),output.data()+32,
                ci,co,ih,iw,oh,ow,k,s,p,tr,y,x,c)) throw std::runtime_error("descriptor rejected");
        }
        if(copy!=input || !std::all_of(output.begin(),output.begin()+32,[](std::int16_t v){return v==0x5A39;}) ||
           !std::all_of(output.end()-32,output.end(),[](std::int16_t v){return v==0x5A39;})) throw std::runtime_error("input/guard damaged");
        std::ofstream actual(prefix+"_actual.raw",std::ios::binary);
        actual.write(reinterpret_cast<const char*>(output.data()+32),expected.size()*2);
        if(!actual || !std::equal(expected.begin(),expected.end(),output.begin()+32)) throw std::runtime_error("Golden mismatch");
        std::cout<<"VENDOR_CSIM_OPERATOR_EXACT "<<prefix<<" elements="<<expected.size()<<"\n";
    }
    std::cout<<"ALL_TILE_CASES_PASS count="<<count<<"\n";
    return 0;
} catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; return 1; }
