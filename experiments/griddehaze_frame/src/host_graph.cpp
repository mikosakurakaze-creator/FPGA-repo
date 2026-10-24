// Independent B CPU executor. No A execution code or Golden is read by this process.
#include "fixed_math.hpp"
#ifdef GDN_TILE_BACKEND
#include "../hls/conv_tile_top.hpp"
#endif
#ifdef GDN_ELEMENTWISE_BACKEND
#include "../hls/elementwise_top.hpp"
#endif
#include <algorithm>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>

std::string digest(const void* data, std::size_t size) {
    if(size>ULONG_MAX) throw std::runtime_error("hash byte count");
    BCRYPT_ALG_HANDLE algorithm=nullptr; BCRYPT_HASH_HANDLE hash=nullptr;
    const auto check=[](NTSTATUS s) { if(s<0) throw std::runtime_error("BCrypt SHA256"); };
    check(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0));
    DWORD length=0,returned=0;
    check(BCryptGetProperty(algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&length),sizeof(length),&returned,0));
    std::vector<UCHAR> object(length),bytes(32);
    check(BCryptCreateHash(algorithm,&hash,object.data(),length,nullptr,0,0));
    check(BCryptHashData(hash,reinterpret_cast<PUCHAR>(const_cast<void*>(data)),static_cast<ULONG>(size),0));
    check(BCryptFinishHash(hash,bytes.data(),32,0));
    BCryptDestroyHash(hash); BCryptCloseAlgorithmProvider(algorithm,0);
    const char hex[]="0123456789abcdef"; std::string result;
    for(auto b:bytes) { result+=hex[b>>4]; result+=hex[b&15]; }
    return result;
}

struct Node {
    std::string id, op;
    int region, c,h,w,frac, a,b, k,stride,pad,weight_bits;
    std::size_t offset, weight,bias,coef;
    std::vector<int> shifts;
    std::size_t count() const { return std::size_t(c)*h*w; }
};
template<class T> T load(const std::vector<char>& bytes, std::size_t at) {
    if (at+sizeof(T)>bytes.size()) throw std::out_of_range("parameter read");
    T value; std::memcpy(&value,bytes.data()+at,sizeof(T)); return value;
}
std::vector<char> read_file(const std::string& path) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    if (!f) throw std::runtime_error("read: "+path);
    const auto size=f.tellg(); std::vector<char> data(static_cast<std::size_t>(size));
    f.seekg(0); f.read(data.data(),size);
    if (!f) throw std::runtime_error("short read");
    return data;
}
struct Guarded {
    std::vector<std::int16_t> memory;
    explicit Guarded(std::size_t bytes):memory(bytes/2+64,std::int16_t(0x5A39)) {}
    std::int16_t* data() { return memory.data()+32; }
    bool guards() const {
        return std::all_of(memory.begin(),memory.begin()+32,[](auto x){return x==0x5A39;}) &&
               std::all_of(memory.end()-32,memory.end(),[](auto x){return x==0x5A39;});
    }
};
int main(int argc,char**argv) try {
    if (argc!=6) throw std::invalid_argument("host_graph PLAN PARAMETERS INPUT OUTPUT_DIR DUMP_NODES(0/1)");
    const std::uint16_t endian=1;
    if (*reinterpret_cast<const unsigned char*>(&endian)!=1) throw std::runtime_error("little endian host required");
    std::ifstream plan(argv[1]);
    std::string magic,bundle; int count; std::size_t scratch_bytes,input_bytes,output_bytes;
    plan>>magic>>bundle>>count>>scratch_bytes>>input_bytes>>output_bytes;
    if (magic!="GDN_B_PLAN_1" || count!=320) throw std::runtime_error("plan header");
    std::vector<Node> nodes;
    for (int i=0;i<count;++i) {
        Node n; int shift_count;
        plan>>n.id>>n.op>>n.region>>n.offset>>n.c>>n.h>>n.w>>n.frac>>n.a>>n.b
            >>n.k>>n.stride>>n.pad>>n.weight_bits>>n.weight>>n.bias>>n.coef>>shift_count;
        n.shifts.resize(shift_count);
        for(auto& s:n.shifts) plan>>s;
        if(!plan || n.c<1 || n.h<1 || n.w<1 || n.region<0 || n.region>2) throw std::runtime_error("invalid node");
        if(n.op!="input" && (n.a<0 || n.a>=i)) throw std::runtime_error("invalid source");
        if(n.b>=i) throw std::runtime_error("invalid source2");
        nodes.push_back(n);
    }
    auto blob=read_file(argv[2]),input=read_file(argv[3]);
    if(input.size()!=input_bytes) throw std::runtime_error("input byte count");
    Guarded scratch(scratch_bytes),in(input_bytes),out(output_bytes);
    std::vector<Guarded*> regions{&scratch,&in,&out};
    std::memcpy(in.data(),input.data(),input_bytes);
    auto ptr=[&](const Node& n) {
        auto* region=regions.at(n.region);
        if(n.offset%2 || n.offset+n.count()*2> (region->memory.size()-64)*2) throw std::runtime_error("feature bounds");
        return region->data()+n.offset/2;
    };
    const std::string output_dir(argv[4]);
    std::ofstream hashes(output_dir+"/node_hashes.txt");
    const auto start=std::chrono::steady_clock::now();
    for (const auto& n:nodes) {
        auto* dst=ptr(n);
        const Node& a=nodes[n.a<0?0:n.a]; const Node& b=nodes[n.b<0?0:n.b];
        auto* x=ptr(a); auto* y=ptr(b);
        if(n.op=="conv" || n.op=="deconv") {
            const bool transpose=n.op=="deconv";
#ifdef GDN_TILE_BACKEND
            if(n.weight_bits!=16) throw std::runtime_error("tile INT16 weights required");
            const auto weight_count=std::size_t(a.c)*n.c*n.k*n.k;
            std::vector<std::int16_t> weights(weight_count);
            std::vector<std::int64_t> bias(n.c);
            std::vector<std::int8_t> shifts(n.c);
            for(std::size_t i=0;i<weight_count;++i) weights[i]=load<std::int16_t>(blob,n.weight+i*2);
            for(int i=0;i<n.c;++i) { bias[i]=load<std::int64_t>(blob,n.bias+i*8); shifts[i]=std::int8_t(n.shifts.at(i)); }
            for(int co=0;co<n.c;co+=8) for(int yy=0;yy<n.h;yy+=16) for(int xx=0;xx<n.w;xx+=16) {
                const auto status=griddehaze_conv_tile_top(x,weights.data(),bias.data(),shifts.data(),dst,
                    a.c,n.c,a.h,a.w,n.h,n.w,n.k,n.stride,n.pad,transpose,yy,xx,co);
                if(status) throw std::runtime_error("tile descriptor rejected: "+n.id+" code="+std::to_string(status));
            }
#else
            for(int o=0;o<n.c;++o) {
                // Output channel/row; only one accumulator row, never full-frame INT64.
                for(int oy=0;oy<n.h;++oy) {
                    std::vector<std::int64_t> accum(n.w,load<std::int64_t>(blob,n.bias+o*8));
                    for(int ci=0;ci<a.c;++ci) for(int ky=0;ky<n.k;++ky) {
                        int iy=transpose ? oy+n.pad-ky : oy*n.stride-n.pad+ky;
                        if(transpose) { if(iy<0 || iy%n.stride) continue; iy/=n.stride; }
                        if(iy<0 || iy>=a.h) continue;
                        for(int kx=0;kx<n.k;++kx) {
                            const auto wi=transpose ? ((ci*n.c+o)*n.k+ky)*n.k+kx : ((o*a.c+ci)*n.k+ky)*n.k+kx;
                            const std::int64_t weight=n.weight_bits==16 ? load<std::int16_t>(blob,n.weight+wi*2) : load<std::int8_t>(blob,n.weight+wi);
                            for(int ox=0;ox<n.w;++ox) {
                                int ix=transpose ? ox+n.pad-kx : ox*n.stride-n.pad+kx;
                                if(transpose) { if(ix<0 || ix%n.stride) continue; ix/=n.stride; }
                                if(ix>=0 && ix<a.w) accum[ox]+=std::int64_t(x[(ci*a.h+iy)*a.w+ix])*weight;
                            }
                        }
                    }
                    for(int ox=0;ox<n.w;++ox) dst[(o*n.h+oy)*n.w+ox]=gdn::sat(gdn::round_shift(accum[ox],n.shifts.at(o)));
                }
            }
#endif
        } else if(n.op=="relu" || n.op=="mulcoef" || n.op=="add" || n.op=="cat") {
#ifdef GDN_ELEMENTWISE_BACKEND
            const bool binary=n.op=="add" || n.op=="cat";
            const int op=n.op=="relu"?GDN_RELU:n.op=="mulcoef"?GDN_MULCOEF:n.op=="add"?GDN_ADD:GDN_CAT;
            std::vector<std::int16_t> coefficients(n.op=="mulcoef"?n.c:0);
            for(std::size_t i=0;i<coefficients.size();++i) coefficients[i]=load<std::int16_t>(blob,n.coef+i*2);
            const int status=griddehaze_elementwise_top(x,binary?y:nullptr,coefficients.data(),dst,
                a.count(),binary?b.count():0,coefficients.size(),n.count(),op,a.c,binary?b.c:0,n.c,n.h,n.w,a.frac,b.frac,n.frac);
            if(status) throw std::runtime_error("elementwise descriptor rejected: "+n.id+" code="+std::to_string(status));
#else
            for(std::size_t i=0;i<n.count();++i) {
                std::int64_t value;
                if(n.op=="cat") {
                    value=i<a.count()?gdn::round_shift(x[i],a.frac-n.frac):gdn::round_shift(y[i-a.count()],b.frac-n.frac);
                } else if(n.op=="add") {
                    value=gdn::round_shift(x[i],a.frac-n.frac)+gdn::round_shift(y[i],b.frac-n.frac);
                } else if(n.op=="relu") {
                    value=std::max<std::int64_t>(0,gdn::round_shift(x[i],a.frac-n.frac));
                } else {
                    const auto co=i/(n.h*n.w);
                    value=gdn::round_shift(std::int64_t(x[i])*load<std::int16_t>(blob,n.coef+co*2),a.frac+14-n.frac);
                }
                dst[i]=gdn::sat(value);
            }
#endif
        } else if(n.op!="input") throw std::runtime_error("unsupported op");
        hashes<<n.id<<" "<<n.count()*2<<" "<<digest(dst,n.count()*2)<<"\n";
        if(!hashes) throw std::runtime_error("hash report failed");
        if(std::string(argv[5])=="1") {
            std::string name=n.id; std::replace(name.begin(),name.end(),'.','_');
            std::ofstream f(output_dir+"/nodes/"+name+".raw",std::ios::binary);
            f.write(reinterpret_cast<const char*>(dst),n.count()*2);
            if(!f) throw std::runtime_error("dump failed");
        }
    }
    if(!in.guards() || !out.guards() || !scratch.guards()) throw std::runtime_error("guard corruption");
    if(std::memcmp(in.data(),input.data(),input_bytes)) throw std::runtime_error("input modified");
    std::ofstream output(output_dir+"/output.raw",std::ios::binary);
    output.write(reinterpret_cast<const char*>(ptr(nodes.back())),output_bytes);
    if(!output) throw std::runtime_error("output write");
    const auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    std::cout<<"B_CPU_COMPLETE nodes="<<count<<" guards=PASS input_unchanged=PASS seconds="<<elapsed<<" bundle="<<bundle<<"\n";
    return 0;
} catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; return 1; }
