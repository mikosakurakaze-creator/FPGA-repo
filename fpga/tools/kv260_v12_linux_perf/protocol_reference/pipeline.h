#ifndef KV260_PIPELINE_H
#define KV260_PIPELINE_H
#include <stdint.h>
#include <stddef.h>

/* Same core can be bound to a BSP or an OS driver. Addresses are bus addresses. */
enum { KV_OK=0, KV_STATE=1, KV_ARG=2, KV_TIMEOUT=3, KV_TIMER=4 };
typedef struct {
    void *ctx;
    uint32_t (*read32)(void *, uint64_t);
    void (*write32)(void *, uint64_t, uint32_t);
    uint64_t (*ticks)(void *);
    void (*barrier)(void *);
    uint64_t frequency, timeout_ticks;
    uint32_t poll_limit;
} kv_io;
typedef struct { uint32_t offset, value; } kv_arg;
typedef struct {
    uint64_t submit_before, submit_after, previous_before, previous_after;
    uint64_t done_before, done_after, polls, last_ctrl;
} kv_stage;
typedef struct {
    uint64_t low_input, model_input, weights, bias, frac, lut;
    uint64_t low_output, full_output, enhanced, workspace;
} kv_buffers;
int kv_execute(kv_io *, uint64_t base, const kv_arg *, size_t, kv_stage *);
int kv_pipeline(kv_io *, const kv_buffers *, kv_stage stages[3], uint64_t starts[3],
                uint64_t dones[3]);
#endif
