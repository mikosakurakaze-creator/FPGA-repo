// One lock publishes one band/tile. No whole-function shared-array PIPO.
using rowstream_io::row_word;
using rowstream_io::take;
typedef ap_uint<128> lane_word; // four channels x two INT16 scalars
typedef ap_uint<1> ownership_token;
typedef lane_word source_strip_t[16][10][53];
typedef lane_word source_tile_t[16][10][9];
typedef lane_word output_tile_t[8][8][8];
typedef lane_word output_strip_t[8][8][53];
#ifndef __SYNTHESIS__
// Shipped SOB C++ emulator queues on write_acquire, not write_release.
// C-only publication notifications prevent reading an unfinished host block.
#define CSIM_PUB_PARAMS(name) , hls::stream<ownership_token> &name
#define CSIM_WAIT(name) take(name)
#define CSIM_NOTIFY(name) name.write(1)
#else
#define CSIM_PUB_PARAMS(name)
#define CSIM_WAIT(name)
#define CSIM_NOTIFY(name)
#endif
// Band metadata only; DW/PW scalar tile maxima remain 8 output rows.
static const int kRowBandHeight=4;
static const int kRowBandCount=15;
static const int kRowTileCount=105;
static int band_height(int band) {
#pragma HLS INLINE
    return kRowBandHeight;
}
static int fresh_rows(int band) {
#pragma HLS INLINE
    return band==0?kRowBandHeight+1:(band==kRowBandCount-1?kRowBandHeight-1:kRowBandHeight);
}
static void source_reader(const zero_dce_q16_t *input,const zero_dce_q16_t *workspace,
    int block,int channels,hls::stream<zero_dce_q16_t> &raw) {
#pragma HLS INLINE off
    const int left=block==5?2:(block==6?1:0),right=block==5?3:(block==6?4:5);
    for(int band=0;band<kRowBandCount;++band) for(int c=0;c<channels;++c) {
        const int sc=block>=5&&c>=32?c-32:c;
        const int slot=block>=5?(c>=32?right:left):block-2;
        const int base=block==1?sc*6360:slot*203520+sc*6360;
        const int first=band==0?0:band*kRowBandHeight+1;
        for(int r=0;r<fresh_rows(band);++r) {
            if(block==1) rowstream_io::row_axi_reader(input,base+(first+r)*106,raw);
            else rowstream_io::row_axi_reader(workspace,base+(first+r)*106,raw);
        }
    }
}
static void unpack_one_row(hls::stream<zero_dce_q16_t> &raw,source_strip_t &strip,
    int c,int r,int old_frac,int new_frac) {
#pragma HLS INLINE off
    row_word pair=0;
    for(int x=0;x<106;++x) {
#pragma HLS PIPELINE II=1
        const zero_dce_q16_t value=rescale_q16(take(raw),old_frac,new_frac);
        if((x&1)==0) pair.range(15,0)=value.range(15,0);
        else {
            pair.range(31,16)=value.range(15,0);
            lane_word packed=c%4==0?lane_word(0):strip[c/4][r][x/2];
            packed.range(32*(c%4)+31,32*(c%4))=pair;
            strip[c/4][r][x/2]=packed;
        }
    }
}
static void source_unpacker(hls::stream<zero_dce_q16_t> &raw,
    hls::stream_of_blocks<source_strip_t> &strips,int block,int channels,
    int input_frac CSIM_PUB_PARAMS(source_pub)) {
#pragma HLS INLINE off
    lane_word carry[16][2][53];
#pragma HLS BIND_STORAGE variable=carry type=ram_2p impl=uram
    const int groups=(channels+3)/4;
    for(int band=0;band<kRowBandCount;++band) {
        {
            hls::write_lock<source_strip_t> lock(strips);
            source_strip_t &strip=lock;
            for(int g=0;g<groups;++g) for(int w=0;w<53;++w) {
#pragma HLS PIPELINE II=1
                if(band==0) strip[g][0][w]=0;
                else {strip[g][0][w]=carry[g][0][w];strip[g][1][w]=carry[g][1][w];}
                if(band==kRowBandCount-1) strip[g][5][w]=0;
            }
            const int left=block==5?2:(block==6?1:0),right=block==5?3:(block==6?4:5);
            for(int c=0;c<channels;++c) {
                const int slot=block>=5?(c>=32?right:left):block-2;
                const int old_frac=block==1?14:kSkipFrac[slot];
                for(int r=0;r<fresh_rows(band);++r)
                    unpack_one_row(raw,strip,c,r+(band==0?1:2),old_frac,input_frac);
            }
            // Only two halo rows are retained independently of the SOB bank.
            if(band<kRowBandCount-1) for(int g=0;g<groups;++g) for(int r=0;r<2;++r)
                for(int w=0;w<53;++w) {
#pragma HLS PIPELINE II=1
                    carry[g][r][w]=strip[g][r+kRowBandHeight][w];
                }
        }
        CSIM_NOTIFY(source_pub);
    }
}
static void feed_tile(const source_strip_t &strip,source_tile_t &tile,
    int channels,int height,int tile_column) {
#pragma HLS INLINE off
    for(int g=0;g<(channels+3)/4;++g) for(int r=0;r<height+2;++r) {
        lane_word previous=tile_column>0?strip[g][r][tile_column/2-1]:lane_word(0);
        const int width=tile_column==96?10:16;
        for(int pair=0;pair<(width+2)/2;++pair) {
#pragma HLS PIPELINE II=1
            const int index=tile_column/2+pair;
            const lane_word current=index<53?strip[g][r][index]:lane_word(0);
            lane_word word=0;
            for(int lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                word.range(32*lane+15,32*lane)=previous.range(32*lane+31,32*lane+16);
                word.range(32*lane+31,32*lane+16)=current.range(32*lane+15,32*lane);
            }
            tile[g][r][pair]=word;previous=current;
        }
    }
}
static void tile_feeder(hls::stream_of_blocks<source_strip_t> &strips,
    hls::stream_of_blocks<source_tile_t> &tiles,int channels
    CSIM_PUB_PARAMS(source_pub) CSIM_PUB_PARAMS(tile_pub)) {
#pragma HLS INLINE off
    for(int band=0;band<kRowBandCount;++band) {
        CSIM_WAIT(source_pub);
        hls::read_lock<source_strip_t> source(strips);
        for(int x=0;x<7;++x) {
            {hls::write_lock<source_tile_t> tile(tiles);
             feed_tile(source,tile,channels,band_height(band),16*x);}
            CSIM_NOTIFY(tile_pub);
        }
    }
}
static void unpack_source_tile(const source_tile_t &packed,
    zero_dce_q16_t tile[64][10][18],int channels,int height,int width) {
#pragma HLS INLINE off
    for(int g=0;g<(channels+3)/4;++g) for(int r=0;r<height+2;++r)
        for(int pair=0;pair<(width+2)/2;++pair) {
#pragma HLS PIPELINE II=1
            const lane_word word=packed[g][r][pair];
            for(int lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                if(4*g+lane<channels) {
                    tile[4*g+lane][r][2*pair].range(15,0)=word.range(32*lane+15,32*lane);
                    tile[4*g+lane][r][2*pair+1].range(15,0)=word.range(32*lane+31,32*lane+16);
                }
            }
        }
}
static void pack_output_tile(const zero_dce_q16_t tile[32][8][16],
    output_tile_t &packed,int channels,int height,int width) {
#pragma HLS INLINE off
    for(int g=0;g<(channels+3)/4;++g) for(int r=0;r<height;++r)
        for(int pair=0;pair<width/2;++pair) {
#pragma HLS PIPELINE II=1
            lane_word word=0;
            for(int lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                if(4*g+lane<channels) {
                    word.range(32*lane+15,32*lane)=tile[4*g+lane][r][2*pair].range(15,0);
                    word.range(32*lane+31,32*lane+16)=tile[4*g+lane][r][2*pair+1].range(15,0);
                }
            }
            packed[g][r][pair]=word;
        }
}
static void compute_actor(hls::stream_of_blocks<source_tile_t> &sources,
    hls::stream_of_blocks<output_tile_t> &outputs,
    const zero_dce_q8_t weights[ZERO_DCE_WEIGHT_ELEMENTS],
    const zero_dce_q8_t point_banks[4][8][kPointBankDepth],
    const zero_dce_q32_t bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_q16_t lut[4][ZERO_DCE_TANH_LUT_ELEMENTS],int block
    CSIM_PUB_PARAMS(tile_pub) CSIM_PUB_PARAMS(output_pub)) {
#pragma HLS INLINE off
#pragma HLS ALLOCATION function instances=compute_depth_tile limit=1
#pragma HLS ALLOCATION function instances=compute_point_tile limit=1
    zero_dce_q16_t source[64][10][18],middle[64][8][16],output[32][8][16];
#pragma HLS BIND_STORAGE variable=source type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=source cyclic factor=4 dim=1
#pragma HLS ARRAY_PARTITION variable=source cyclic factor=3 dim=2
#pragma HLS ARRAY_PARTITION variable=source cyclic factor=3 dim=3
#pragma HLS BIND_STORAGE variable=middle type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=middle cyclic factor=8 dim=1
#pragma HLS BIND_STORAGE variable=output type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=output cyclic factor=4 dim=1
#pragma HLS ARRAY_PARTITION variable=output cyclic factor=2 dim=3
    const zero_dce_layer_spec_t &depth=kZeroDceLayers[2*(block-1)];
    const zero_dce_layer_spec_t &point=kZeroDceLayers[2*(block-1)+1];
    for(int t=0;t<kRowTileCount;++t) {
        const int height=band_height(t/7),width=t%7==6?10:16;
        CSIM_WAIT(tile_pub);
        {hls::read_lock<source_tile_t> lock(sources);
         unpack_source_tile(lock,source,depth.input_channels,height,width);}
        compute_depth_tile(source,middle,weights,bias,frac,depth,point,height,width);
        compute_point_tile(middle,output,point_banks,bias,frac,lut,point,block,height,width);
        {hls::write_lock<output_tile_t> lock(outputs);
         pack_output_tile(output,lock,point.output_channels,height,width);}
        CSIM_NOTIFY(output_pub);
    }
}
static void assemble_tile(const output_tile_t &tile,output_strip_t &strip,
    int channels,int height,int tile_column) {
#pragma HLS INLINE off
    for(int g=0;g<(channels+3)/4;++g) for(int r=0;r<height;++r)
        for(int w=0;w<(tile_column==96?5:8);++w) {
#pragma HLS PIPELINE II=1
            strip[g][r][tile_column/2+w]=tile[g][r][w];
        }
}
static void output_assembler(hls::stream_of_blocks<output_tile_t> &tiles,
    hls::stream_of_blocks<output_strip_t> &strips,int channels
    CSIM_PUB_PARAMS(output_pub) CSIM_PUB_PARAMS(store_pub)) {
#pragma HLS INLINE off
    for(int band=0;band<kRowBandCount;++band) {
        {hls::write_lock<output_strip_t> strip(strips);
         for(int x=0;x<7;++x) {
            CSIM_WAIT(output_pub);
            hls::read_lock<output_tile_t> tile(tiles);
            assemble_tile(tile,strip,channels,band_height(band),16*x);
         }}
        CSIM_NOTIFY(store_pub);
    }
}
static void output_packer(hls::stream_of_blocks<output_strip_t> &strips,
    int channels,hls::stream<zero_dce_q16_t> &values CSIM_PUB_PARAMS(store_pub)) {
#pragma HLS INLINE off
    for(int band=0;band<kRowBandCount;++band) {
        CSIM_WAIT(store_pub);
        hls::read_lock<output_strip_t> strip(strips);
        for(int c=0;c<channels;++c) for(int r=0;r<band_height(band);++r) {
            lane_word word=0;
            for(int x=0;x<106;++x) {
#pragma HLS PIPELINE II=1
                if((x&1)==0) word=strip[c/4][r][x/2];
                zero_dce_q16_t value;
                value.range(15,0)=word.range(32*(c%4)+16*(x%2)+15,32*(c%4)+16*(x%2));
                values.write(value);
            }
        }
    }
}
static void output_writer(zero_dce_q16_t *output,zero_dce_q16_t *workspace,
    int block,int channels,hls::stream<zero_dce_q16_t> &values) {
#pragma HLS INLINE off
    const int slot_base=block==7?0:(block-1)*203520;
    for(int band=0;band<kRowBandCount;++band) for(int c=0;c<channels;++c)
        for(int r=0;r<band_height(band);++r) {
            const int address=slot_base+c*6360+(band*kRowBandHeight+r)*106;
            if(block==7) rowstream_io::row_axi_writer(output,address,values);
            else rowstream_io::row_axi_writer(workspace,address,values);
        }
}
static void rowstream_block(const zero_dce_q16_t *input,zero_dce_q16_t *workspace,
    zero_dce_q16_t *output,const zero_dce_q8_t weights[ZERO_DCE_WEIGHT_ELEMENTS],
    const zero_dce_q8_t point_banks[4][8][kPointBankDepth],
    const zero_dce_q32_t bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_q16_t lut[4][ZERO_DCE_TANH_LUT_ELEMENTS],int block) {
#pragma HLS INLINE off
    hls::stream_of_blocks<source_strip_t> source_strips;
    hls::stream_of_blocks<source_tile_t> source_tiles;
    hls::stream_of_blocks<output_tile_t> output_tiles;
    hls::stream_of_blocks<output_strip_t> output_strips;
#pragma HLS BIND_STORAGE variable=source_strips type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=source_tiles type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=output_tiles type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=output_strips type=ram_2p impl=uram
    hls::stream<zero_dce_q16_t> raw("raw"),result("result");
#pragma HLS STREAM variable=raw depth=256
#pragma HLS STREAM variable=result depth=256
    const int ci=kZeroDceLayers[2*(block-1)].input_channels;
    const int co=kZeroDceLayers[2*(block-1)+1].output_channels;
    const int input_frac=kZeroDceLayers[2*(block-1)].input_frac;
#ifndef __SYNTHESIS__
    hls::stream<ownership_token> source_pub,tile_pub,output_pub,store_pub;
    std::thread reader([&]{source_reader(input,workspace,block,ci,raw);});
    std::thread unpacker([&]{source_unpacker(raw,source_strips,block,ci,input_frac,source_pub);});
    std::thread feeder([&]{tile_feeder(source_strips,source_tiles,ci,source_pub,tile_pub);});
    std::thread computer([&]{compute_actor(source_tiles,output_tiles,weights,point_banks,bias,frac,lut,block,tile_pub,output_pub);});
    std::thread assembler([&]{output_assembler(output_tiles,output_strips,co,output_pub,store_pub);});
    std::thread packer([&]{output_packer(output_strips,co,result,store_pub);});
    std::thread writer([&]{output_writer(output,workspace,block,co,result);});
    reader.join();unpacker.join();feeder.join();computer.join();assembler.join();packer.join();writer.join();
#else
#pragma HLS DATAFLOW
    source_reader(input,workspace,block,ci,raw);
    source_unpacker(raw,source_strips,block,ci,input_frac);
    tile_feeder(source_strips,source_tiles,ci);
    compute_actor(source_tiles,output_tiles,weights,point_banks,bias,frac,lut,block);
    output_assembler(output_tiles,output_strips,co);
    output_packer(output_strips,co,result);
    output_writer(output,workspace,block,co,result);
#endif
}

