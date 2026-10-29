// Execute the locked HLS C models on the same new RGB8 frame and compare every scalar.
#include "joint_adapters.hpp"
#include "zero_dce_cnn_top.h"
#include "bilinear_fixed16_buffered.hpp"
#include "curve_image_fixed16.hpp"
#include "compact_d.hpp"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static const int N=3*720*1272, LOW=3*60*106;
template<class T> static std::vector<T> read_raw(const std::string& file,int count) {
    std::ifstream f(file.c_str(),std::ios::binary|std::ios::ate);
    if(!f || f.tellg()!=std::streampos(sizeof(T)*size_t(count))) throw std::runtime_error("bad file size: "+file);
    f.seekg(0); std::vector<T> data(count);
    f.read(reinterpret_cast<char*>(data.data()),sizeof(T)*size_t(count));
    if(!f) throw std::runtime_error("read failed: "+file);
    return data;
}
template<class T> static std::vector<T> convert(const std::vector<int16_t>& raw) {
    std::vector<T> value(raw.size());
    for(size_t i=0;i<raw.size();++i) value[i].range(15,0)=uint16_t(raw[i]);
    return value;
}
static void compare(const std::vector<int16_t>& value,const std::string& file,const char* stage) {
    const auto expected=read_raw<int16_t>(file,int(value.size()));
    for(size_t i=0;i<value.size();++i) if(value[i]!=expected[i])
        throw std::runtime_error(std::string(stage)+" mismatch index="+std::to_string(i)+
                                 " got="+std::to_string(value[i])+" want="+std::to_string(expected[i]));
    std::cout<<"JOINT_MODEL_MATCH "<<stage<<" scalars="<<value.size()<<std::endl;
}
template<class T> static std::vector<int16_t> decode(const std::vector<T>& value) {
    std::vector<int16_t> raw(value.size());
    for(size_t i=0;i<value.size();++i) raw[i]=int16_t(value[i].range(15,0).to_uint());
    return raw;
}
int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("usage: test_joint_models GOLDEN MODEL_ASSETS");
        const std::string g=argv[1], m=argv[2];
        const auto rgb=read_raw<uint8_t>(g+"/rgb.u8",N);
        std::vector<int16_t> original(N),din(N),cin(LOW);
        if(joint_rgb8_prepare(rgb.data(),original.data(),din.data(),cin.data(),0x4A503031U)!=0)
            throw std::runtime_error("prepare status");
        compare(original,g+"/original.i16","prepare original");
        compare(din,g+"/d_input.i16","prepare D input");
        compare(cin,g+"/cnn_input.i16","prepare CNN input");
        auto input=convert<zero_dce_q16_t>(cin);
        const auto wr=read_raw<int8_t>(m+"/weights_int8.bin",10075);
        const auto br=read_raw<int32_t>(m+"/bias_int32.bin",486);
        const auto fr=read_raw<int8_t>(m+"/weight_frac.bin",486);
        const auto lr=read_raw<int16_t>(m+"/tanh_lut_q15.bin",4097);
        std::vector<zero_dce_q8_t> weights(wr.begin(),wr.end()),frac(fr.begin(),fr.end());
        std::vector<zero_dce_q32_t> bias(br.begin(),br.end());
        auto lut=convert<zero_dce_q16_t>(lr);
        std::vector<zero_dce_q16_t> alow(LOW),workspace(1221120);
        zero_dce_cnn_top(input.data(),weights.data(),bias.data(),frac.data(),lut.data(),alow.data(),workspace.data());
        compare(decode(alow),g+"/a_low.i16","CNN");
        auto low_fixed=convert<bilinear_fixed16_t>(decode(alow));
        std::vector<bilinear_fixed16_t> afull(N);
        bilinear_fixed16_buffered(low_fixed.data(),afull.data(),60,106);
        compare(decode(afull),g+"/a_full.i16","Bilinear");
        auto full_fixed=convert<curve_fixed16_t>(decode(afull));
        auto image_fixed=convert<curve_fixed16_t>(original);
        std::vector<curve_fixed16_t> light(N);
        curve_image_fixed16(image_fixed.data(),full_fixed.data(),light.data(),N);
        compare(decode(light),g+"/lowlight.i16","Curve");
        std::vector<int16_t> dout(N);
        uint64_t work_cycles=0,input_cycles=0;
        compact_d::set_trace(nullptr,nullptr);
        if(compact_d_top(din.data(),dout.data(),720,1272,0x44433031U,work_cycles,input_cycles)!=0)
            throw std::runtime_error("D status");
        compare(dout,g+"/d_output.i16","Compact D 720x1272");
        std::cout<<"JOINT_HLS_HOST_PASS scalars="<<5LL*N+2LL*LOW<<std::endl;
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<std::endl;return 1;}
}
