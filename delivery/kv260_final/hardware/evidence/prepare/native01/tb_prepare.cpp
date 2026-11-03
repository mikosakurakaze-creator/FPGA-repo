#include "joint_adapters.hpp"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <fstream>
#include <string>

// Compile the locked original implementation as a separate reference. Its
// original header declarations would conflict with the new physical word type.
#define JOINT_ADAPTERS_HPP
#define joint_rgb8_prepare frozen_rgb8_prepare
static const uint32_t JOINT_COPY_COOKIE = 0x4a433031;
#include "frozen/joint_adapters.cpp"
#undef joint_rgb8_prepare

static void fail(const char* what, int n, long actual, long expected) {
    std::fprintf(stderr, "PREPARE_FAIL %s index=%d actual=%ld expected=%ld\n", what, n, actual, expected);
    std::exit(1);
}
static void compare(const char* name, const std::vector<joint_word>& got,
                    const std::vector<int16_t>& expected) {
    for (int i=0; i<(int)expected.size(); ++i) {
        uint16_t bits=got[1+i/8].range(16*(i%8)+15,16*(i%8)).to_uint();
        int16_t value=static_cast<int16_t>(bits);
        if(value!=expected[i]) fail(name,i,value,expected[i]);
    }
    if(got.front()!=joint_word(0x1234) || got.back()!=joint_word(0x1234)) fail("guard",0,0,1);
}
int main(int argc, char** argv) {
    const int frames=(argc>1 && std::string(argv[1])=="--rtl") ? 2 : 3;
    std::vector<uint8_t> rgb(JOINT_COUNT);
    std::vector<int16_t> ref_i(JOINT_COUNT),ref_d(JOINT_COUNT),ref_c(JOINT_LOW_COUNT);
    std::vector<joint_word> packed(JOINT_COUNT/16);
    std::vector<joint_word> actual_i(JOINT_COUNT/8+2, joint_word(0x1234));
    std::vector<joint_word> actual_d(JOINT_COUNT/8+2, joint_word(0x1234));
    std::vector<joint_word> actual_c(JOINT_LOW_COUNT/8+2, joint_word(0x1234));
    if(joint_rgb8_prepare(packed.data(),actual_i.data()+1,actual_d.data()+1,actual_c.data()+1,0)!=-1)
        fail("invalid_cookie_status",0,0,-1);
    for(const auto& v:actual_i) if(v!=joint_word(0x1234)) fail("invalid_cookie_wrote_original",0,0,1);
    for(const auto& v:actual_d) if(v!=joint_word(0x1234)) fail("invalid_cookie_wrote_d",0,0,1);
    for(const auto& v:actual_c) if(v!=joint_word(0x1234)) fail("invalid_cookie_wrote_cnn",0,0,1);
    uint32_t random=0x28a0317u;
    for(int frame=0; frame<frames; ++frame) {
        for(int i=0; i<JOINT_COUNT; ++i) {
            random^=random<<13;random^=random>>17;random^=random<<5;
            rgb[i]=frame==0 ? uint8_t(i%256) : frame==1 ? uint8_t(random) : uint8_t((i/3%JOINT_W+i/(3*JOINT_W))&1 ? 255 : 0);
        }
        for(int w=0;w<JOINT_COUNT/16;++w) {
            joint_word word=0;
            for(int b=0;b<16;++b) word.range(8*b+7,8*b)=rgb[16*w+b];
            packed[w]=word;
        }
        if(frozen_rgb8_prepare(rgb.data(),ref_i.data(),ref_d.data(),ref_c.data(),JOINT_PREPARE_COOKIE)!=0)
            fail("reference_status",0,1,0);
        if(joint_rgb8_prepare(packed.data(),actual_i.data()+1,actual_d.data()+1,actual_c.data()+1,JOINT_PREPARE_COOKIE)!=0)
            fail("status",0,1,0);
        compare("original",actual_i,ref_i); compare("d",actual_d,ref_d); compare("cnn",actual_c,ref_c);
        std::printf("PREPARE_FRAME_PASS frame=%d original=%d d=%d cnn=%d\n",frame,JOINT_COUNT,JOINT_COUNT,JOINT_LOW_COUNT);
        std::fflush(stdout);
    }
    std::printf("PREPARE_ALL_PASS frames=%d invalid=1\n",frames);
    return 0;
}
