#include "weather_frame.h"
#include "params_derain.h"
#include "params_dehaze.h"
#if defined(__SYNTHESIS__) && !defined(WEATHER_PORTABLE_SYNTH_TEST)
#include <ap_int.h>
#include <hls_stream.h>
#else
#include <deque>
#include <stdexcept>
#endif

namespace weather_b {
#if defined(__SYNTHESIS__) && !defined(WEATHER_PORTABLE_SYNTH_TEST)
typedef ap_uint<176> Pixel;
template<typename T> using Stream = hls::stream<T>;
static int16_t lane(const Pixel& p, int c) {
#pragma HLS INLINE
    return int16_t(p.range(c*16+15,c*16));
}
static void put(Pixel& p,int c,int16_t v) {
#pragma HLS INLINE
    p.range(c*16+15,c*16)=uint16_t(v);
}
#else
// Unbounded FIFOs for sequential host execution; hardware FIFOs are bounded.
struct Pixel { int16_t value[11]; Pixel() : value{} {} };
template<typename T> class Stream {
    std::deque<T> data;
public:
    void write(const T& v) { data.push_back(v); }
    T read() { if(data.empty())throw std::runtime_error("stream underflow");
        T v=data.front();data.pop_front();return v; }
};
static int16_t lane(const Pixel& p,int c) { return p.value[c]; }
static void put(Pixel& p,int c,int16_t v) { p.value[c]=v; }
#endif
#ifndef __SYNTHESIS__
static ScalarTrace trace_callback=0;
static void* trace_user=0;
void set_trace(ScalarTrace cb,void* user) { trace_callback=cb;trace_user=user; }
#endif
static void trace(int node,int c,int y,int x,int16_t v) {
#pragma HLS INLINE
#ifndef __SYNTHESIS__
    if(trace_callback)trace_callback(node,c,y,x,v,trace_user);
#else
    (void)node;(void)c;(void)y;(void)x;(void)v;
#endif
}
static int32_t rne(int32_t v,int shift) {
#pragma HLS INLINE
    if(!shift)return v;
    const uint32_t mag=v<0 ? uint32_t(-(v+1))+1U : uint32_t(v);
    uint32_t q=mag>>shift;
    const uint32_t rem=mag&((uint32_t(1)<<shift)-1U),half=uint32_t(1)<<(shift-1);
    if(rem>half || (rem==half && (q&1U)))++q;
    return v<0 ? -int32_t(q) : int32_t(q);
}
static int16_t sat(int32_t v) {
#pragma HLS INLINE
    return v < -32768 ? int16_t(-32768) : v > 32767 ? int16_t(32767) : int16_t(v);
}
static int32_t scale(int16_t v,int from,int to) {
#pragma HLS INLINE
    return from>=to ? rne(v,from-to) : int32_t(v)*(int32_t(1)<<(to-from));
}
template<int L> static int8_t weight(int task,int i) {
#pragma HLS INLINE
    return task ? weather::detail::DEHAZE_PARAMS.layers[L].weights[i]
                : weather::detail::DERAIN_PARAMS.layers[L].weights[i];
}
template<int L> static int32_t bias(int task,int c) {
#pragma HLS INLINE
    return task ? weather::detail::DEHAZE_PARAMS.layers[L].bias[c]
                : weather::detail::DERAIN_PARAMS.layers[L].bias[c];
}
template<int L> static int out_frac(int task) {
#pragma HLS INLINE
    return task ? weather::detail::DEHAZE_PARAMS.layers[L].output_frac
                : weather::detail::DERAIN_PARAMS.layers[L].output_frac;
}
template<int L> static int16_t quantize(int32_t v,int task,int c) {
#pragma HLS INLINE
    const int shift=task
        ? weather::detail::DEHAZE_PARAMS.layers[L].input_frac+weather::detail::DEHAZE_PARAMS.layers[L].weight_frac[c]-weather::detail::DEHAZE_PARAMS.layers[L].output_frac
        : weather::detail::DERAIN_PARAMS.layers[L].input_frac+weather::detail::DERAIN_PARAMS.layers[L].weight_frac[c]-weather::detail::DERAIN_PARAMS.layers[L].output_frac;
    return sat(rne(v,shift));
}
template<int N> static int32_t sum_tree(int32_t (&v)[N]) {
#pragma HLS INLINE
    for(int step=1;step<N;step*=2) {
#pragma HLS UNROLL
        for(int i=0;i<N;i+=2*step) {
#pragma HLS UNROLL
            v[i]+=v[i+step];
        }
    }
    return v[0];
}
static void read_plane(const int16_t* input,int start,int width,Stream<int16_t>& stream) {
#pragma HLS INLINE off
    for(int x=0;x<width;++x) {
#pragma HLS PIPELINE II=1
        stream.write(input[start+x]);
    }
}
static void read_nchw(const int16_t* input,int h,int w,Stream<int16_t>& r,Stream<int16_t>& g,Stream<int16_t>& b) {
#pragma HLS INLINE off
    for(int y=0;y<h;++y) {
#pragma HLS LOOP_FLATTEN off
        read_plane(input,y*w,w,r);read_plane(input,(h+y)*w,w,g);read_plane(input,(2*h+y)*w,w,b);
    }
}
static void interleave(Stream<int16_t>& r,Stream<int16_t>& g,Stream<int16_t>& b,Stream<Pixel>& out,int h,int w) {
#pragma HLS INLINE off
    for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
#pragma HLS PIPELINE II=1
        Pixel p{};
        const int16_t rv=r.read(),gv=g.read(),bv=b.read();
        put(p,8,rv);put(p,9,gv);put(p,10,bv);
        trace(0,0,y,x,rv);trace(0,1,y,x,gv);trace(0,2,y,x,bv);out.write(p);
    }
}
// Padding overwrites stale row state before the first valid output of each
// invocation, including width/task changes. Carry RGB with its center feature.
template<int STAGE> static void spatial(Stream<Pixel>& input,Stream<Pixel>& output,int h,int w,int task) {
#pragma HLS INLINE off
    static Pixel rows[2][1282];
    Pixel window[3][3];
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS BIND_STORAGE variable=rows type=ram_2p impl=uram
#pragma HLS ARRAY_PARTITION variable=window complete dim=0
    for(int y=0;y<h+2;++y)for(int x=0;x<w+2;++x) {
#pragma HLS PIPELINE II=1
        Pixel p{};
        if(y>0 && y<=h && x>0 && x<=w)p=input.read();
        const Pixel top=rows[0][x],middle=rows[1][x];
        rows[0][x]=middle;rows[1][x]=p;
        for(int r=0;r<3;++r) {
#pragma HLS UNROLL
            window[r][0]=window[r][1];window[r][1]=window[r][2];
        }
        window[0][2]=top;window[1][2]=middle;window[2][2]=p;
        if(y>=2 && x>=2) {
            Pixel result=window[1][1];
            if(STAGE==0) {
                for(int oc=0;oc<8;++oc) {
#pragma HLS UNROLL
                    int32_t products[32];
#pragma HLS ARRAY_PARTITION variable=products complete
                    for(int i=0;i<32;++i) {
#pragma HLS UNROLL
                        products[i]=i<27 ? int32_t(lane(window[(i%9)/3][i%3],8+i/9))*int32_t(weight<0>(task,oc*27+i)) : 0;
                    }
                    const int16_t q=quantize<0>(sum_tree(products)+bias<0>(task,oc),task,oc);
                    const int16_t a=q<0 ? int16_t(0) : q;
                    trace(1,oc,y-2,x-2,q);trace(2,oc,y-2,x-2,a);put(result,oc,a);
                }
            } else {
                // Valid indices even in the compile-time discarded STAGE=0 branch.
                const int BLOCK=STAGE>0 ? STAGE-1 : 0,DL=STAGE>0 ? 2*STAGE-1 : 0,PL=2*STAGE;
                int16_t depth[8];
#pragma HLS ARRAY_PARTITION variable=depth complete
                for(int c=0;c<8;++c) {
#pragma HLS UNROLL
                    int32_t products[16];
#pragma HLS ARRAY_PARTITION variable=products complete
                    for(int i=0;i<16;++i) {
#pragma HLS UNROLL
                        products[i]=i<9 ? int32_t(lane(window[i/3][i%3],c))*int32_t(weight<DL>(task,c*9+i)) : 0;
                    }
                    const int16_t q=quantize<DL>(sum_tree(products)+bias<DL>(task,c),task,c);
                    depth[c]=q<0 ? int16_t(0) : q;
                    trace(3+BLOCK*5,c,y-2,x-2,q);trace(4+BLOCK*5,c,y-2,x-2,depth[c]);
                }
                const int previous=STAGE>1 ? STAGE-2 : 0;
                const int skip_frac=STAGE==1 ? out_frac<0>(task) : (task ? weather::detail::DEHAZE_PARAMS.add_frac[previous] : weather::detail::DERAIN_PARAMS.add_frac[previous]);
                const int add_frac=task ? weather::detail::DEHAZE_PARAMS.add_frac[BLOCK] : weather::detail::DERAIN_PARAMS.add_frac[BLOCK];
                for(int oc=0;oc<8;++oc) {
#pragma HLS UNROLL
                    int32_t products[8];
#pragma HLS ARRAY_PARTITION variable=products complete
                    for(int ic=0;ic<8;++ic) {
#pragma HLS UNROLL
                        products[ic]=int32_t(depth[ic])*int32_t(weight<PL>(task,oc*8+ic));
                    }
                    const int16_t point=quantize<PL>(sum_tree(products)+bias<PL>(task,oc),task,oc);
                    const int16_t added=sat(scale(lane(window[1][1],oc),skip_frac,add_frac)+scale(point,out_frac<PL>(task),add_frac));
                    const int16_t a=added<0 ? int16_t(0) : added;
                    trace(5+BLOCK*5,oc,y-2,x-2,point);trace(6+BLOCK*5,oc,y-2,x-2,added);trace(7+BLOCK*5,oc,y-2,x-2,a);put(result,oc,a);
                }
            }
            output.write(result);
        }
    }
}
static void tail(Stream<Pixel>& input,Stream<Pixel>& output,int h,int w,int task) {
#pragma HLS INLINE off
    const int frac=task ? weather::detail::DEHAZE_PARAMS.tail_frac : weather::detail::DERAIN_PARAMS.tail_frac;
    for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
#pragma HLS PIPELINE II=1
        const Pixel p=input.read();Pixel result{};
        for(int oc=0;oc<3;++oc) {
#pragma HLS UNROLL
            int32_t products[8];
#pragma HLS ARRAY_PARTITION variable=products complete
            for(int ic=0;ic<8;++ic) {
#pragma HLS UNROLL
                products[ic]=int32_t(lane(p,ic))*int32_t(weight<11>(task,oc*8+ic));
            }
            const int16_t residual=quantize<11>(sum_tree(products)+bias<11>(task,oc),task,oc);
            const int32_t v=int32_t(lane(p,8+oc))+scale(residual,frac,14);
            const int16_t q=v<0 ? int16_t(0) : v>16384 ? int16_t(16384) : int16_t(v);
            trace(28,oc,y,x,residual);trace(29,oc,y,x,q);put(result,8+oc,q);
        }
        output.write(result);
    }
}
static void deinterleave(Stream<Pixel>& input,Stream<int16_t>& r,Stream<int16_t>& g,Stream<int16_t>& b,int h,int w) {
#pragma HLS INLINE off
    for(int i=0;i<h*w;++i) {
#pragma HLS PIPELINE II=1
        const Pixel p=input.read();r.write(lane(p,8));g.write(lane(p,9));b.write(lane(p,10));
    }
}
static void write_plane(int16_t* output,int start,int w,Stream<int16_t>& in) {
#pragma HLS INLINE off
    for(int x=0;x<w;++x) {
#pragma HLS PIPELINE II=1
        output[start+x]=in.read();
    }
}
static void write_nchw(int16_t* output,int h,int w,Stream<int16_t>& r,Stream<int16_t>& g,Stream<int16_t>& b) {
#pragma HLS INLINE off
    for(int y=0;y<h;++y) {
#pragma HLS LOOP_FLATTEN off
        write_plane(output,y*w,w,r);write_plane(output,(h+y)*w,w,g);write_plane(output,(2*h+y)*w,w,b);
    }
}
static void frame(const int16_t* input,int16_t* output,int h,int w,int task) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    Stream<int16_t> ir,ig,ib,orr,og,ob;
    Stream<Pixel> s0,s1,s2,s3,s4,s5,s6,s7;
#pragma HLS STREAM variable=ir depth=2048
#pragma HLS STREAM variable=ig depth=2048
#pragma HLS STREAM variable=ib depth=2048
#pragma HLS STREAM variable=orr depth=2048
#pragma HLS STREAM variable=og depth=2048
#pragma HLS STREAM variable=ob depth=2048
#pragma HLS STREAM variable=s0 depth=32
#pragma HLS STREAM variable=s1 depth=32
#pragma HLS STREAM variable=s2 depth=32
#pragma HLS STREAM variable=s3 depth=32
#pragma HLS STREAM variable=s4 depth=32
#pragma HLS STREAM variable=s5 depth=32
#pragma HLS STREAM variable=s6 depth=32
#pragma HLS STREAM variable=s7 depth=32
    read_nchw(input,h,w,ir,ig,ib);interleave(ir,ig,ib,s0,h,w);
    spatial<0>(s0,s1,h,w,task);spatial<1>(s1,s2,h,w,task);
    spatial<2>(s2,s3,h,w,task);spatial<3>(s3,s4,h,w,task);
    spatial<4>(s4,s5,h,w,task);spatial<5>(s5,s6,h,w,task);
    tail(s6,s7,h,w,task);deinterleave(s7,orr,og,ob,h,w);write_nchw(output,h,w,orr,og,ob);
}
#ifndef __SYNTHESIS__
int tile_local(const int16_t* input,int16_t* output,int h,int w,int task) {
    if(h<1 || h>140 || w<1 || w>140)return 1;
    if(task<0 || task>1)return 2;
    frame(input,output,h,w,task);return 0;
}
#endif
}
extern "C" int weather_frame_top(const int16_t* input,int16_t* output,int height,int width,int task) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_in depth=2764800 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_out depth=2764800 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=input bundle=CTRL offset=0x18
#pragma HLS INTERFACE s_axilite port=output bundle=CTRL offset=0x24
#pragma HLS INTERFACE s_axilite port=height bundle=CTRL offset=0x30
#pragma HLS INTERFACE s_axilite port=width bundle=CTRL offset=0x38
#pragma HLS INTERFACE s_axilite port=task bundle=CTRL offset=0x40
#pragma HLS INTERFACE s_axilite port=return bundle=CTRL
    if(height<1 || height>720 || width<1 || width>1280)return 1;
    if(task<0 || task>1)return 2;
    weather_b::frame(input,output,height,width,task);return 0;
}
