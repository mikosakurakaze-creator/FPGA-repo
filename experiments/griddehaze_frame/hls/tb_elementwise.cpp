#include "elementwise_top.hpp"
#include "fixed_math.hpp"
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
void require(bool pass,const char* what) { if(!pass) throw std::runtime_error(what); }

int boundary_tests() {
    int cases=0;
    // Each scale combination, signed endpoints, half ties, channel order,
    // coefficient signs, odd row length and a partial 256-element cache block.
    const int plane=259;
    const std::int16_t values[]={-32768,-32767,-20000,-3,-2,-1,0,1,2,3,20000,32767};
    std::vector<std::int16_t> a(2*plane),b(2*plane),out(4*plane+64),coef{8192,-16384};
    for(int i=0;i<2*plane;++i) { a[i]=values[i%12]; b[i]=values[(i+7)%12]; }
    for(int op=GDN_RELU;op<=GDN_CAT;++op) for(int fa=3;fa<=14;++fa)
        for(int fb=3;fb<=14;++fb) for(int fo=3;fo<=14;++fo) {
        const bool binary=op==GDN_ADD || op==GDN_CAT;
        const int co=op==GDN_CAT?4:2;
        std::fill(out.begin(),out.end(),std::int16_t(0x5A39));
        require(griddehaze_elementwise_top(a.data(),b.data(),coef.data(),out.data()+32,
                    a.size(),b.size(),coef.size(),co*plane,op,2,binary?2:0,co,1,plane,fa,fb,fo)==0,"boundary descriptor");
        for(int i=0;i<co*plane;++i) {
            std::int64_t expected;
            if(op==GDN_CAT) expected=i<2*plane?gdn::round_shift(a[i],fa-fo):gdn::round_shift(b[i-2*plane],fb-fo);
            else if(op==GDN_ADD) expected=gdn::round_shift(a[i],fa-fo)+gdn::round_shift(b[i],fb-fo);
            else if(op==GDN_MULCOEF) expected=gdn::round_shift(std::int64_t(a[i])*coef[i/plane],fa+14-fo);
            else expected=std::max<std::int64_t>(0,gdn::round_shift(a[i],fa-fo));
            require(out[32+i]==gdn::sat(expected),"boundary arithmetic");
        }
        require(std::all_of(out.begin(),out.begin()+32,[](std::int16_t x){return x==0x5A39;}),"boundary prefix guard");
        require(std::all_of(out.begin()+32+co*plane,out.end(),[](std::int16_t x){return x==0x5A39;}),"boundary suffix guard");
        ++cases;
    }
    std::int16_t x=20000,y=-10000,z=0;
    require(griddehaze_elementwise_top(&x,&y,nullptr,&z,1,1,0,1,GDN_ADD,1,1,1,1,1,13,14,14)==0 && z==30000,
            "addition must align wide before saturation");
    ++cases;
    // All invalid descriptors use null pointers: rejection must precede reads.
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,1,0,1,0,1,1,1,1,1,14,14,14)==1,"invalid op");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,1,0,1,GDN_ADD,1,1,1,1,1,2,14,14)==1,"invalid scale");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,1,0,1,GDN_CAT,1,1,1,1,1,14,14,14)==1,"invalid channels");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,0,0,1,GDN_RELU,1,0,1,721,1,14,14,14)==1,"invalid height");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,0,0,0,1,GDN_RELU,1,0,1,1,1,14,14,14)==2,"short a");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,0,0,1,GDN_ADD,1,1,1,1,1,14,14,14)==2,"short b");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,0,0,1,GDN_MULCOEF,1,0,1,1,1,14,14,14)==2,"short coefficients");
    require(griddehaze_elementwise_top(nullptr,nullptr,nullptr,nullptr,1,0,0,0,GDN_RELU,1,0,1,1,1,14,14,14)==2,"short output");
    return cases+8;
}

int main(int argc,char**argv) try {
    if(argc!=2) throw std::runtime_error("provide cases.txt");
    const int boundaries=boundary_tests();
    std::ifstream cases(argv[1]); int count; cases>>count;
    for(int index=0;index<count;++index) {
        std::string prefix; int op,ca,cb,co,h,w,fa,fb,fo;
        cases>>prefix>>op>>ca>>cb>>co>>h>>w>>fa>>fb>>fo;
        require(bool(cases),"case metadata");
        const auto a=read<std::int16_t>(prefix+"_a.raw",ca*h*w);
        const auto b=read<std::int16_t>(prefix+"_b.raw",cb*h*w);
        const auto coef=read<std::int16_t>(prefix+"_coefficients.raw",op==GDN_MULCOEF?co:0);
        const auto expected=read<std::int16_t>(prefix+"_expected.raw",co*h*w);
        auto aa=a,bb=b,cc=coef;
        std::vector<std::int16_t> output(co*h*w+64,0x5A39);
        require(griddehaze_elementwise_top(aa.data(),bb.data(),cc.data(),output.data()+32,
                    aa.size(),bb.size(),cc.size(),expected.size(),op,ca,cb,co,h,w,fa,fb,fo)==0,"Golden descriptor");
        require(std::equal(expected.begin(),expected.end(),output.begin()+32),"Golden mismatch");
        require(aa==a && bb==b && cc==coef,"input modified");
        require(std::all_of(output.begin(),output.begin()+32,[](std::int16_t x){return x==0x5A39;}),"prefix guard");
        require(std::all_of(output.end()-32,output.end(),[](std::int16_t x){return x==0x5A39;}),"suffix guard");
        std::ofstream f(prefix+"_actual.raw",std::ios::binary);
        f.write(reinterpret_cast<const char*>(output.data()+32),expected.size()*2);
        require(bool(f),"actual raw write");
    }
    std::cout<<"ALL_ELEMENTWISE_CASES_PASS nodes="<<count<<" boundaries="<<boundaries<<"\n";
    return 0;
} catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; return 1; }
