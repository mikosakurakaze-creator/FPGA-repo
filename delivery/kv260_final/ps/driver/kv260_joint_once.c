// SPDX-License-Identifier: GPL-2.0
/* Fixed 720p one-request bring-up. No reset, mmap, retry or timeout recovery. */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/miscdevice.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/reset.h>
#include <linux/dma-mapping.h>
#include <linux/dma-map-ops.h>
#include <linux/iommu.h>
#include <linux/kref.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/delay.h>
#include <linux/ktime.h>
#include <linux/workqueue.h>
#include <linux/crc32.h>
#include <asm/sysreg.h>
#include <asm/unaligned.h>
#include "d_uapi.h"
#include "smmu_ns_policy.h"


#define GUARD 64
#define DEADLINE_NS (120ULL * 1000000000ULL)
#define NB 84
#define SLOTS 6
static unsigned int bench_frames=120, ps_mode=0, verify_all=1, output_workers=2;
module_param(output_workers,uint,0644);
static unsigned int cache_poison=1;
module_param(cache_poison,uint,0644);
static unsigned int output_variant=2;
module_param(output_variant,uint,0644);
static unsigned int verify_output=1;
module_param(verify_output,uint,0644);
static u8 rgb_lut[65536];
static bool crc_accel;
static u32 output_crc(const u8 *p,size_t n)
{
    u32 crc=0;
    if(!crc_accel)return crc32_le(0,p,n);
    while(n>=8) {
        u64 v=get_unaligned_le64(p);
        asm volatile(".arch_extension crc\n\tcrc32x %w0, %w0, %1" : "+r"(crc) : "r"(v));
        p+=8;n-=8;
    }
    while(n--) {u32 v=*p++;asm volatile(".arch_extension crc\n\tcrc32b %w0, %w0, %w1" : "+r"(crc) : "r"(v));}
    return crc;
}
module_param(bench_frames,uint,0644);
module_param(ps_mode,uint,0644);
module_param(verify_all,uint,0644);
#define NR 11
static const size_t payload[NB] = {2747520,5495040,5495040,38160,38160,5495040,5495040,5495040,5495040,2442240,10075,1944,486,8194,2747520,5495040,5495040,38160,38160,5495040,5495040,5495040,5495040,2442240,10075,1944,486,8194,2747520,5495040,5495040,38160,38160,5495040,5495040,5495040,5495040,2442240,10075,1944,486,8194,2747520,5495040,5495040,38160,38160,5495040,5495040,5495040,5495040,2442240,10075,1944,486,8194,2747520,5495040,5495040,38160,38160,5495040,5495040,5495040,5495040,2442240,10075,1944,486,8194,2747520,5495040,5495040,38160,38160,5495040,5495040,5495040,5495040,2442240,10075,1944,486,8194};
static const unsigned int upload_slot[9] = {1,2,3,10,11,12,13,8,0};
static const resource_size_t bases[NR] = {0xa0000000,0xa0010000,0xa0020000,0xa0030000,0xa0040000,0xa0050000,0xfd800000,0xfd380000,0xfd390000,0xfd3a0000,0xfd3b0000};
static const resource_size_t spans[NR] = {0x10000,0x10000,0x10000,0x10000,0x10000,0x10000,0x1000,0x1000,0x1000,0x1000,0x1000};
struct joint_once {
    struct kref refs;
    struct mutex lock;
    struct miscdevice misc;
    struct device *dev;
    struct clk *clock, *clock_d;
    struct reset_control *reset;
    void __iomem *regs[NR];
    bool claimed[NR],used,removed,pinned,prepared;
    bool done_seen[6];
    u64 begin_ns[6],elapsed_ns[6],calls[6];
    void *cpu[NB],*frozen[9],*variants[3];
    dma_addr_t dma[NB];
    size_t received;
    struct compact_d_status status;
};
static size_t allocation(unsigned int i) { return PAGE_ALIGN(payload[i]+2*GUARD); }
static void free_state(struct kref *ref)
{
    struct joint_once *s=container_of(ref,struct joint_once,refs);
    unsigned int i;
    WARN_ON(s->status.pending);
    for(i=0;i<NB;i++) if(s->cpu[i]) dma_free_noncoherent(s->dev,allocation(i),s->cpu[i],s->dma[i],DMA_BIDIRECTIONAL);
    for(i=0;i<9;i++) kvfree(s->frozen[i]);
    for(i=0;i<3;i++) kvfree(s->variants[i]);
    for(i=0;i<NR;i++) {
        if(s->regs[i]) iounmap(s->regs[i]);
        if(s->claimed[i]) release_mem_region(bases[i],spans[i]);
    }
    if(!IS_ERR_OR_NULL(s->reset)) reset_control_put(s->reset);
    if(!IS_ERR_OR_NULL(s->clock_d)) clk_put(s->clock_d);
    if(!IS_ERR_OR_NULL(s->clock)) clk_put(s->clock);
    put_device(s->dev);kfree(s);
}
static int gates(struct joint_once *s)
{
    unsigned int i;
    if(s->removed) return -ENODEV;
    s->status.clock_hz=clk_get_rate(s->clock);
    if(!__clk_is_enabled(s->clock) || reset_control_status(s->reset)!=0) return -EHOSTDOWN;
    if(s->status.clock_hz<99000000 || s->status.clock_hz>101000000) return -ERANGE;
    if(!kv260_smmu_ns_bypass_ok(readl(s->regs[6]+0x20),readl(s->regs[6]))) return -EOPNOTSUPP;
    if(!__clk_is_enabled(s->clock_d) || clk_get_rate(s->clock_d)<198000000 || clk_get_rate(s->clock_d)>202000000) return -EHOSTDOWN;
    for(i=7;i<NR;i++) if((readl(s->regs[i])&3) || (readl(s->regs[i]+0x14)&3)) return -EPROTO;
    return 0;
}
static int idle(struct joint_once *s)
{
    unsigned int i;
    for(i=0;i<6;i++) {
        u32 v;
        if(readl(s->regs[i]+4) || readl(s->regs[i]+8) || (readl(s->regs[i]+12)&~3U)) return -EPROTO;
        v=readl(s->regs[i]);
        if((v&~0xfU) || !(v&4) || (v&1)) return -EBUSY;
    }
    return 0;
}
static int prepare(struct joint_once *s)
{
    unsigned int i,j;
    int ret=gates(s);
    if(s->prepared) return -EALREADY;
    if(!ret) ret=idle(s);
    if(ret) return ret;
    s->prepared=true;
    for(i=0;i<9;i++) {
        s->frozen[i]=kvzalloc(payload[upload_slot[i]]*(i==8?SLOTS:1),GFP_KERNEL);
        if(!s->frozen[i]) return -ENOMEM;
    }
    for(i=0;i<3;i++) {
        s->variants[i]=kvzalloc(SLOTS*payload[0],GFP_KERNEL);
        if(!s->variants[i]) return -ENOMEM;
    }
    for(i=0;i<NB;i++) {
        s->cpu[i]=dma_alloc_noncoherent(s->dev,allocation(i),&s->dma[i],DMA_BIDIRECTIONAL,GFP_KERNEL);
        if(!s->cpu[i]) return -ENOMEM;
        if((s->dma[i]&63) || s->dma[i]>=0x7ff00000ULL || allocation(i)>0x7ff00000ULL-s->dma[i]) return -ERANGE;
        for(j=0;j<i;j++) if(!(s->dma[i]+allocation(i)<=s->dma[j] || s->dma[j]+allocation(j)<=s->dma[i])) return -EADDRINUSE;
        s->status.dma[i]=s->dma[i]+GUARD;
        dma_sync_single_for_cpu(s->dev,s->dma[i],allocation(i),DMA_BIDIRECTIONAL);
        memset(s->cpu[i],0x3c,GUARD);
        memset((u8 *)s->cpu[i]+GUARD+payload[i],0xc3,allocation(i)-GUARD-payload[i]);
        dma_sync_single_for_device(s->dev,s->dma[i],allocation(i),DMA_BIDIRECTIONAL);
    }
    return 0;
}
static int reg32(struct joint_once *s,unsigned int ip,u32 offset,u32 value)
{
    writel(value,s->regs[ip]+offset);
    return readl(s->regs[ip]+offset)==value ? 0 : -EIO;
}
static int ptr(struct joint_once *s,unsigned int ip,u32 offset,unsigned int slot)
{
    u64 addr=s->status.dma[slot];
    int ret=reg32(s,ip,offset,lower_32_bits(addr));
    return ret ? ret : reg32(s,ip,offset+4,upper_32_bits(addr));
}
static int launch(struct joint_once *s,unsigned int ip)
{
    u32 v=readl(s->regs[ip]);
    int ret=gates(s);
    if(ret) return ret;
    if(!(v&4) || (v&1) || (v&~0xfU)) return -EBUSY;
    if(!s->pinned) { __module_get(THIS_MODULE);kref_get(&s->refs);s->pinned=true; }
    s->done_seen[ip]=false;s->status.pending=1;dma_wmb();
    
    s->begin_ns[ip]=ktime_get_ns();writel(1,s->regs[ip]);return 0;
}
static int poll_done(struct joint_once *s,unsigned int ip)
{
    u32 v=readl(s->regs[ip]);
    s->status.ctrl=v;
    if(v&~0xfU) return -EPROTO;
    if(v&2)s->done_seen[ip]=true;
    if(!s->done_seen[ip] || !(v&4))return 0;
    s->done_seen[ip]=false;
    if(ip>=3) { s->status.core_return=readl(s->regs[ip]+0x10);if(s->status.core_return) return -EREMOTEIO; }
    s->elapsed_ns[ip]+=ktime_get_ns()-s->begin_ns[ip];s->calls[ip]++;
    dma_rmb();s->status.completed_nodes|=BIT(ip);return 1;
}
/* Each slot is handed to the CPU only after its own fusion completes.
 * Model arrays are shared read-only and synchronized only with all IPs idle. */
static void slot_to_device(struct joint_once *s,unsigned int slot,unsigned int id)
{
    unsigned int j,n=slot*14+8;
    dma_sync_single_for_cpu(s->dev,s->dma[n],allocation(n),DMA_BIDIRECTIONAL);
    /* Poison the whole output each frame, so stale cache lines cannot pass Golden. */
    if(cache_poison)memset((u8 *)s->cpu[n]+GUARD,(id&1)?0x5a:0xa5,payload[n]);
    for(j=slot*14;j<slot*14+10;j++) {
        if(ps_mode==1 && j%14>=1 && j%14<=3)continue;
        dma_sync_single_for_device(s->dev,s->dma[j],allocation(j),DMA_BIDIRECTIONAL);
    }
}
static void slot_to_cpu(struct joint_once *s,unsigned int slot)
{
    unsigned int j;
    for(j=slot*14;j<slot*14+10;j++) {
        size_t tail=(GUARD+payload[j])&~63UL;
        if(j%14==8)dma_sync_single_for_cpu(s->dev,s->dma[j],allocation(j),DMA_BIDIRECTIONAL);
        else {
            dma_sync_single_range_for_cpu(s->dev,s->dma[j],0,GUARD,DMA_BIDIRECTIONAL);
            dma_sync_single_range_for_cpu(s->dev,s->dma[j],tail,allocation(j)-tail,DMA_BIDIRECTIONAL);
        }
    }
}
struct frame_state { unsigned int id,started,done; };
struct slot_work {
    struct work_struct work;
    struct joint_once *s;
    unsigned int slot,id,kind,mode,check;
    bool finished;
    int error;
    void *original,*d,*low,*output,*rgb[3];
    u64 ps_ns,consume_ns;
    u32 crc;
};
static void cpu_slot_work(struct work_struct *work)
{
    struct slot_work *w=container_of(work,struct slot_work,work);
    struct joint_once *s=w->s;
    const unsigned int n=720*1272;
    unsigned int i,c,y,x,j;
    u64 begin=ktime_get_ns();
    w->error=0;
    if(w->kind==0 && w->mode==2) {
        unsigned int k=w->slot*14;
        dma_sync_single_for_cpu(s->dev,s->dma[k],allocation(k),DMA_BIDIRECTIONAL);
        memcpy((u8 *)s->cpu[k]+GUARD,(u8 *)s->frozen[8]+(w->id-1)*payload[0],payload[0]);
        dma_sync_single_for_device(s->dev,s->dma[k],allocation(k),DMA_BIDIRECTIONAL);
        w->ps_ns+=ktime_get_ns()-begin;
    } else if(w->kind==0) {
        const u8 *raw=s->frozen[8];
        s16 *o=(s16 *)((u8 *)s->cpu[w->slot*14+1]+GUARD);
        s16 *d=(s16 *)((u8 *)s->cpu[w->slot*14+2]+GUARD);
        s16 *low=(s16 *)((u8 *)s->cpu[w->slot*14+3]+GUARD);
        s16 ilut[256],dlut[256];
        for(j=1;j<=3;j++)dma_sync_single_for_cpu(s->dev,s->dma[w->slot*14+j],allocation(w->slot*14+j),DMA_BIDIRECTIONAL);
        for(i=0;i<256;i++) {ilut[i]=(i*16384+127)/255;dlut[i]=(i*32768+127)/255-16384;}
        for(i=0;i<n;i++)for(c=0;c<3;c++){unsigned int v=raw[3*i+c];o[c*n+i]=ilut[v];d[c*n+i]=dlut[v];}
        for(c=0;c<3;c++)for(y=0;y<60;y++)for(x=0;x<106;x++) {
            unsigned int k=c*n+(12*y+5)*1272+12*x+5;
            int v=o[k]+o[k+1]+o[k+1272]+o[k+1273],q=v/4,rem=v%4;
            low[c*6360+y*106+x]=q+(rem>2 || (rem==2 && (q&1)));
        }
        /* Check the PS conversion independently on its first use per slot. */
        if(w->id<=SLOTS && (memcmp(o,s->frozen[0],payload[1]) || memcmp(d,s->frozen[1],payload[2]) || memcmp(low,s->frozen[2],payload[3])))w->error=-EILSEQ;
        for(j=1;j<=3;j++)dma_sync_single_for_device(s->dev,s->dma[w->slot*14+j],allocation(w->slot*14+j),DMA_BIDIRECTIONAL);
        dma_wmb();w->ps_ns+=ktime_get_ns()-begin;
    } else {
        dma_rmb();slot_to_cpu(s,w->slot);
        if(verify_all && w->check && w->mode==2)for(j=1;j<=3;j++) {
            unsigned int k=w->slot*14+j;
            dma_sync_single_for_cpu(s->dev,s->dma[k],allocation(k),DMA_BIDIRECTIONAL);
            if(memcmp((u8 *)s->cpu[k]+GUARD,s->frozen[j-1],payload[j]))w->error=-EILSEQ;
        }
        if(w->mode) {
            static const unsigned int outputs[3]={6,7,8};
            unsigned int v;
            for(v=output_variant;v<=output_variant;v++) {
                const u16 *q;
                u8 *rgb=w->rgb[v];
                if(outputs[v]!=8)dma_sync_single_for_cpu(s->dev,s->dma[w->slot*14+outputs[v]],allocation(w->slot*14+outputs[v]),DMA_BIDIRECTIONAL);
                q=(u16 *)((u8 *)s->cpu[w->slot*14+outputs[v]]+GUARD);
                if(v==2 && verify_output && w->check && memcmp(q,s->frozen[7],payload[8]))w->error=-EILSEQ;
                for(i=0;i<n;i++) {
                    rgb[3*i]=rgb_lut[q[i]];
                    rgb[3*i+1]=rgb_lut[q[n+i]];
                    rgb[3*i+2]=rgb_lut[q[2*n+i]];
                }
                memcpy((u8 *)s->variants[v]+(w->id-1)*payload[0],w->rgb[v],payload[0]);
            }
            w->crc=output_crc(w->rgb[output_variant],3*n);
            memcpy(s->frozen[7],w->rgb[output_variant],3*n);
        } else if(w->check && memcmp((u8 *)s->cpu[w->slot*14+8]+GUARD,s->frozen[7],payload[8]))w->error=-EILSEQ;
        for(j=w->slot*14;j<w->slot*14+10;j++)if(memchr_inv(s->cpu[j],0x3c,GUARD) || memchr_inv((u8 *)s->cpu[j]+GUARD+payload[j],0xc3,allocation(j)-GUARD-payload[j]))w->error=-EOVERFLOW;
        w->consume_ns+=ktime_get_ns()-begin;
    }
    smp_store_release(&w->finished,true);
}
static int configure(struct joint_once *s,unsigned int ip,unsigned int slot,unsigned int frame)
{
    static const unsigned int pp[][3]={
      {3,0x18,0},{3,0x24,1},{3,0x30,2},{3,0x3c,3},
      {2,0x10,3},{2,0x1c,10},{2,0x28,11},{2,0x34,12},{2,0x40,13},{2,0x4c,4},{2,0x58,9},
      {0,0x10,4},{0,0x1c,5},{1,0x10,1},{1,0x1c,5},{1,0x28,6},
      {5,0x18,2},{5,0x24,7},{4,0x18,1},{4,0x24,6},{4,0x30,7},{4,0x3c,8}};
    static const u32 cfg[][3]={{3,0x48,0x4a503031},{0,0x28,60},{0,0x30,106},{1,0x34,2747520},
      {5,0x30,720},{5,0x38,1272},{5,0x40,0x44433031},
      {4,0x48,10923},{4,0x50,10923},{4,0x58,10922},{4,0x60,0x4a463031}};
    unsigned int i;int ret;
    for(i=0;i<ARRAY_SIZE(pp);i++)if(pp[i][0]==ip) {
        unsigned int n=pp[i][2];ret=ptr(s,ip,pp[i][1],n>=10?n:slot*14+n);if(ret)return ret;
    }
    for(i=0;i<ARRAY_SIZE(cfg);i++)if(cfg[i][0]==ip) {ret=reg32(s,ip,cfg[i][1],cfg[i][2]);if(ret)return ret;}
    if(ip==4) {ret=reg32(s,4,0x68,frame);if(ret)return ret;}
    return 0;
}
static int execute(struct joint_once *s)
{
    const unsigned int order[6]={4,1,0,2,5,3};
    unsigned int deps[6]={BIT(2),BIT(0),0,0,BIT(1)|BIT(5),0};
    struct frame_state f[SLOTS]={0};
    struct slot_work w[SLOTS]={0};
    struct workqueue_struct *psq=NULL,*outq=NULL;
    int owner[6]={-1,-1,-1,-1,-1,-1};
    unsigned int i,j,admitted=0,retired=0,max_running=0;
    unsigned int frames=bench_frames,mode=ps_mode,all=verify_all;
    bool ready[SLOTS]={0},consuming[SLOTS]={0};
    size_t total=0;u64 begin=0,ps_total=0,consume_total=0;int ret=0;
    for(i=0;i<9;i++)total+=payload[upload_slot[i]]*(i==8?frames:1);
    if(frames<1 || frames>SLOTS || output_variant>2 || mode!=2 || all>1 || output_workers<1 || output_workers>3 || cache_poison>1)return -EINVAL;
    if(s->status.attempted || !s->prepared || s->received!=total)return -EINVAL;
    if(mode==2){deps[2]=BIT(3);deps[5]=BIT(3);}
    s->status.attempted=1;ret=gates(s);if(!ret)ret=idle(s);if(ret)return ret;
    psq=alloc_ordered_workqueue("joint_ps_prepare",WQ_MEM_RECLAIM);
    outq=alloc_workqueue("joint_output",WQ_UNBOUND|WQ_MEM_RECLAIM,output_workers);
    if(!psq || !outq){ret=-ENOMEM;goto cleanup;}
    for(i=0;i<14*frames;i++)dma_sync_single_for_cpu(s->dev,s->dma[i],allocation(i),DMA_BIDIRECTIONAL);
    for(i=0;i<frames;i++) {
        w[i].s=s;w[i].slot=i;w[i].mode=mode;INIT_WORK(&w[i].work,cpu_slot_work);
        if(mode) {
            for(j=output_variant;j<=output_variant;j++) {
                w[i].rgb[j]=kvzalloc(payload[0],GFP_KERNEL);
                if(!w[i].rgb[j]){ret=-ENOMEM;goto cleanup;}
            }
        } else for(j=0;j<3;j++)memcpy((u8 *)s->cpu[i*14+1+j]+GUARD,s->frozen[j],payload[1+j]);
    }
    for(i=3;i<7;i++)memcpy((u8 *)s->cpu[upload_slot[i]]+GUARD,s->frozen[i],payload[upload_slot[i]]);
    for(i=10;i<14;i++)dma_sync_single_for_device(s->dev,s->dma[i],allocation(i),DMA_BIDIRECTIONAL);
    memset(s->elapsed_ns,0,sizeof(s->elapsed_ns));memset(s->calls,0,sizeof(s->calls));
    begin=ktime_get_ns();
    dev_info(s->dev,"FPS_BEGIN frames=%u ps_mode=%u verify_all=%u slots=%u poison=%u workers=%u\n",frames,mode,all,SLOTS,cache_poison,output_workers);
    while(retired<frames) {
        unsigned int running=0;
        for(i=0;i<SLOTS;i++)if(f[i].id && !ready[i] && !consuming[i] && smp_load_acquire(&w[i].finished)) {
            flush_work(&w[i].work);if(w[i].error){ret=w[i].error;goto cleanup;}ready[i]=true;
        }
        for(i=0;i<6;i++)if(owner[i]>=0) {
            j=owner[i];ret=poll_done(s,i);if(ret<0)goto cleanup;
            if(ret==1) {
                if(i==4 && readl(s->regs[4]+0x70)!=f[j].id){ret=-EPROTO;goto cleanup;}
                f[j].done|=BIT(i);owner[i]=-1;
            }
        }
        for(i=0;i<SLOTS;i++)if(f[i].id && (f[i].done&BIT(4)) && !consuming[i]) {
            w[i].kind=1;w[i].check=all || f[i].id==1 || f[i].id==frames;
            WRITE_ONCE(w[i].finished,false);consuming[i]=true;queue_work(outq,&w[i].work);
        }
        for(i=0;i<SLOTS;i++)if(f[i].id==retired+1 && consuming[i] && smp_load_acquire(&w[i].finished)) {
            flush_work(&w[i].work);if(w[i].error){ret=w[i].error;goto cleanup;}
            retired++;dev_info(s->dev,"FPS_FRAME id=%u slot=%u elapsed_ns=%llu checked=%u rgb_crc=%u\n",f[i].id,i,ktime_get_ns()-begin,w[i].check,w[i].crc);
            f[i].id=0;f[i].started=f[i].done=0;ready[i]=consuming[i]=false;
        }
        for(i=0;i<SLOTS && admitted<frames;i++)if(!f[i].id) {
            f[i].id=++admitted;w[i].id=f[i].id;w[i].kind=0;w[i].error=0;
            slot_to_device(s,i,f[i].id);
            WRITE_ONCE(w[i].finished,false);
            if(mode)queue_work(psq,&w[i].work);else ready[i]=true;
        }
        for(i=0;i<(mode==2?6:5);i++) {
            unsigned int ip=order[i],best=frames+1,slot=SLOTS;
            if(owner[ip]>=0)continue;
            for(j=0;j<SLOTS;j++)if(f[j].id && !(f[j].started&BIT(ip)) && f[j].id<best){best=f[j].id;slot=j;}
            if(slot==SLOTS || !ready[slot] || (f[slot].done&deps[ip])!=deps[ip])continue;
            ret=configure(s,ip,slot,f[slot].id);if(ret)goto cleanup;
            ret=launch(s,ip);if(ret)goto cleanup;
            f[slot].started|=BIT(ip);owner[ip]=slot;
        }
        for(i=0;i<6;i++)if(owner[i]>=0)running++;
        if(running>max_running)max_running=running;
        if(ktime_get_ns()-begin>=DEADLINE_NS){ret=-ETIMEDOUT;goto cleanup;}
        usleep_range(50,100);
    }
    ret=idle(s);if(ret)goto cleanup;
    s->status.pending=0;s->status.elapsed_ns=ktime_get_ns()-begin;
    for(i=0;i<14*frames;i++)dma_sync_single_for_cpu(s->dev,s->dma[i],allocation(i),DMA_BIDIRECTIONAL);
    /* All output slots have been consumed; final immutable model check is separate. */
    for(i=3;i<7;i++)if(memcmp((u8 *)s->cpu[upload_slot[i]]+GUARD,s->frozen[i],payload[upload_slot[i]])){ret=-EILSEQ;goto cleanup;}
    for(i=0;i<NB;i++)if(memchr_inv(s->cpu[i],0x3c,GUARD) || memchr_inv((u8 *)s->cpu[i]+GUARD+payload[i],0xc3,allocation(i)-GUARD-payload[i])){ret=-EOVERFLOW;goto cleanup;}
    s->status.guards_ok=1;s->status.completed=1;s->status.reserved=frames;
    for(i=0;i<SLOTS;i++){ps_total+=w[i].ps_ns;consume_total+=w[i].consume_ns;}
    dev_info(s->dev,"FPS_DONE frames=%u mode=%u verify_all=%u max_concurrent=%u elapsed_ns=%llu ps_total_ns=%llu consume_total_ns=%llu\n",retired,mode,all,max_running,s->status.elapsed_ns,ps_total,consume_total);
    for(i=0;i<6;i++)if(s->calls[i])dev_info(s->dev,"CORE_TIMING ip=%u calls=%llu total_ns=%llu\n",i,s->calls[i],s->elapsed_ns[i]);
    ret=0;
cleanup:
    if(psq)destroy_workqueue(psq);
    if(outq)destroy_workqueue(outq);
    for(i=0;i<SLOTS;i++){for(j=0;j<3;j++)kvfree(w[i].rgb[j]);kvfree(w[i].original);kvfree(w[i].d);kvfree(w[i].low);kvfree(w[i].output);}
    return ret;
}
static long d_ioctl(struct file *file,unsigned int cmd,unsigned long arg)
{
    struct joint_once *s=file->private_data;
    int ret;
    mutex_lock(&s->lock);
    if(cmd==_IO('G',0xe3) || cmd==_IO('G',0xe4)) {
        if(s->removed || s->status.error || s->status.pending || !s->status.completed)ret=-EBUSY;
        else {
            ret=idle(s);
            if(!ret){s->status.attempted=s->status.completed=s->status.completed_nodes=s->status.guards_ok=s->status.reserved=s->status.core_return=0;s->status.elapsed_ns=0;s->received=0;file->f_pos=0;
                if(cmd==_IO('G',0xe4)){unsigned int z;for(z=0;z<8;z++)s->received+=payload[upload_slot[z]];file->f_pos=s->received;}}
        }
    }
    else if(cmd==D_STATUS) ret=copy_to_user((void __user *)arg,&s->status,sizeof(s->status))?-EFAULT:0;
    else if(cmd!=D_ALLOC && cmd!=D_RUN) ret=-ENOTTY;
    else if(s->removed || s->status.error || s->status.pending) ret=-ECANCELED;
    else {
        if(cmd==D_ALLOC) ret=prepare(s);
        else { file->f_pos=0;ret=execute(s); }
        if(ret) s->status.error=ret;
    }
    mutex_unlock(&s->lock);return ret;
}
static int d_open(struct inode *inode,struct file *file)
{
    struct joint_once *s=container_of(file->private_data,struct joint_once,misc);
    int ret=0;
    mutex_lock(&s->lock);
    if(s->used || s->removed) ret=-EBUSY;
    else { s->used=true;kref_get(&s->refs);file->private_data=s; }
    mutex_unlock(&s->lock);return ret;
}
static int d_release(struct inode *inode,struct file *file)
{
    struct joint_once *s=file->private_data;
    bool unpin=false;
    unsigned int i;
    mutex_lock(&s->lock);
    if(s->status.pending) dev_err(s->dev,"D_QUARANTINE: retain DMA/maps/module; no reset/reload/retry\n");
    else {
        for(i=0;i<NB;i++) if(s->cpu[i]) {
            dma_free_noncoherent(s->dev,allocation(i),s->cpu[i],s->dma[i],DMA_BIDIRECTIONAL);s->cpu[i]=NULL;
        }
        if(s->pinned) { s->pinned=false;unpin=true; }
    }
    mutex_unlock(&s->lock);
    if(unpin) kref_put(&s->refs,free_state);
    kref_put(&s->refs,free_state);
    if(unpin) module_put(THIS_MODULE);
    return 0;
}
static ssize_t d_write(struct file *file,const char __user *buf,size_t count,loff_t *ppos)
{
    struct joint_once *s=file->private_data;
    unsigned int i;
    size_t at,n;
    ssize_t ret=-EINVAL;
    mutex_lock(&s->lock);
    if(!s->prepared || s->status.error || s->status.attempted || s->removed || s->status.pending || *ppos!=s->received) goto out;
    at=s->received;
    for(i=0;i<9;i++) {
        if(at<payload[upload_slot[i]]*(i==8?bench_frames:1)) {
            n=min_t(size_t,count,payload[upload_slot[i]]*(i==8?bench_frames:1)-at);
            if(copy_from_user((u8 *)s->frozen[i]+at,buf,n)) { ret=-EFAULT;goto out; }
            s->received+=n;*ppos+=n;ret=n;goto out;
        }
        at-=payload[upload_slot[i]]*(i==8?bench_frames:1);
    }
out:
    mutex_unlock(&s->lock);return ret;
}
static ssize_t d_read(struct file *file,char __user *buf,size_t count,loff_t *ppos)
{
    struct joint_once *s=file->private_data;
    ssize_t ret=-EBUSY;
    size_t at,n;
    mutex_lock(&s->lock);
    if(s->status.pending || s->status.error || !s->status.completed || s->removed) ret=-EBUSY;
    else if(*ppos>=bench_frames*payload[0])ret=0;
    else {
        at=*ppos;n=min_t(size_t,count,bench_frames*payload[0]-at);
        if(copy_to_user(buf,(u8 *)s->variants[output_variant]+at,n))ret=-EFAULT;
        else {*ppos+=n;ret=n;}
    }
    mutex_unlock(&s->lock);return ret;
}
static const struct file_operations d_fops={
    .owner=THIS_MODULE,.open=d_open,.release=d_release,.read=d_read,.write=d_write,
    .unlocked_ioctl=d_ioctl,.llseek=no_llseek,
};
static int d_probe(struct platform_device *pdev)
{
    struct joint_once *s;
    unsigned int i;
    int ret;
    BUILD_BUG_ON(sizeof(struct compact_d_status)!=736);
    for(i=0;i<65536;i++) {
        int v=(s16)i;
        rgb_lut[i]=v<=0?0:v>=16384?255:(v*255+8192)/16384;
    }
    crc_accel=((read_sysreg(id_aa64isar0_el1)>>16)&15)!=0;
    if(output_crc(rgb_lut,65536)!=crc32_le(0,rgb_lut,65536))return -EILSEQ;
    BUILD_BUG_ON(PAGE_SIZE!=4096);
    if(platform_get_resource(pdev,IORESOURCE_MEM,NR) ||
       of_find_property(pdev->dev.of_node,"dma-coherent",NULL) ||
       of_find_property(pdev->dev.of_node,"iommus",NULL) ||
       of_find_property(pdev->dev.of_node,"dma-ranges",NULL) ||
       of_find_property(pdev->dev.of_node,"memory-region",NULL)) return -EINVAL;
    s=kzalloc(sizeof(*s),GFP_KERNEL);if(!s) return -ENOMEM;
    kref_init(&s->refs);mutex_init(&s->lock);s->dev=get_device(&pdev->dev);s->status.abi=1;
    s->clock=clk_get(s->dev,"pl0");if(IS_ERR(s->clock)) { ret=PTR_ERR(s->clock);goto fail; }
    s->clock_d=clk_get(s->dev,"pl1");if(IS_ERR(s->clock_d)) { ret=PTR_ERR(s->clock_d);goto fail; }
    s->reset=reset_control_get_shared(s->dev,"pl0");if(IS_ERR(s->reset)) { ret=PTR_ERR(s->reset);goto fail; }
    if(get_dma_ops(s->dev) || iommu_get_domain_for_dev(s->dev)) { ret=-EOPNOTSUPP;goto fail; }
    ret=dma_coerce_mask_and_coherent(s->dev,DMA_BIT_MASK(32));if(ret) goto fail;
    for(i=0;i<NR;i++) {
        struct resource *r=platform_get_resource(pdev,IORESOURCE_MEM,i);
        if(!r || r->start!=bases[i] || resource_size(r)!=spans[i]) { ret=-EINVAL;goto fail; }
        if(!request_mem_region(bases[i],spans[i],"kv260-grid-once")) { ret=-EBUSY;goto fail; }
        s->claimed[i]=true;s->regs[i]=ioremap(bases[i],spans[i]);
        if(!s->regs[i]) { ret=-ENOMEM;goto fail; }
    }
    s->misc.minor=MISC_DYNAMIC_MINOR;s->misc.name="kv260_joint_once";s->misc.mode=0600;
    s->misc.fops=&d_fops;s->misc.parent=s->dev;
    ret=misc_register(&s->misc);if(ret) goto fail;
    platform_set_drvdata(pdev,s);
    dev_info(s->dev,"D_REGISTERED no IP start or DMA at probe\n");return 0;
fail:
    kref_put(&s->refs,free_state);return ret;
}
static int d_remove(struct platform_device *pdev)
{
    struct joint_once *s=platform_get_drvdata(pdev);
    mutex_lock(&s->lock);s->removed=true;mutex_unlock(&s->lock);
    misc_deregister(&s->misc);kref_put(&s->refs,free_state);return 0;
}
static const struct of_device_id d_match[]={ {.compatible="fpga-joint,kv260-once-v1"},{} };
MODULE_DEVICE_TABLE(of,d_match);
static struct platform_driver d_driver={ .probe=d_probe,.remove=d_remove,
    .driver={.name="kv260_joint_once",.of_match_table=d_match,.suppress_bind_attrs=true} };
module_platform_driver(d_driver);
MODULE_LICENSE("GPL");
MODULE_VERSION("1.0");
MODULE_DESCRIPTION("KV260 joint six-core single-frame bring-up");
