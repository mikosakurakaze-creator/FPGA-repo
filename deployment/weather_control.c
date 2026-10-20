#include "weather_control.h"
#include <string.h>

static int valid_buffer(const struct weather_buffer* b, size_t need) {
    uintptr_t p = (uintptr_t)b->cpu;
    return b->cpu && !(p & 1U) && !(b->device_address & 1U) &&
        b->bytes >= need && b->bytes <= UINT64_MAX - b->device_address &&
        b->bytes <= UINTPTR_MAX - p;
}
static int overlaps(uint64_t a, size_t an, uint64_t b, size_t bn) {
    return a < b + bn && b < a + an;
}
static int disjoint(const struct weather_buffer* a, const struct weather_buffer* b) {
    return !overlaps(a->device_address,a->bytes,b->device_address,b->bytes) &&
        !overlaps((uintptr_t)a->cpu,a->bytes,(uintptr_t)b->cpu,b->bytes);
}
static int release_buffers(struct weather_device* d) {
    int i;
    for (i = 2; i >= 0; --i) {
        unsigned bit = 1U << i;
        if ((d->owned_mask & bit) && !d->platform.sync(d->platform.user,&d->held[i],
                d->active_bytes[i],d->directions[i],WEATHER_CPU)) d->owned_mask &= ~bit;
    }
    if (d->owned_mask) { d->quarantined = 1; return WEATHER_EQUARANTINED; }
    return WEATHER_OK;
}
int weather_device_init(struct weather_device* d, const struct weather_platform* p,
                        enum weather_abi abi, int task) {
    if (!d || !p || !p->read32 || !p->write32 || !p->sync || !p->barrier || !p->now_us ||
        (abi != WEATHER_TILE_V1 && abi != WEATHER_FRAME_V2) ||
        (abi == WEATHER_TILE_V1 ? (task < 0 || task > 1) : task != -1)) return WEATHER_EINVAL;
    /* Do not reinitialize an active/quarantined object: only the caller can
     * ensure that this is a fresh object. Use weather_recover after a fault. */
    memset(d,0,sizeof(*d)); d->platform=*p; d->abi=abi; d->fixed_task=task;
    return WEATHER_OK;
}
static int pointer_write(struct weather_device* d, uint32_t reg, uint64_t addr) {
    return d->platform.write32(d->platform.user,reg,(uint32_t)addr) ||
        d->platform.write32(d->platform.user,reg+4,(uint32_t)(addr>>32));
}
int weather_run(struct weather_device* d, const struct weather_job* j,
                uint64_t timeout, uint32_t max_polls, uint32_t* core_return) {
    uint32_t ctrl=0, status=0, poll;
    uint64_t start;
    size_t pixels;
    int count, i, error=WEATHER_EIO;
    if (!d || !j || !timeout || !max_polls) return WEATHER_EINVAL;
    if (d->quarantined || d->owned_mask) return WEATHER_EQUARANTINED;
    if ((d->abi != WEATHER_TILE_V1 && d->abi != WEATHER_FRAME_V2) ||
        j->height < 1 || j->width < 1 || j->task < 0 || j->task > 1) return WEATHER_EINVAL;
    if (d->abi == WEATHER_TILE_V1) {
        if (j->height > 140 || j->width > 140 || j->task != d->fixed_task) return WEATHER_EINVAL;
    } else if (j->height > 720 || j->width > 1280 || j->scratch.cpu ||
                j->scratch.bytes || j->scratch.device_address) return WEATHER_EINVAL;
    pixels=(size_t)j->height*j->width; count=d->abi==WEATHER_TILE_V1 ? 3 : 2;
    d->held[0]=j->input; d->held[1]=j->output; d->held[2]=j->scratch;
    d->active_bytes[0]=d->active_bytes[1]=6*pixels; d->active_bytes[2]=48*pixels;
    d->directions[0]=WEATHER_DEVICE_READ;
    d->directions[1]=d->abi==WEATHER_TILE_V1 ? WEATHER_DEVICE_RW : WEATHER_DEVICE_WRITE;
    d->directions[2]=WEATHER_DEVICE_RW;
    for (i=0; i<count; ++i) {
        int k;
        if (!valid_buffer(&d->held[i],d->active_bytes[i])) return WEATHER_EINVAL;
        for(k=0;k<i;++k) if (!disjoint(&d->held[i],&d->held[k])) return WEATHER_EINVAL;
    }
    /* This consumes stale ap_done and rejects a running/auto-restarting IP. */
    if (d->platform.read32(d->platform.user,0,&ctrl)) return WEATHER_EIO;
    if (!(ctrl&4U) || (ctrl&0x80U)) return WEATHER_EBUSY;
    for (i=0; i<count; ++i) {
        if (d->platform.sync(d->platform.user,&d->held[i],d->active_bytes[i],
                d->directions[i],WEATHER_DEVICE)) goto before_start_error;
        d->owned_mask |= 1U << i;
    }
    if (pointer_write(d,0x18,j->input.device_address) || pointer_write(d,0x24,j->output.device_address))
        goto before_start_error;
    if (d->abi==WEATHER_TILE_V1) {
        if (pointer_write(d,0x30,j->scratch.device_address) ||
            d->platform.write32(d->platform.user,0x3c,(uint32_t)j->height) ||
            d->platform.write32(d->platform.user,0x44,(uint32_t)j->width)) goto before_start_error;
    } else if (d->platform.write32(d->platform.user,0x30,(uint32_t)j->height) ||
               d->platform.write32(d->platform.user,0x38,(uint32_t)j->width) ||
               d->platform.write32(d->platform.user,0x40,(uint32_t)j->task)) goto before_start_error;
    d->platform.barrier(d->platform.user);
    start=d->platform.now_us(d->platform.user);
    /* A failed start write may already have reached hardware: quarantine. */
    if (d->platform.write32(d->platform.user,0,1)) goto uncertain_error;
    for(poll=0;poll<max_polls;++poll) {
        if(d->platform.read32(d->platform.user,0,&ctrl)) goto uncertain_error;
        if(ctrl&2U) {
            d->platform.barrier(d->platform.user);
            error=d->platform.read32(d->platform.user,0x10,&status) ? WEATHER_EIO :
                status ? WEATHER_ECORE : WEATHER_OK;
            if(core_return && error!=WEATHER_EIO) *core_return=status;
            if(release_buffers(d)) return WEATHER_EQUARANTINED;
            return error;
        }
        if(d->platform.now_us(d->platform.user)-start>=timeout) break;
        if(d->platform.poll) d->platform.poll(d->platform.user);
    }
    d->quarantined=1; return WEATHER_ETIMEOUT;
before_start_error:
    return release_buffers(d) ? WEATHER_EQUARANTINED : WEATHER_EIO;
uncertain_error:
    d->quarantined=1; return WEATHER_EQUARANTINED;
}
int weather_recover(struct weather_device* d) {
    if(!d) return WEATHER_EINVAL;
    if(!d->quarantined && !d->owned_mask) return WEATHER_OK;
    if(!d->platform.reset_and_quiesce || d->platform.reset_and_quiesce(d->platform.user))
        return WEATHER_EQUARANTINED;
    d->platform.barrier(d->platform.user);
    if(release_buffers(d)) return WEATHER_EQUARANTINED;
    d->quarantined=0; return WEATHER_OK;
}
