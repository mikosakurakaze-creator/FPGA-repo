#include "compact_d.hpp"
#include "generated_parameters.hpp"
#include <ap_int.h>
#include <hls_stream.h>

namespace compact_d {
template<int C> using Pixel = ap_uint<16*C>;
template<int C> using Stream = hls::stream<Pixel<C> >;

static const int MAX_W = 1280;
static const uint32_t ABI_COOKIE = 0x44433031U;

#ifndef __SYNTHESIS__
static Trace trace_callback = 0;
static void* trace_user = 0;
void set_trace(Trace callback, void* user) {
    trace_callback = callback;
    trace_user = user;
}
#endif
static void trace(int node, int c, int y, int x, int16_t value) {
#pragma HLS INLINE
#ifndef __SYNTHESIS__
    if (trace_callback) trace_callback(node, c, y, x, value, trace_user);
#else
    (void)node; (void)c; (void)y; (void)x; (void)value;
#endif
}
template<int C> static ap_int<16> lane(const Pixel<C>& p, int c) {
#pragma HLS INLINE
    ap_int<16> v;
    v.range(15,0) = p.range(16*c+15,16*c);
    return v;
}
template<int C> static void put(Pixel<C>& p, int c, ap_int<16> value) {
#pragma HLS INLINE
    p.range(16*c+15,16*c) = value.range(15,0);
}
static ap_int<16> sat16(ap_int<38> value) {
#pragma HLS INLINE
    return value < -32768 ? ap_int<16>(-32768) :
           value > 32767 ? ap_int<16>(32767) : ap_int<16>(value);
}
static ap_int<16> quantize(ap_int<37> value, int shift) {
#pragma HLS INLINE
    // Widen before negation and half-step addition. A certifies the 37-bit MAC.
    const ap_int<38> wide = value;
    const ap_uint<38> magnitude = wide < 0 ? ap_uint<38>(-wide) : ap_uint<38>(wide);
    const ap_uint<38> rounded = (magnitude + (ap_uint<38>(1) << (shift-1))) >> shift;
    ap_int<38> signed_result;
    if (wide < 0) {
        signed_result = ap_int<38>(-ap_int<39>(rounded));
    } else {
        signed_result = ap_int<38>(rounded);
    }
    return sat16(signed_result);
}

static void read_plane(const int16_t* input, int offset, int w, hls::stream<int16_t>& out) {
#pragma HLS INLINE off
READ_PLANE:
    for (int x=0; x<w; ++x) {
#pragma HLS PIPELINE II=1
        out.write(input[offset+x]);
    }
}
static void read_nchw(const int16_t* input, int h, int w,
                      hls::stream<int16_t>& r, hls::stream<int16_t>& g,
                      hls::stream<int16_t>& b, hls::stream<ap_uint<1> >& done) {
#pragma HLS INLINE off
    for (int y=0; y<h; ++y) {
#pragma HLS LOOP_FLATTEN off
        read_plane(input,y*w,w,r);
        read_plane(input,(h+y)*w,w,g);
        read_plane(input,(2*h+y)*w,w,b);
    }
    done.write(1);
}
static void pack_input(hls::stream<int16_t>& r, hls::stream<int16_t>& g,
                       hls::stream<int16_t>& b, Stream<3>& features,
                       Stream<3>& base, int h, int w) {
#pragma HLS INLINE off
    for (int i=0; i<h*w; ++i) {
#pragma HLS PIPELINE II=1
        const int16_t values[3] = {r.read(),g.read(),b.read()};
#pragma HLS ARRAY_PARTITION variable=values complete
        Pixel<3> p=0, q=0;
        for (int c=0; c<3; ++c) {
#pragma HLS UNROLL
            const ap_int<18> shifted = ap_int<18>(values[c]) + 16384;
            // Legal qin is [-16384,16384], so affine numerator is nonnegative.
            const ap_int<16> affine = ap_int<16>((shifted+1) >> 1);
            put<3>(p,c,values[c]); put<3>(q,c,affine);
            trace(0,c,i/w,i%w,values[c]); trace(19,c,i/w,i%w,affine);
        }
        features.write(p); base.write(q);
    }
}

template<int L, int CIN, int COUT>
static void convolution(Stream<CIN>& input, Stream<COUT>& output, int h, int w) {
#pragma HLS INLINE off
    const int GROUPS = (CIN+3)/4;
    const int PHASES = GROUPS*3;
    static Pixel<CIN> rows[2][MAX_W+2];
    Pixel<CIN> window[3][3] = {};
    ap_int<37> accum[COUT];
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS BIND_STORAGE variable=rows type=ram_2p impl=uram
#pragma HLS DEPENDENCE variable=rows inter false
#pragma HLS ARRAY_PARTITION variable=window complete dim=0
#pragma HLS ARRAY_PARTITION variable=accum complete
    int phase=0, y=0, x=0;
    const int steps=(h+2)*(w+2)*PHASES;
CONV_PHASE:
    for (int step=0; step<steps; ++step) {
#pragma HLS PIPELINE II=1
        if (phase==0) {
            Pixel<CIN> p=0;
            if (y>0 && y<=h && x>0 && x<=w) p=input.read();
            const Pixel<CIN> top=rows[0][x], middle=rows[1][x];
            rows[0][x]=middle; rows[1][x]=p;
            for (int r=0; r<3; ++r) {
#pragma HLS UNROLL
                window[r][0]=window[r][1]; window[r][1]=window[r][2];
            }
            window[0][2]=top; window[1][2]=middle; window[2][2]=p;
        }
        Pixel<COUT> result=0;
        const int ky=phase/GROUPS, first_ci=(phase%GROUPS)*4;
        for (int co=0; co<COUT; ++co) {
#pragma HLS UNROLL
            ap_int<37> terms[16];
#pragma HLS ARRAY_PARTITION variable=terms complete
            for (int j=0; j<16; ++j) {
#pragma HLS UNROLL
                ap_int<32> product=0;
#pragma HLS BIND_OP variable=product op=mul impl=dsp latency=2
                const int ci=first_ci+j/3, kx=j%3;
                if (j<12 && ci<CIN) {
                    const ap_int<16> a=lane<CIN>(window[ky][kx],ci);
                    const ap_int<16> b=Layer<L>::weight(co,ci,ky,kx);
                    product=a*b;
                }
                terms[j]=product;
            }
            for (int stride=1; stride<16; stride*=2) {
#pragma HLS UNROLL
                for (int j=0; j<16; j+=2*stride) {
#pragma HLS UNROLL
                    terms[j]=terms[j]+terms[j+stride];
                }
            }
            const ap_int<37> previous = phase==0 ? ap_int<37>(Layer<L>::bias(co)) : accum[co];
            const ap_int<37> value=previous+terms[0];
            accum[co]=value;
            if (phase==PHASES-1 && y>=2 && x>=2) {
                const ap_int<16> q=quantize(value,Layer<L>::shift(co));
                put<COUT>(result,co,q);
                trace(Layer<L>::node,co,y-2,x-2,int16_t(q));
            }
        }
        if (phase==PHASES-1) {
            if (y>=2 && x>=2) output.write(result);
            phase=0;
            if (x==w+1) {x=0; ++y;} else ++x;
        } else ++phase;
    }
}
template<int NODE> static void relu(Stream<8>& input, Stream<8>& output, int h, int w) {
#pragma HLS INLINE off
    for (int i=0; i<h*w; ++i) {
#pragma HLS PIPELINE II=1
        const Pixel<8> p=input.read(); Pixel<8> result=0;
        for (int c=0; c<8; ++c) {
#pragma HLS UNROLL
            const ap_int<16> q=lane<8>(p,c), a=q<0 ? ap_int<16>(0) : q;
            put<8>(result,c,a); trace(NODE,c,i/w,i%w,int16_t(a));
        }
        output.write(result);
    }
}
template<int BLOCK> static void fork(Stream<8>& input, Stream<8>& first,
                                      Stream<8>& skip, int count) {
#pragma HLS INLINE off
    for (int i=0; i<count; ++i) {
#pragma HLS PIPELINE II=1
        const Pixel<8> p=input.read(); first.write(p); skip.write(p);
    }
}
template<int BLOCK> static void add_relu(Stream<8>& input, Stream<8>& skip,
                                         Stream<8>& output, int h, int w) {
#pragma HLS INLINE off
    for (int i=0; i<h*w; ++i) {
#pragma HLS PIPELINE II=1
        const Pixel<8> a=input.read(), b=skip.read(); Pixel<8> result=0;
        for (int c=0; c<8; ++c) {
#pragma HLS UNROLL
            const ap_int<16> sum=sat16(ap_int<38>(lane<8>(a,c))+ap_int<38>(lane<8>(b,c)));
            const ap_int<16> activated=sum<0 ? ap_int<16>(0) : sum;
            put<8>(result,c,activated);
            trace(6+BLOCK*5,c,i/w,i%w,int16_t(sum));
            trace(7+BLOCK*5,c,i/w,i%w,int16_t(activated));
        }
        output.write(result);
    }
}
template<int BLOCK> static void residual_block(Stream<8>& input, Stream<8>& output, int h, int w) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    Stream<8> a("block_input"), b("conv0"), c("relu0"), d("conv1"), skip("skip");
#pragma HLS STREAM variable=a depth=32
#pragma HLS STREAM variable=b depth=32
#pragma HLS STREAM variable=c depth=32
#pragma HLS STREAM variable=d depth=32
#pragma HLS STREAM variable=skip depth=4096
#pragma HLS BIND_STORAGE variable=skip type=fifo impl=uram
    fork<BLOCK>(input,a,skip,h*w);
    convolution<1+2*BLOCK,8,8>(a,b,h,w);
    relu<4+5*BLOCK>(b,c,h,w);
    convolution<2+2*BLOCK,8,8>(c,d,h,w);
    add_relu<BLOCK>(d,skip,output,h,w);
}
static void finish(Stream<3>& correction, Stream<3>& base,
                   hls::stream<int16_t>& r, hls::stream<int16_t>& g,
                   hls::stream<int16_t>& b, int h, int w) {
#pragma HLS INLINE off
    for (int i=0; i<h*w; ++i) {
#pragma HLS PIPELINE II=1
        const Pixel<3> a=correction.read(), original=base.read();
        int16_t values[3];
#pragma HLS ARRAY_PARTITION variable=values complete
        for (int c=0; c<3; ++c) {
#pragma HLS UNROLL
            const ap_int<16> sum=sat16(ap_int<38>(lane<3>(a,c))+ap_int<38>(lane<3>(original,c)));
            const ap_int<16> activated=sum<0 ? ap_int<16>(0) : sum;
            values[c]=int16_t(activated);
            trace(20,c,i/w,i%w,int16_t(sum)); trace(21,c,i/w,i%w,values[c]);
        }
        r.write(values[0]); g.write(values[1]); b.write(values[2]);
    }
}
static void write_plane(int16_t* output, int offset, int w, hls::stream<int16_t>& in) {
#pragma HLS INLINE off
WRITE_PLANE:
    for (int x=0; x<w; ++x) {
#pragma HLS PIPELINE II=1
        output[offset+x]=in.read();
    }
}
static void write_nchw(int16_t* output, int h, int w,
                       hls::stream<int16_t>& r, hls::stream<int16_t>& g,
                       hls::stream<int16_t>& b, hls::stream<ap_uint<1> >& done) {
#pragma HLS INLINE off
    for (int y=0; y<h; ++y) {
#pragma HLS LOOP_FLATTEN off
        write_plane(output,y*w,w,r);
        write_plane(output,(h+y)*w,w,g);
        write_plane(output,(2*h+y)*w,w,b);
    }
    done.write(1);
}
static void monitor(hls::stream<ap_uint<1> >& read_done,
                    hls::stream<ap_uint<1> >& write_done,
                    uint64_t& work_cycles, uint64_t& input_cycles) {
#pragma HLS INLINE off
    uint64_t ticks=0, read_ticks=0;
    bool seen_read=false, seen_write=false;
    while (!seen_write) {
#pragma HLS PIPELINE II=1
        ap_uint<1> v;
        if (!seen_read && read_done.read_nb(v)) {seen_read=true; read_ticks=ticks;}
        if (write_done.read_nb(v)) seen_write=true;
        ++ticks;
    }
    // DATAFLOW work interval; final AXI response draining may finish later.
    // External start-to-ap_done measurement is the end-to-end core latency.
    work_cycles=ticks; input_cycles=read_ticks;
}
static void frame(const int16_t* input, int16_t* output, int h, int w,
                  uint64_t& work_cycles, uint64_t& input_cycles) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<int16_t> ir("ir"),ig("ig"),ib("ib"),orr("orr"),og("og"),ob("ob");
    Stream<3> rgb("rgb"),base("base"),head("head");
    Stream<8> stem("stem"),s0("s0"),s1("s1"),s2("s2"),s3("s3");
    hls::stream<ap_uint<1> > read_done("read_done"),write_done("write_done");
#pragma HLS STREAM variable=ir depth=2048
#pragma HLS STREAM variable=ig depth=2048
#pragma HLS STREAM variable=ib depth=2048
#pragma HLS STREAM variable=orr depth=2048
#pragma HLS STREAM variable=og depth=2048
#pragma HLS STREAM variable=ob depth=2048
#pragma HLS STREAM variable=rgb depth=32
#pragma HLS STREAM variable=base depth=16384
#pragma HLS BIND_STORAGE variable=base type=fifo impl=uram
#pragma HLS STREAM variable=head depth=32
#pragma HLS STREAM variable=stem depth=32
#pragma HLS STREAM variable=s0 depth=32
#pragma HLS STREAM variable=s1 depth=32
#pragma HLS STREAM variable=s2 depth=32
#pragma HLS STREAM variable=s3 depth=32
#pragma HLS STREAM variable=read_done depth=2
#pragma HLS STREAM variable=write_done depth=2
    read_nchw(input,h,w,ir,ig,ib,read_done);
    pack_input(ir,ig,ib,rgb,base,h,w);
    convolution<0,3,8>(rgb,stem,h,w);
    relu<2>(stem,s0,h,w);
    residual_block<0>(s0,s1,h,w);
    residual_block<1>(s1,s2,h,w);
    residual_block<2>(s2,s3,h,w);
    convolution<7,8,3>(s3,head,h,w);
    finish(head,base,orr,og,ob,h,w);
    write_nchw(output,h,w,orr,og,ob,write_done);
    monitor(read_done,write_done,work_cycles,input_cycles);
}
} // namespace compact_d

extern "C" int compact_d_top(const int16_t* input, int16_t* output,
                            int height, int width, uint32_t abi_cookie,
                            uint64_t& work_cycles, uint64_t& input_cycles) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_in depth=2764800 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem_out depth=2764800 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=input bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=output bundle=control offset=0x24
#pragma HLS INTERFACE s_axilite port=height bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=width bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=abi_cookie bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=work_cycles bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=input_cycles bundle=control offset=0x58
#pragma HLS INTERFACE s_axilite port=return bundle=control
    work_cycles=0; input_cycles=0;
    if (abi_cookie!=compact_d::ABI_COOKIE) return -1;
    if (height<1 || height>720 || width<1 || width>1280) return -2;
    compact_d::frame(input,output,height,width,work_cycles,input_cycles);
    return 0;
}
