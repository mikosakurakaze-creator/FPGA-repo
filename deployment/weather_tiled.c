#include "weather_control.h"
#include <string.h>

static int min_i(int a,int b) { return a<b?a:b; }
static int max_i(int a,int b) { return a>b?a:b; }
static int cpu_range(const void* p,size_t bytes) {
    return p && !((uintptr_t)p&1U) && bytes<=UINTPTR_MAX-(uintptr_t)p;
}
static int intersects(const void* a,size_t n,const void* b,size_t m) {
    return (uintptr_t)a < (uintptr_t)b+m && (uintptr_t)b < (uintptr_t)a+n;
}
int weather_run_tiled(struct weather_device* d,const int16_t* input,size_t ni,
                      int16_t* output,size_t no,int h,int w,int core,
                      struct weather_job* workspace,uint64_t timeout,uint32_t max_polls,
                      uint32_t* completed) {
    int y,x,c,r;
    size_t count,bytes;
    struct weather_buffer b[3];
    if(completed) *completed=0;
    if(!d || !workspace || d->abi!=WEATHER_TILE_V1 || h<1 || h>720 || w<1 || w>1280 ||
       (core!=64 && core!=128) || !timeout || !max_polls) return WEATHER_EINVAL;
    if(d->quarantined || d->owned_mask) return WEATHER_EQUARANTINED;
    count=(size_t)3*h*w;bytes=count*2;
    if(ni<count || no<count || !cpu_range(input,bytes) || !cpu_range(output,bytes) ||
       intersects(input,bytes,output,bytes)) return WEATHER_EINVAL;
    b[0]=workspace->input;b[1]=workspace->output;b[2]=workspace->scratch;
    /* Validate all maximum-tile capacities before touching frame/work memory. */
    for(c=0;c<3;++c) {
        size_t need=(c==2?48U:6U)*min_i(h,core+12)*min_i(w,core+12);
        int k;
        if(!cpu_range(b[c].cpu,b[c].bytes) || b[c].bytes<need ||
           b[c].bytes>UINT64_MAX-b[c].device_address || (b[c].device_address&1U) ||
           intersects(input,bytes,b[c].cpu,b[c].bytes) || intersects(output,bytes,b[c].cpu,b[c].bytes))
            return WEATHER_EINVAL;
        for(k=0;k<c;++k) {
            if(intersects(b[c].cpu,b[c].bytes,b[k].cpu,b[k].bytes) ||
               (b[c].device_address < b[k].device_address+b[k].bytes &&
                b[k].device_address < b[c].device_address+b[c].bytes)) return WEATHER_EINVAL;
        }
    }
    if(workspace->task!=d->fixed_task) return WEATHER_EINVAL;
    for(y=0;y<h;y+=core) for(x=0;x<w;x+=core) {
        int y1=min_i(y+core,h),x1=min_i(x+core,w);
        int y0=max_i(y-6,0),x0=max_i(x-6,0);
        int th=min_i(y1+6,h)-y0,tw=min_i(x1+6,w)-x0;
        int status;
        uint32_t ctrl;
        struct weather_job job=*workspace;
        job.height=th;job.width=tw;
        /* Reject a stale running/auto-restarting IP before modifying DMA input. */
        if(d->platform.read32(d->platform.user,0,&ctrl)) return WEATHER_EIO;
        if(!(ctrl&4U) || (ctrl&0x80U)) return WEATHER_EBUSY;
        for(c=0;c<3;++c) for(r=0;r<th;++r)
            memcpy((int16_t*)job.input.cpu+(c*th+r)*tw,input+(c*h+y0+r)*w+x0,(size_t)tw*2);
        status=weather_run(d,&job,timeout,max_polls,0);
        if(status) return status;
        for(c=0;c<3;++c) for(r=y;r<y1;++r)
            memcpy(output+(c*h+r)*w+x,(int16_t*)job.output.cpu+(c*th+r-y0)*tw+x-x0,(size_t)(x1-x)*2);
        if(completed) ++*completed;
    }
    return WEATHER_OK;
}
