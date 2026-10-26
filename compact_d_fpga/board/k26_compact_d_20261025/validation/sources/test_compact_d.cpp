#include "compact_d.hpp"
#include "generated_parameters.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
const int MAX_SCALARS=3*720*1280;
struct TraceState {
    int h,w;
    std::vector<std::vector<int16_t> > values;
    std::vector<int> counts;
    TraceState(int height,int width):h(height),w(width),values(22),counts(22,0) {
        for(int n=0;n<22;++n) values[n].resize(compact_d::NODE_CHANNELS[n]*h*w);
    }
};
#ifndef COMPACT_D_RTL_TEST
void capture(int n,int c,int y,int x,int16_t value,void* user) {
    TraceState& t=*static_cast<TraceState*>(user);
    if(n<0 || n>=22 || c<0 || c>=compact_d::NODE_CHANNELS[n] || y<0 || y>=t.h || x<0 || x>=t.w)
        throw std::runtime_error("trace index out of bounds");
    t.values[n][(c*t.h+y)*t.w+x]=value;
    ++t.counts[n];
}
#endif
std::vector<int16_t> read_file(const std::string& path,int count) {
    std::ifstream f(path.c_str(),std::ios::binary|std::ios::ate);
    if(!f || f.tellg()!=std::streampos(2LL*count)) throw std::runtime_error("invalid input length: "+path);
    f.seekg(0);std::vector<int16_t> data(count);
    f.read(reinterpret_cast<char*>(data.data()),2LL*count);
    if(!f) throw std::runtime_error("input read failure: "+path);
    return data;
}
void write_file(const std::string& path,const int16_t* data,int count) {
    std::ofstream f(path.c_str(),std::ios::binary);
    f.write(reinterpret_cast<const char*>(data),2LL*count);
    if(!f) throw std::runtime_error("output write failure: "+path);
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::runtime_error("usage: test_compact_d CASES.txt");
        std::ifstream cases(argv[1]);
        int count=0; cases>>count;
        if(!cases || count<1) throw std::runtime_error("invalid case list");
        std::vector<int16_t> input(MAX_SCALARS,0),output(MAX_SCALARS,12345);
        for(int seq=0;seq<count;++seq) {
            int h=0,w=0; std::string input_path,golden,prefix;
            cases>>h>>w>>input_path>>golden>>prefix;
            if(!cases || h<1 || h>720 || w<1 || w>1280) throw std::runtime_error("bad shape");
            const int scalars=3*h*w;
            const std::vector<int16_t> src=read_file(input_path,scalars);
            std::copy(src.begin(),src.end(),input.begin());
            std::fill(output.begin(),output.end(),12345);
            TraceState traces(h,w);
#ifndef COMPACT_D_RTL_TEST
            compact_d::set_trace(capture,&traces);
#endif
            uint64_t work_cycles=0,input_cycles=0;
            const int rc=compact_d_top(input.data(),output.data(),h,w,0x44433031U,work_cycles,input_cycles);
            if(rc!=0) throw std::runtime_error("top returned error");
#ifndef COMPACT_D_RTL_TEST
            compact_d::set_trace(0,0);
            for(int n=0;n<22;++n) {
                const int size=compact_d::NODE_CHANNELS[n]*h*w;
                if(traces.counts[n]!=size) throw std::runtime_error("incomplete node trace");
                const std::string name=(n<10 ? "0" : "")+std::to_string(n)+"_"+compact_d::NODE_NAMES[n]+".i16";
                const std::vector<int16_t> expected=read_file(golden+"/"+name,size);
                if(traces.values[n]!=expected) {
                    for(int i=0;i<size;++i) if(traces.values[n][i]!=expected[i]) {
                        std::cerr<<"node="<<n<<" index="<<i<<" expected="<<expected[i]<<" actual="<<traces.values[n][i]<<std::endl;
                        break;
                    }
                    throw std::runtime_error("node mismatch");
                }
            }
#endif
            const std::vector<int16_t> expected=read_file(golden+"/21_output.relu.i16",scalars);
            if(!std::equal(expected.begin(),expected.end(),output.begin())) throw std::runtime_error("final output mismatch");
            if(!std::all_of(output.begin()+scalars,output.end(),[](int16_t v){return v==12345;}))
                throw std::runtime_error("write outside actual frame");
            write_file(prefix+".i16",output.data(),scalars);
            std::cout<<"D_FRAME_PASS seq="<<seq<<" h="<<h<<" w="<<w
                     <<" scope="
#ifdef COMPACT_D_RTL_TEST
                     <<"rtl_final_output_status_bounds"
#else
                     <<"host_all22_nodes"
#endif
                     <<std::endl;
        }
        uint64_t a=99,b=99;
        if(compact_d_top(input.data(),output.data(),1,1,0,a,b)!=-1) throw std::runtime_error("cookie rejection failure");
        if(compact_d_top(input.data(),output.data(),0,1,0x44433031U,a,b)!=-2) throw std::runtime_error("shape rejection failure");
        if(compact_d_top(input.data(),output.data(),720,1281,0x44433031U,a,b)!=-2) throw std::runtime_error("max shape rejection failure");
        std::cout<<"D_ALL_CASES_PASS frames="<<count<<" invalid=3"<<std::endl;
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"D_TEST_FAILED: "<<e.what()<<std::endl;
        return 1;
    }
}
