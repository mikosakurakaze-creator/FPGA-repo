#include "pipeline.h"

static int stamp(kv_io *io, uint64_t *v, uint64_t *last) {
    *v=io->ticks(io->ctx);
    if (*v < *last) return KV_TIMER;
    *last=*v;
    return KV_OK;
}

int kv_execute(kv_io *io, uint64_t base, const kv_arg *args, size_t n, kv_stage *s) {
    uint64_t last=0, first, now;
    uint32_t ctrl;
    *s=(kv_stage){0};
    if (!io->frequency || !io->timeout_ticks || !io->poll_limit) return KV_TIMER;
    /* Consume old done before start, then demand a clean idle state. One reader. */
    ctrl=io->read32(io->ctx,base);
    s->last_ctrl=ctrl;
    if ((ctrl & ~0xEu) || !(ctrl & 4u)) return KV_STATE;
    ctrl=io->read32(io->ctx,base);
    s->last_ctrl=ctrl;
    if (ctrl!=4u || io->read32(io->ctx,base+4)!=0u ||
        io->read32(io->ctx,base+8)!=0u || io->read32(io->ctx,base+12)!=0u)
        return KV_STATE;
    for (size_t i=0;i<n;i++) {
        io->write32(io->ctx,base+args[i].offset,args[i].value);
        if (io->read32(io->ctx,base+args[i].offset)!=args[i].value) return KV_ARG;
    }
    io->barrier(io->ctx);
    if (stamp(io,&s->submit_before,&last)) return KV_TIMER;
    io->write32(io->ctx,base,1u); /* Exactly one start. No retry/abort/reset. */
    io->barrier(io->ctx);
    if (stamp(io,&s->submit_after,&last)) return KV_TIMER;
    first=s->submit_before;
    for (uint32_t k=0;k<io->poll_limit;k++) {
        uint64_t before;
        if (stamp(io,&before,&last)) return KV_TIMER;
        ctrl=io->read32(io->ctx,base);
        io->barrier(io->ctx);
        if (stamp(io,&now,&last)) return KV_TIMER;
        s->polls++; s->last_ctrl=ctrl;
        if (ctrl & ~0xFu) return KV_STATE;
        if (ctrl & 2u) {
            s->done_before=before; s->done_after=now;
            if (!(ctrl & 4u) || (ctrl & 1u)) return KV_STATE;
            if (now-first>io->timeout_ticks) return KV_TIMEOUT;
            return KV_OK;
        }
        s->previous_before=before; s->previous_after=now;
        if (now-first>io->timeout_ticks) return KV_TIMEOUT;
    }
    return KV_TIMEOUT;
}

static void ptr(kv_arg *a, size_t *n, uint32_t off, uint64_t p) {
    a[(*n)++]=(kv_arg){off,(uint32_t)p};
    a[(*n)++]=(kv_arg){off+4,(uint32_t)(p>>32)};
}
int kv_pipeline(kv_io *io, const kv_buffers *b, kv_stage s[3], uint64_t starts[3],
                uint64_t dones[3]) {
    const uint64_t bases[3]={0xA0020000ULL,0xA0000000ULL,0xA0010000ULL};
    kv_arg a[14]; size_t n=0; int rc;
    ptr(a,&n,0x10,b->low_input); ptr(a,&n,0x1C,b->weights);
    ptr(a,&n,0x28,b->bias); ptr(a,&n,0x34,b->frac); ptr(a,&n,0x40,b->lut);
    ptr(a,&n,0x4C,b->low_output); ptr(a,&n,0x58,b->workspace);
    rc=kv_execute(io,bases[0],a,n,&s[0]);
    starts[0]+=s[0].submit_before!=0; dones[0]+=rc==KV_OK;
    if (rc) return rc;
    n=0; ptr(a,&n,0x10,b->low_output); ptr(a,&n,0x1C,b->full_output);
    a[n++]=(kv_arg){0x28,60}; a[n++]=(kv_arg){0x30,106};
    rc=kv_execute(io,bases[1],a,n,&s[1]);
    starts[1]+=s[1].submit_before!=0; dones[1]+=rc==KV_OK;
    if (rc) return rc;
    n=0; ptr(a,&n,0x10,b->model_input); ptr(a,&n,0x1C,b->full_output);
    ptr(a,&n,0x28,b->enhanced); a[n++]=(kv_arg){0x34,2747520};
    rc=kv_execute(io,bases[2],a,n,&s[2]);
    starts[2]+=s[2].submit_before!=0; dones[2]+=rc==KV_OK;
    return rc;
}
