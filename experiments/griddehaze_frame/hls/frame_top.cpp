#include "frame_top.hpp"
#include "conv_tile_top.hpp"
#include "elementwise_top.hpp"
#include "generated_model.hpp"

namespace {
std::uint32_t aligned(std::uint32_t n) { return (n+63u)&~63u; }
}

extern "C" int griddehaze_frame_top(
    const std::int16_t* input,std::int16_t* output,std::int16_t* scratch,
    const std::int16_t* parameters,const std::uint32_t* layout,
    std::uint32_t input_bytes,std::uint32_t output_bytes,std::uint32_t scratch_bytes,
    std::uint32_t parameter_bytes,std::uint32_t layout_bytes,
    int height,int width,std::uint32_t model_id,std::uint32_t abi,
    std::uint32_t& completed_nodes,std::uint32_t& hardware_model,std::uint32_t& hardware_abi) {
#pragma HLS INTERFACE m_axi port=input bundle=feature_mem depth=2764800 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=output bundle=feature_mem depth=2764800 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE m_axi port=scratch bundle=feature_mem depth=268435456 max_read_burst_length=64 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=parameters bundle=parameter_mem depth=966560 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=layout bundle=parameter_mem depth=336 max_read_burst_length=64
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=scratch bundle=control
#pragma HLS INTERFACE s_axilite port=parameters bundle=control
#pragma HLS INTERFACE s_axilite port=layout bundle=control
#pragma HLS INTERFACE s_axilite port=input_bytes bundle=control
#pragma HLS INTERFACE s_axilite port=output_bytes bundle=control
#pragma HLS INTERFACE s_axilite port=scratch_bytes bundle=control
#pragma HLS INTERFACE s_axilite port=parameter_bytes bundle=control
#pragma HLS INTERFACE s_axilite port=layout_bytes bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=model_id bundle=control
#pragma HLS INTERFACE s_axilite port=abi bundle=control
#pragma HLS INTERFACE s_axilite port=completed_nodes bundle=control
#pragma HLS INTERFACE s_axilite port=hardware_model bundle=control
#pragma HLS INTERFACE s_axilite port=hardware_abi bundle=control
    using namespace gdn_model;
    completed_nodes=0;hardware_model=MODEL_ID;hardware_abi=ABI;
    if(model_id!=MODEL_ID || abi!=ABI || height<4 || height>720 || width<4 || width>1280) return 1;
    const std::uint32_t image_bytes=std::uint32_t(height*width*6);
    if(input_bytes<image_bytes || output_bytes<image_bytes || parameter_bytes!=PARAMETER_BYTES ||
       layout_bytes!=336*4 || scratch_bytes==0 || scratch_bytes>536870912u) return 2;
    if(layout[0]!=0x314c4447u || layout[1]!=1 || layout[2]!=std::uint32_t(height) ||
       layout[3]!=std::uint32_t(width) || layout[4]!=320 || layout[5]!=0 ||
       layout[6]!=scratch_bytes || layout[7]!=0) return 3;
    for(int i=0;i<8;++i) if(layout[8+i]!=bundle[i]) return 3;
    std::uint32_t offsets[NODES],sizes[NODES];
    std::uint16_t heights[NODES],widths[NODES];
#pragma HLS BIND_STORAGE variable=offsets type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=sizes type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=heights type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=widths type=ram_2p impl=bram
    heights[0]=height;widths[0]=width;offsets[0]=0;sizes[0]=image_bytes;
    if(layout[16]!=0 || layout[16+NODES-1]!=0) return 3;
    // First validate the entire address plan. No feature/weight reads or writes
    // occur until all sizes, live tensor overlaps and metadata identity pass.
    for(int i=1;i<NODES;++i) {
        const Node n=graph[i];
        int h=heights[n.a],w=widths[n.a];
        if(n.op==1 && n.stride==2) { h=(h+1)/2;w=(w+1)/2; }
        if(n.op==2) { h=heights[n.like];w=widths[n.like]; }
        heights[i]=h;widths[i]=w;
        const std::uint32_t bytes=std::uint32_t(n.channels)*h*w*2u;
        sizes[i]=bytes;
        const std::uint32_t at=layout[16+i];offsets[i]=at;
        if(i!=NODES-1) {
            if((at&63u)!=0 || aligned(bytes)>scratch_bytes || at>scratch_bytes-aligned(bytes)) return 4;
            for(int j=1;j<i;++j) if(graph[j].last_use>=i) {
                if(at<offsets[j]+aligned(sizes[j]) && offsets[j]<at+aligned(bytes)) return 5;
            }
        }
    }
#ifndef __SYNTHESIS__
    gdn_frame_observe(0,input,image_bytes/2);
#endif
    completed_nodes=1;
    for(int i=1;i<NODES;++i) {
        const Node n=graph[i],a=graph[n.a],b=graph[n.b];
        const auto* x=n.a==0?input:scratch+offsets[n.a]/2;
        const auto* y=n.b==0?input:scratch+offsets[n.b]/2;
        auto* dst=i==NODES-1?output:scratch+offsets[i]/2;
        int status=0;
        if(n.op==1 || n.op==2) {
            std::int64_t biases[64];std::int8_t scale_shifts[64];
            for(int c=0;c<n.channels;++c) {
                const int at=n.bias+4*c;
                std::uint64_t raw=0;
                for(int k=0;k<4;++k) raw|=std::uint64_t(std::uint16_t(parameters[at+k]))<<(16*k);
                // Decode two's complement without an out-of-range unsigned to
                // signed cast, which is implementation-defined in C++11.
                const std::int64_t value=(raw&(std::uint64_t(1)<<63)) ?
                    -1-static_cast<std::int64_t>(~raw) : static_cast<std::int64_t>(raw);
                // This also protects 48-bit accumulators from corrupted INT64
                // biases. Software must still authenticate the parameter blob.
                if(value<-(std::int64_t(1)<<43) || value>=(std::int64_t(1)<<43)) return 6;
                biases[c]=value;scale_shifts[c]=shifts[n.shift+c];
            }
            for(int co=0;co<n.channels;co+=8) for(int yy=0;yy<heights[i];yy+=16) for(int xx=0;xx<widths[i];xx+=16) {
                status=griddehaze_conv_tile_top(x,parameters+n.weight,biases,scale_shifts,dst,
                    a.channels,n.channels,heights[n.a],widths[n.a],heights[i],widths[i],
                    n.kernel,n.stride,n.padding,n.op==2,yy,xx,co);
                if(status) return 16+status;
            }
        } else {
            const bool binary=n.op==5 || n.op==6;
            status=griddehaze_elementwise_top(x,y,parameters+n.coefficient,dst,
                sizes[n.a]/2,binary?sizes[n.b]/2:0,n.op==4?n.channels:0,sizes[i]/2,
                n.op-2,a.channels,binary?b.channels:0,n.channels,heights[i],widths[i],a.frac,b.frac,n.frac);
            if(status) return 32+status;
        }
        completed_nodes=i+1;
#ifndef __SYNTHESIS__
        gdn_frame_observe(i,dst,sizes[i]/2);
#endif
    }
    return 0;
}
