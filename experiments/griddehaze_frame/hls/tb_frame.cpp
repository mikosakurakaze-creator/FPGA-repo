#include "frame_top.hpp"
#include "generated_model.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<std::string> expected_files;
std::string active_prefix;
int observed=0;
template<class T> std::vector<T> read(const std::string& file) {
    std::ifstream f(file,std::ios::binary|std::ios::ate);
    if(!f) throw std::runtime_error("read "+file);
    const auto size=f.tellg();
    if(size<0 || std::size_t(size)%sizeof(T)) throw std::runtime_error("file size "+file);
    std::vector<T> data(std::size_t(size)/sizeof(T));
    f.seekg(0);f.read(reinterpret_cast<char*>(data.data()),size);
    if(!f) throw std::runtime_error("short read "+file);
    return data;
}
void require(bool p,const std::string& msg) { if(!p) throw std::runtime_error(msg); }
struct Buffer {
    std::vector<std::int16_t> values;
    explicit Buffer(std::size_t bytes):values((bytes+1)/2+64,std::int16_t(0x5A39)) {}
    std::int16_t* data() { return values.data()+32; }
    bool guards() const {
        return std::all_of(values.begin(),values.begin()+32,[](std::int16_t x){return x==0x5A39;}) &&
               std::all_of(values.end()-32,values.end(),[](std::int16_t x){return x==0x5A39;});
    }
};
}

void gdn_frame_observe(int node,const std::int16_t* values,std::uint32_t elements) {
    require(node==observed && node<int(expected_files.size()),"observation order");
    const auto expected=read<std::int16_t>(expected_files[node]);
    require(expected.size()==elements,"node length "+std::to_string(node));
    for(std::size_t i=0;i<elements;++i) if(values[i]!=expected[i]) {
        throw std::runtime_error("node="+std::to_string(node)+" index="+std::to_string(i)+
                                 " actual="+std::to_string(values[i])+" expected="+std::to_string(expected[i]));
    }
    if(!active_prefix.empty()) {
        std::ofstream f(active_prefix+"_node"+std::to_string(node)+".raw",std::ios::binary);
        f.write(reinterpret_cast<const char*>(values),elements*2);
        require(bool(f),"node dump");
    }
    ++observed;
}

int main(int argc,char**argv) try {
    require(argc==2,"provide cases.txt");
    std::ifstream f(argv[1]);std::string parameter_file;int cases;
    f>>parameter_file>>cases;require(bool(f),"cases header");
    auto parameters=read<std::int16_t>(parameter_file);
    require(parameters.size()*2==gdn_model::PARAMETER_BYTES,"parameter length");
    const auto original_parameters=parameters;
    int negative_tests=0;
    for(int test=0;test<cases;++test) {
        std::string prefix,input_file,layout_file,index_file;int h,w,warm;
        f>>prefix>>input_file>>layout_file>>index_file>>h>>w>>warm;require(bool(f),"case row");
        auto input=read<std::int16_t>(input_file);const auto original_input=input;
        auto layout=read<std::uint32_t>(layout_file);const auto original_layout=layout;
        require(layout.size()==336,"layout size");
        const std::uint32_t image_bytes=std::uint32_t(input.size()*2),scratch_bytes=layout[6];
        Buffer output(image_bytes),scratch(scratch_bytes);
        expected_files.clear();
        std::ifstream paths(index_file);std::string path;
        while(paths>>path) expected_files.push_back(path);
        require(expected_files.size()==320,"expected paths count");
        std::uint32_t completed=0,model=0,abi=0;
        auto run=[&](std::uint32_t ib,std::uint32_t ob,std::uint32_t sb,std::uint32_t pb,
                     std::uint32_t lb,int ih,int iw,std::uint32_t mi,std::uint32_t av) {
            return griddehaze_frame_top(input.data(),output.data(),scratch.data(),parameters.data(),layout.data(),
                ib,ob,sb,pb,lb,ih,iw,mi,av,completed,model,abi);
        };
        auto standard=[&]() { return run(image_bytes,image_bytes,scratch_bytes,parameters.size()*2,
                    layout.size()*4,h,w,gdn_model::MODEL_ID,gdn_model::ABI); };
        if(test==0) {
            require(run(image_bytes,image_bytes,scratch_bytes,parameters.size()*2,1344,h,w,0,gdn_model::ABI)==1,"bad model");++negative_tests;
            require(run(image_bytes,image_bytes,scratch_bytes,parameters.size()*2,1344,h,w,gdn_model::MODEL_ID,0)==1,"bad ABI");++negative_tests;
            require(run(image_bytes,image_bytes,scratch_bytes,parameters.size()*2,1344,3,w,gdn_model::MODEL_ID,gdn_model::ABI)==1,"bad H");++negative_tests;
            require(run(0,image_bytes,scratch_bytes,parameters.size()*2,1344,h,w,gdn_model::MODEL_ID,gdn_model::ABI)==2,"short input");++negative_tests;
            require(run(image_bytes,0,scratch_bytes,parameters.size()*2,1344,h,w,gdn_model::MODEL_ID,gdn_model::ABI)==2,"short output");++negative_tests;
            require(run(image_bytes,image_bytes,scratch_bytes,0,1344,h,w,gdn_model::MODEL_ID,gdn_model::ABI)==2,"short parameters");++negative_tests;
            require(run(image_bytes,image_bytes,scratch_bytes,parameters.size()*2,1340,h,w,gdn_model::MODEL_ID,gdn_model::ABI)==2,"short layout");++negative_tests;
            layout[8]^=1;require(standard()==3,"bad bundle");layout=original_layout;++negative_tests;
            layout[17]|=1;require(standard()==4,"unaligned scratch");layout=original_layout;++negative_tests;
            layout[17]=scratch_bytes;require(standard()==4,"scratch overflow");layout=original_layout;++negative_tests;
            layout[18]=layout[17];require(standard()==5,"live tensor alias");layout=original_layout;++negative_tests;
            require(observed==0,"invalid layout executed arithmetic");
            require(std::all_of(output.values.begin(),output.values.end(),[](std::int16_t v){return v==0x5A39;}) &&
                    std::all_of(scratch.values.begin(),scratch.values.end(),[](std::int16_t v){return v==0x5A39;}),"invalid descriptor wrote feature memory");
        }
        for(int pass=0;pass<(warm?2:1);++pass) {
            observed=0;active_prefix=pass==0?prefix:"";
            // A warm run must write a fresh output, rather than pass because
            // the first run left an already-correct image in host memory.
            std::fill(output.data(),output.data()+image_bytes/2,std::int16_t(0x39A5));
            require(standard()==0,"frame status");
            require(completed==320 && model==gdn_model::MODEL_ID && abi==gdn_model::ABI,"frame completion");
#ifndef GDN_RTL_TESTBENCH
            require(observed==320,"C simulation node observations");
#endif
            // This independent final-image comparison also runs in RTL co-sim.
            // The C-only observation hook is absent from synthesized RTL.
            const auto expected_output=read<std::int16_t>(expected_files.back());
            require(expected_output.size()==image_bytes/2,"final output length");
            require(std::equal(expected_output.begin(),expected_output.end(),output.data()),"final output mismatch");
            require(input==original_input && parameters==original_parameters && layout==original_layout,"readonly input changed");
            require(output.guards() && scratch.guards(),"DMA region guard changed");
            if(pass==0) {
                std::ofstream raw(prefix+"_output.raw",std::ios::binary);
                raw.write(reinterpret_cast<const char*>(output.data()),image_bytes);
                require(bool(raw),"output write");
            }
        }
        std::cout<<"FRAME_EXACT case="<<test<<" completed_nodes=320 warm="<<warm<<" final_output=PASS host_guards=PASS\n";
    }
#ifdef GDN_RTL_TESTBENCH
    std::cout<<"RTL_TESTBENCH_SCOPE=final_output_and_status_not_per_node\n";
#else
    std::cout<<"C_TESTBENCH_SCOPE=all_320_nodes_and_final_output\n";
#endif
    std::cout<<"ALL_FRAME_CASES_PASS cases="<<cases<<" negative_tests="<<negative_tests<<"\n";
    return 0;
} catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; return 1; }
