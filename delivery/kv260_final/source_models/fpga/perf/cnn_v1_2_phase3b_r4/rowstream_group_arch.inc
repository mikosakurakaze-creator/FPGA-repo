// Group-strip architecture: DW consumes each four-channel strip as soon as
// it is ready. PW independently consumes a complete eight-output-row band.
// R3 separates scalar tile unpack, PW, and output packing into independently
// owned SOB stages. Original DW/PW functions and MAC counts are unchanged.
typedef lane_word group_strip_t[10][53];
typedef lane_word middle_band_t[8][8][106]; // eight channels per 128-bit word
typedef zero_dce_q16_t point_input_tile_t[64][8][16];
typedef zero_dce_q16_t point_result_tile_t[32][8][16];
static void unpack_group_row(hls::stream<zero_dce_q16_t> &raw,
    group_strip_t &strip,int lane,int r,int old_frac,int new_frac) {
#pragma HLS INLINE off
    row_word pair=0;
    for(int x=0;x<106;++x) {
#pragma HLS PIPELINE II=1
        const zero_dce_q16_t value=rescale_q16(take(raw),old_frac,new_frac);
        if((x&1)==0) pair.range(15,0)=value.range(15,0);
        else {
            pair.range(31,16)=value.range(15,0);
            lane_word packed=lane==0?lane_word(0):strip[r][x/2];
            packed.range(32*lane+31,32*lane)=pair;
            strip[r][x/2]=packed;
        }
    }
}
static void group_unpacker(hls::stream<zero_dce_q16_t> &raw,
    hls::stream_of_blocks<group_strip_t> &groups,int block,int channels,
    int input_frac CSIM_PUB_PARAMS(group_pub)) {
#pragma HLS INLINE off
    lane_word carry[16][2][53];
#pragma HLS BIND_STORAGE variable=carry type=ram_2p impl=uram
    for(int band=0;band<kRowBandCount;++band) for(int g=0;g<(channels+3)/4;++g) {
        {
            hls::write_lock<group_strip_t> lock(groups);
            group_strip_t &strip=lock;
            // One destination write per clock, avoiding the old two-write II=3.
            for(int r=0;r<(band==0?1:2);++r) for(int w=0;w<53;++w) {
#pragma HLS PIPELINE II=1
                strip[r][w]=band==0?lane_word(0):carry[g][r][w];
            }
            if(band==kRowBandCount-1) for(int w=0;w<53;++w) {
#pragma HLS PIPELINE II=1
                strip[5][w]=0;
            }
            for(int lane=0;lane<4;++lane) {
                const int c=4*g+lane;
                if(c<channels) {
                    const int left=block==5?2:(block==6?1:0);
                    const int right=block==5?3:(block==6?4:5);
                    const int slot=block>=5?(c>=32?right:left):block-2;
                    const int old_frac=block==1?14:kSkipFrac[slot];
                    for(int r=0;r<fresh_rows(band);++r)
                        unpack_group_row(raw,strip,lane,r+(band==0?1:2),old_frac,input_frac);
                }
            }
            if(band<kRowBandCount-1) for(int r=0;r<2;++r) for(int w=0;w<53;++w) {
#pragma HLS PIPELINE II=1
                carry[g][r][w]=strip[r+kRowBandHeight][w];
            }
        }
        CSIM_NOTIFY(group_pub);
    }
}
static void load_group_tile(const group_strip_t &strip,
    zero_dce_q16_t tile[4][10][18],int height,int tile_column) {
#pragma HLS INLINE off
    const int width=tile_column==96?10:16;
    for(int r=0;r<height+2;++r) {
        lane_word previous=tile_column>0?strip[r][tile_column/2-1]:lane_word(0);
        for(int pair=0;pair<(width+2)/2;++pair) {
#pragma HLS PIPELINE II=1
            const int index=tile_column/2+pair;
            const lane_word current=index<53?strip[r][index]:lane_word(0);
            for(int lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                tile[lane][r][2*pair].range(15,0)=previous.range(32*lane+31,32*lane+16);
                tile[lane][r][2*pair+1].range(15,0)=current.range(32*lane+15,32*lane);
            }
            previous=current;
        }
    }
}
static void store_middle_group(const zero_dce_q16_t tile[4][8][16],
    middle_band_t &middle,int channel_base,int channels,int height,int column,int width) {
#pragma HLS INLINE off
    for(int r=0;r<height;++r) for(int x=0;x<width;++x) {
#pragma HLS PIPELINE II=1
        lane_word word=channel_base%8==0?lane_word(0):middle[channel_base/8][r][column+x];
        for(int lane=0;lane<4;++lane) {
#pragma HLS UNROLL
            if(lane<channels)
                word.range(16*(channel_base%8+lane)+15,16*(channel_base%8+lane))=tile[lane][r][x].range(15,0);
        }
        middle[channel_base/8][r][column+x]=word;
    }
}
static void depth_band_actor(hls::stream_of_blocks<group_strip_t> &groups,
    hls::stream_of_blocks<middle_band_t> &bands,
    const zero_dce_q8_t weights[ZERO_DCE_WEIGHT_ELEMENTS],
    const zero_dce_q32_t bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],int block
    CSIM_PUB_PARAMS(group_pub) CSIM_PUB_PARAMS(middle_pub)) {
#pragma HLS INLINE off
#pragma HLS ALLOCATION function instances=compute_depth_tile limit=1
    zero_dce_q16_t source[4][10][18],middle[4][8][16];
#pragma HLS BIND_STORAGE variable=source type=ram_2p impl=lutram
#pragma HLS ARRAY_PARTITION variable=source complete dim=1
#pragma HLS ARRAY_PARTITION variable=source cyclic factor=3 dim=2
#pragma HLS ARRAY_PARTITION variable=source cyclic factor=3 dim=3
#pragma HLS BIND_STORAGE variable=middle type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=middle complete dim=1
    const zero_dce_layer_spec_t &original=kZeroDceLayers[2*(block-1)];
    const zero_dce_layer_spec_t &point=kZeroDceLayers[2*(block-1)+1];
    for(int band=0;band<kRowBandCount;++band) {
        {
            hls::write_lock<middle_band_t> output(bands);
            for(int g=0;g<(original.input_channels+3)/4;++g) {
                CSIM_WAIT(group_pub);
                hls::read_lock<group_strip_t> input(groups);
                const int base=4*g;
                const int lanes=original.input_channels-base<4?original.input_channels-base:4;
                zero_dce_layer_spec_t depth=original;
                // Slice the same depthwise kernel/bias/frac arrays. Each global
                // channel appears exactly once with its original arithmetic.
                depth.input_channels=lanes;depth.output_channels=lanes;depth.groups=lanes;
                depth.weight_offset+=9*base;
                depth.bias_offset+=base;depth.weight_frac_offset+=base;
                for(int tx=0;tx<7;++tx) {
                    const int height=band_height(band),width=tx==6?10:16;
                    load_group_tile(input,source,height,16*tx);
                    compute_depth_tile(source,middle,weights,bias,frac,depth,point,height,width);
                    store_middle_group(middle,output,base,lanes,height,16*tx,width);
                }
            }
        }
        CSIM_NOTIFY(middle_pub);
    }
}
static void unpack_middle_tile(const middle_band_t &band,
    zero_dce_q16_t tile[64][8][16],int channels,int height,int column,int width) {
#pragma HLS INLINE off
    for(int g=0;g<(channels+7)/8;++g) for(int r=0;r<height;++r)
        for(int x=0;x<width;++x) {
#pragma HLS PIPELINE II=1
            const lane_word word=band[g][r][column+x];
            for(int lane=0;lane<8;++lane) {
#pragma HLS UNROLL
                if(8*g+lane<channels)
                    tile[8*g+lane][r][x].range(15,0)=word.range(16*lane+15,16*lane);
            }
        }
}
static void point_tile_feed_actor(hls::stream_of_blocks<middle_band_t> &bands,
    hls::stream_of_blocks<point_input_tile_t> &tiles,int block
    CSIM_PUB_PARAMS(middle_pub) CSIM_PUB_PARAMS(point_input_pub)) {
#pragma HLS INLINE off
    const zero_dce_layer_spec_t &point=kZeroDceLayers[2*(block-1)+1];
    for(int band=0;band<kRowBandCount;++band) {
        CSIM_WAIT(middle_pub);
        hls::read_lock<middle_band_t> input(bands);
        for(int tx=0;tx<7;++tx) {
            const int height=band_height(band),width=tx==6?10:16;
            {hls::write_lock<point_input_tile_t> tile(tiles);
             unpack_middle_tile(input,tile,point.input_channels,height,16*tx,width);}
            CSIM_NOTIFY(point_input_pub);
        }
    }
}
static void point_tile_compute_actor(hls::stream_of_blocks<point_input_tile_t> &inputs,
    hls::stream_of_blocks<point_result_tile_t> &outputs,
    const zero_dce_q8_t point_banks[4][8][kPointBankDepth],
    const zero_dce_q32_t bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_q16_t lut[4][ZERO_DCE_TANH_LUT_ELEMENTS],int block
    CSIM_PUB_PARAMS(point_input_pub) CSIM_PUB_PARAMS(point_result_pub)) {
#pragma HLS INLINE off
#pragma HLS ALLOCATION function instances=compute_point_tile limit=1
    const zero_dce_layer_spec_t &point=kZeroDceLayers[2*(block-1)+1];
    for(int tile=0;tile<kRowTileCount;++tile) {
        const int height=band_height(tile/7),width=tile%7==6?10:16;
        CSIM_WAIT(point_input_pub);
        {
            hls::read_lock<point_input_tile_t> input(inputs);
            hls::write_lock<point_result_tile_t> output(outputs);
            compute_point_tile(input,output,point_banks,bias,frac,lut,point,block,height,width);
        }
        CSIM_NOTIFY(point_result_pub);
    }
}
static void point_tile_pack_actor(hls::stream_of_blocks<point_result_tile_t> &inputs,
    hls::stream_of_blocks<output_tile_t> &outputs,int block
    CSIM_PUB_PARAMS(point_result_pub) CSIM_PUB_PARAMS(output_pub)) {
#pragma HLS INLINE off
    const int channels=kZeroDceLayers[2*(block-1)+1].output_channels;
    for(int tile=0;tile<kRowTileCount;++tile) {
        const int height=band_height(tile/7),width=tile%7==6?10:16;
        CSIM_WAIT(point_result_pub);
        {
            hls::read_lock<point_result_tile_t> input(inputs);
            hls::write_lock<output_tile_t> output(outputs);
            pack_output_tile(input,output,channels,height,width);
        }
        CSIM_NOTIFY(output_pub);
    }
}
static void group_rowstream_block(const zero_dce_q16_t *input,zero_dce_q16_t *workspace,
    zero_dce_q16_t *output,const zero_dce_q8_t weights[ZERO_DCE_WEIGHT_ELEMENTS],
    const zero_dce_q8_t point_banks[4][8][kPointBankDepth],
    const zero_dce_q32_t bias[ZERO_DCE_BIAS_ELEMENTS],
    const zero_dce_q8_t frac[ZERO_DCE_WEIGHT_FRAC_ELEMENTS],
    const zero_dce_q16_t lut[4][ZERO_DCE_TANH_LUT_ELEMENTS],int block) {
#pragma HLS INLINE off
    hls::stream_of_blocks<group_strip_t> source_groups;
    hls::stream_of_blocks<middle_band_t> middle_bands;
    hls::stream_of_blocks<point_input_tile_t> point_inputs;
    hls::stream_of_blocks<point_result_tile_t> point_results;
    hls::stream_of_blocks<output_tile_t> output_tiles;
    hls::stream_of_blocks<output_strip_t> output_strips;
#pragma HLS BIND_STORAGE variable=source_groups type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=middle_bands type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=point_inputs type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=point_inputs cyclic factor=8 dim=1
#pragma HLS BIND_STORAGE variable=point_results type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=point_results cyclic factor=4 dim=1
#pragma HLS ARRAY_PARTITION variable=point_results cyclic factor=2 dim=3
#pragma HLS BIND_STORAGE variable=output_tiles type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=output_strips type=ram_2p impl=uram
    hls::stream<zero_dce_q16_t> raw("raw"),result("result");
#pragma HLS STREAM variable=raw depth=256
#pragma HLS STREAM variable=result depth=256
    const int ci=kZeroDceLayers[2*(block-1)].input_channels;
    const int co=kZeroDceLayers[2*(block-1)+1].output_channels;
    const int input_frac=kZeroDceLayers[2*(block-1)].input_frac;
#ifndef __SYNTHESIS__
    hls::stream<ownership_token> group_pub,middle_pub,point_input_pub,point_result_pub,output_pub,store_pub;
    std::thread reader([&]{source_reader(input,workspace,block,ci,raw);});
    std::thread unpacker([&]{group_unpacker(raw,source_groups,block,ci,input_frac,group_pub);});
    std::thread depth([&]{depth_band_actor(source_groups,middle_bands,weights,bias,frac,block,group_pub,middle_pub);});
    std::thread point_feed([&]{point_tile_feed_actor(middle_bands,point_inputs,block,middle_pub,point_input_pub);});
    std::thread point_compute([&]{point_tile_compute_actor(point_inputs,point_results,point_banks,bias,frac,lut,block,point_input_pub,point_result_pub);});
    std::thread point_pack([&]{point_tile_pack_actor(point_results,output_tiles,block,point_result_pub,output_pub);});
    std::thread assembler([&]{output_assembler(output_tiles,output_strips,co,output_pub,store_pub);});
    std::thread packer([&]{output_packer(output_strips,co,result,store_pub);});
    std::thread writer([&]{output_writer(output,workspace,block,co,result);});
    reader.join();unpacker.join();depth.join();point_feed.join();point_compute.join();point_pack.join();assembler.join();packer.join();writer.join();
#else
#pragma HLS DATAFLOW
    source_reader(input,workspace,block,ci,raw);
    group_unpacker(raw,source_groups,block,ci,input_frac);
    depth_band_actor(source_groups,middle_bands,weights,bias,frac,block);
    point_tile_feed_actor(middle_bands,point_inputs,block);
    point_tile_compute_actor(point_inputs,point_results,point_banks,bias,frac,lut,block);
    point_tile_pack_actor(point_results,output_tiles,block);
    output_assembler(output_tiles,output_strips,co);
    output_packer(output_strips,co,result);
    output_writer(output,workspace,block,co,result);
#endif
}

