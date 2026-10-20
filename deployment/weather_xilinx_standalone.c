#include "weather_xilinx_standalone.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xtime_l.h"
#include <string.h>

static void ordered(void* user) {
    (void)user;
    __asm__ volatile("dsb sy" ::: "memory");
}
static int read_reg(void* user, uint32_t offset, uint32_t* value) {
    const struct weather_xilinx_context* c = user;
    if (!value || (offset & 3U) || offset > 0x44U) return -1;
    *value = Xil_In32(c->control_base + offset);
    return 0;
}
static int write_reg(void* user, uint32_t offset, uint32_t value) {
    const struct weather_xilinx_context* c = user;
    if ((offset & 3U) || offset > 0x44U) return -1;
    Xil_Out32(c->control_base + offset, value);
    return 0;
}
static int sync_buffer(void* user, const struct weather_buffer* b, size_t bytes,
                       enum weather_direction direction, enum weather_owner owner) {
    const uintptr_t address = (uintptr_t)b->cpu;
    const size_t rounded = (bytes + 63U) & ~(size_t)63U;
    /* Enforce the specific bare-metal allocation/translation contract. */
    if ((address & 63U) || address != b->device_address ||
        !bytes || rounded > b->bytes || address >= 0x80000000ULL ||
        b->bytes > 0x80000000ULL - address) return -1;
    if (owner == WEATHER_DEVICE) {
        /* Flush also discards dirty output cache lines before PL overwrites DDR. */
        Xil_DCacheFlushRange((INTPTR)address, (INTPTR)rounded);
    } else if (direction != WEATHER_DEVICE_READ) {
        Xil_DCacheInvalidateRange((INTPTR)address, (INTPTR)rounded);
    }
    ordered(user);
    return 0;
}
static uint64_t now_us(void* user) {
    XTime count;
    (void)user;
    XTime_GetTime(&count);
    /* Avoid multiplying the full free-running 64-bit count by one million. */
    return (uint64_t)(count / COUNTS_PER_SECOND) * 1000000ULL
         + (uint64_t)(count % COUNTS_PER_SECOND) * 1000000ULL / COUNTS_PER_SECOND;
}
int weather_xilinx_platform(struct weather_platform* p, struct weather_xilinx_context* c) {
    if (!p || !c || (c->control_base & 0xffffU)) return WEATHER_EINVAL;
    memset(p, 0, sizeof(*p));
    p->user = c; p->read32 = read_reg; p->write32 = write_reg;
    p->sync = sync_buffer; p->barrier = ordered; p->now_us = now_us;
    /* No reset hook: an IP-only reset cannot prove outstanding DDR is drained. */
    return WEATHER_OK;
}
